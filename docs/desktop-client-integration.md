# Desktop Client Integration with AgentCore Memory: Design and Test Results

> Translation. The primary document is [桌面客户端集成设计](桌面客户端集成设计.md) (Chinese).
> All conclusions in this document come from live testing against real AWS infrastructure,
> not from documentation inference.
> Raw results: `build/identity-pool-validation.json` (8 assertions),
> `build/bridge-validation.json` (17 assertions).
> Related: [实验报告](实验报告.md) · [architecture.md](architecture.md) · [demo-runbook.md](demo-runbook.md)

## 1. The Problem

When an agent runs inside AgentCore Runtime, a trusted server-side component supplies the
calling identity.

The desktop-client path lacks this premise. Engineers use local agents such as Claude Code
or Codex CLI while sharing the **same cloud-hosted AgentCore Memory**: personal preferences
remain isolated by user, and team knowledge is available to members.

The identity requirement is:

> **What gives the cloud side any reason to believe "this is who I am"?**

If the client declares its own identity, changing a single environment variable lets
someone read a colleague's personal memories. The project's original single-machine MCP
server was exactly this anti-pattern:

```json
"agentcore-memory": { "env": { "AGENTCORE_DEFAULT_ACTOR": "yabolin" } }
```

That is fine for a single user working locally. The moment multiple users share a
cloud-hosted Memory, it becomes an exploitable privilege-escalation hole.

## 2. Identity Constraint

**Claude Code does not expose the logged-in user's identity to MCP servers or hooks.**

A hook's stdin contains only `session_id`, `cwd`, `transcript_path`, and
`permission_mode`. An MCP server receives only the HTTP headers you configure yourself.
Claude Code never automatically attaches any identity assertion.

This constraint eliminates an entire class of solutions: **any design where the client
tells the server who it is cannot be trusted.** Identity must come from credentials the
server can verify independently.

## 3. The Eliminated Approach: Gateway + Cognito Direct Connection

A candidate approach is AgentCore Gateway, a managed MCP endpoint that supports
`CUSTOM_JWT` inbound authentication and independently verifies a JWT's signature, issuer,
and audience.

For interactive MCP clients, however, this path does not work, for three reasons:

| Gap | Consequence |
|---|---|
| Cognito does not support RFC 7591 Dynamic Client Registration (DCR) | Claude Code cannot self-register |
| Cognito's OIDC discovery does not serve RFC 8414 metadata at the path MCP clients expect | Metadata discovery fails immediately |
| Cognito enforces exact redirect URI matching | Blocks MCP clients' loopback callbacks on random ports |

Gateway does return a `WWW-Authenticate` challenge per RFC 9728, but the client breaks
down at the subsequent metadata discovery and DCR stages. AWS blog examples for this
pattern use Kiro IDE with an `mcp-remote` proxy; there are no publicly documented
end-to-end cases with Claude Code.

**The failure occurs during the handshake, not during token expiry.**

AgentCore Identity's Token Vault can automatically refresh tokens, but it addresses
**outbound** authorization for an agent calling GitHub or Slack. Memory uses IAM rather
than OAuth, so the Token Vault does not apply to this path; AgentCore Identity also cannot
serve as an inbound authorization server.

## 4. The Adopted Approach: Local Bridge + Identity Pool

The design keeps **OAuth tokens off the hot path.**

```
Claude Code / Codex ──stdio──→ local memory-bridge (MCP server)
                                    │ 1. User logs in to IdP, obtains id_token
                                    │ 2. Identity Pool exchanges it for temporary
                                    │    credentials with session tags
                                    │ 3. Silent renewal before expiry
                                    ▼  (all subsequent calls use SigV4)
                              AgentCore Memory
                     IAM enforces isolation by actorId / namespace
```

The desktop client touches OAuth only on first sign-in; every subsequent Memory call is
SigV4-signed. This sidesteps the known fragility of Claude Code's MCP OAuth refresh and
avoids all three RFC gaps described in the previous section.

### The Key Mechanism: One Role, Session Tags Distinguish Users

**There is no need to create a separate IAM role for each user, or to maintain per-user
configuration.** All engineers share a single role; the difference in identity is carried
by the session tags that STS stamps into the credentials:

```json
{
  "Sid": "OwnShortTermMemoryOnly",
  "Effect": "Allow",
  "Action": [
    "bedrock-agentcore:CreateEvent",
    "bedrock-agentcore:ListEvents",
    "bedrock-agentcore:GetEvent"
  ],
  "Resource": "arn:aws:bedrock-agentcore:...:memory/<personal>",
  "Condition": {
    "StringEquals": {
      "bedrock-agentcore:actorId": "user:${aws:PrincipalTag/userId}"
    }
  }
}
```

The Identity Pool-side mapping (**the pivot of the entire isolation model**):

```
PrincipalTags: {'userId': 'sub'}   UseDefaults: False
```

The tag value comes from the IdP-verified `sub` claim; the client cannot influence it.
100 engineers = 1 role + 1 policy. Adding a new team member requires only creating an
account in the IdP — **zero changes on the AWS side.**

### Empirical Evidence: Condition Keys Actually Enforce

`bedrock-agentcore` provides native IAM condition keys. Tested under restricted
credentials:

| Condition key | Test result |
|---|---|
| `bedrock-agentcore:actorId` | Scoped to Alice → reads by Alice succeed; reads targeting Bob are denied by AWS |
| `bedrock-agentcore:namespace` | Matching value is allowed; non-matching value is denied |

The critical **mirror test**: when Bob signs in using the **same role**, the permissions
invert completely — Bob can read Bob's data and is denied access to Alice's. This rules
out the possibility that the policy was simply hard-coded for one user. Both callers share
the same ARN:

```
arn:aws:sts::<account-id>:assumed-role/agentcore-memory-desktop-client-role/CognitoIdentityCredentials
```

### Full Policy Structure

| Sid | Allows | Condition |
|---|---|---|
| `OwnShortTermMemoryOnly` | `CreateEvent`, `ListEvents`, `GetEvent` | `actorId` == self |
| `OwnLongTermMemoryOnly` | `RetrieveMemoryRecords`, `ListMemoryRecords` | `namespace` LIKE `/users/self/*` |
| `ReadApprovedSharedMemory` | Same (shared Memory resource) | `namespace` == this project's namespace (**no wildcard**) |
| `AppendOwnEvidenceOnly` | `s3:PutObject` | Own `evidence/self/*` prefix only |
| `DecryptMemory` | `kms:Decrypt` and related | — |

Note the **absence** of `BatchCreateMemoryRecords`. The desktop role cannot write shared
memory at the IAM level.

## 5. MCP Tool Contract: Encoding Governance Boundaries in the Tool Surface

The tool contract does not expose a direct shared-memory write operation.

| Tool | Authorization source | Notes |
|---|---|---|
| `memory_sign_in` / `memory_sign_out` | — | Establish / clear the session |
| `memory_whoami` | token | Show current identity and permissions |
| `memory_write_turn` | token `sub` | Can only write the caller's own short-term memory |
| `memory_search` | token `sub` | Personal preferences and shared knowledge **returned in separate lists** |
| `memory_capture_evidence` | token `sub` | Uploads to S3 and returns an `s3://` evidence reference |
| `memory_propose_shared` | token `sub` | Submits a **proposal** only; routes to human review |
| `memory_review_queue` / `memory_review_decide` | token + reviewer group | Non-reviewers receive an explicit 403 |
| ~~`memory_write_shared`~~ | — | **Not provided** |

Three design constraints:

1. **No tool accepts an `actor_id` or `namespace` parameter** — the client cannot assert
   its own identity.
2. **Credentials are short-lived and tagged** — even if the bridge has a bug, IAM
   provides the backstop.
3. **No tool writes shared memory directly** — team knowledge can only be proposed.

`memory_search` intentionally returns the two knowledge types in separate lists, together
with a precedence rule (live data > authoritative documentation > shared knowledge >
personal preferences > model inference), to prevent the model from treating a personal
preference as a team-wide conclusion.

## 6. The Evidence Chain: Why a Local Transcript Is Not Evidence

The governance rules require every candidate to carry an `evidence_ref` pointing to an
immutable record (`trace://`, `s3://`, or `log://`).

**Claude Code's transcript lives on the user's own disk, where it can be edited or
deleted, and therefore cannot serve as evidence.** If it could, a reviewer would be
approving a statement that cannot be independently verified after the fact.

The solution: `memory_capture_evidence` uploads the conversation excerpt along with a
SHA-256 digest to an append-only audit bucket and returns an `s3://` reference.

Bucket constraints (CDK-defined):

- KMS encryption, SSL enforced, public access blocked, versioning enabled
- Bucket policy DENYs `s3:DeleteObject`, `s3:DeleteObjectVersion`, and `s3:PutObjectAcl`
  (excluding the account root principal — omitting that exclusion would lock out lifecycle
  management and emergency recovery)
- The desktop role has only `s3:PutObject`, restricted to its own prefix
- **`evidence_ref` pins the `versionId`**

### Incorrect Assumption in the Initial Implementation

The first version denied only deletion and therefore assumed that "the proposer cannot alter
their own evidence." Code review prompted a test that disproved the assumption:
result overturned it:

```
2. Overwrite at the same key (evidence forgery): *** ALLOWED ***
3. Delete:                                        AccessDenied
```

The bucket policy does not block the author from re-PUTting under the **same key**.
Versioning preserves the old version, but a bare `s3://bucket/key` reference resolves to
the **latest version** — so a proposer can swap out the evidence after approval, and a
reviewer clicking the link would see the forged content. My initial tests only covered
deletion and missed this path entirely.

The fix is not to prohibit overwrites (that would break normal retries) — it is to
**make the reference point to a specific version**:

```
s3://<bucket>/evidence/user:<sub>/2026/07/28/163727-38dee654ece1.json?versionId=NL0WCbWdQcQEjW5w...
```

Overwrites remain allowed, but deleting a version is denied, so the version that the
reference pins never changes. Test result:

```
[PASS] The reviewed evidence version cannot be altered by its author
       pins_version=yes  delete=AccessDenied
       overwrite_key=ALLOWED  delete_pinned=AccessDenied  other_prefix=AccessDenied
```

Reading the S3 object directly and comparing the two versions of the same key:

```
latest=False  NL0WCbWdQcQEjW5w... -> {"captured_at": "2026-07-28T16:37:27...", "pr...
latest=True   rZsO4DeDfN0FslAr... -> {"excerpt":"FORGED"}
```

The forged content is now the latest version, but **the version that the reference pins
still returns the original.** The reviewer always sees the content they approved.

The proposer also cannot write forged evidence into someone else's prefix
(`other_prefix=AccessDenied`).

## 7. The Proposal Path: POST /proposals

The desktop role does not hold `events:PutEvents` permission (which would allow bypassing
validation by injecting events directly). Proposals go through a Cognito-protected API
instead:

```
Claude Code → memory_propose_shared → POST /proposals (Cognito)
                                          │ Validate + extract sub from token
                                          ▼
                                    EventBridge
                                          ▼
                          Step Functions (policy gate → human review)
                                          ▼
                                    Shared Memory
```

Two key points in `src/handlers/propose_candidate.py`:

**1. The proposer is derived from the token only — never trusted from the request body.**
Otherwise a client could attribute a rejected statement to a colleague.

```python
"proposer_actor_id": f"user:{subject}",   # subject comes from Cognito claims
```

The same applies to `project_id`: it is determined by a server-side environment variable
and cannot be overridden by the request body.

**2. Status is reported honestly.** A candidate that does not clear the policy gate never
reaches the reviewer, so the response returns `SUBMITTED` with an `eligible_for_review`
field rather than unconditionally claiming `PENDING_REVIEW`.

This Lambda's IAM permissions are limited to `events:PutEvents` — CDK tests assert that
it cannot touch Memory or the candidate table.

## 8. End-to-End Test Results

### Identity Pool Isolation (8/8)

```
[PASS] Alice writes her own short-term memory              → ALLOWED
[PASS] Alice writes into Bob's actor (impersonation)       → AccessDeniedException
[PASS] Alice reads her own events                          → ALLOWED
[PASS] Alice reads Bob's events                            → AccessDeniedException
[PASS] Alice retrieves her own preference namespace        → ALLOWED
[PASS] Alice retrieves Bob's preference namespace          → AccessDeniedException
[PASS] Alice reads approved shared project memory          → ALLOWED
[PASS] Alice writes shared memory directly, bypassing review → AccessDeniedException
```

### Bridge Behaviour (17/17, over real MCP JSON-RPC via stdio)

> The following are raw results from the 2026-07-28 run, not backfilled. One assertion
> was added afterwards — verifying that the proposal tool description contains the
> **semantics** of all five `category` values, not merely their names — and that
> assertion is not reflected in the table below. Re-running `bridge/validate_bridge.py`
> will produce a result that includes it.

```
[PASS] Tool surface offers no direct shared-memory write
[PASS] Tools refuse to act before sign-in
[PASS] Writing without sign-in is refused
[PASS] Sign-in derives actor_id from the verified token
[PASS] Two clients get two distinct identities from one shared IAM role
[PASS] Alice writes a turn into her own memory
[PASS] Bob's credentials are refused on Alice's actor and namespace
[PASS] Bob's search returns no trace of Alice's content
[PASS] Search separates personal from approved shared knowledge
[PASS] Approved shared knowledge is readable by any signed-in member
[PASS] Proposals validate evidence provenance locally
[PASS] Proposals validate category and confidence range locally
[PASS] A well-formed proposal is not silently dropped
[PASS] Evidence capture returns an immutable s3:// reference
[PASS] The reviewed evidence version cannot be altered by its author
[PASS] Desktop proposal with real evidence reaches the review pipeline
[PASS] Non-reviewer is refused the review queue
```

### Full End-to-End Loop

Complete pipeline verified, from a desktop proposal to team knowledge:

| Stage | Test result |
|---|---|
| Desktop evidence capture | `s3://.../evidence/user:34e8b408-.../2026/07/28/160319-38dee654ece1.json` |
| Desktop proposal | `cand-desktop-0a2dc579bb26`, proposer derived from the token's `sub` |
| Written to candidate table | `PENDING_REVIEW`, evidence points to a real S3 object |
| Reviewer approves | `PUBLISHED`, reviewer_id `64c844a8-...` |
| Shared memory published | `mem-d3f81ee6-fe7d-4e03-ae5f-7f515f8c28a4` |
| Retrievable and verified | Record is retrievable; metadata includes `candidate_id` linking back to the candidate |

**A piece of knowledge proposed from a desktop client, after review, becomes available
across the entire project and can be traced back to both the evidence and the approver.**

## 9. Deployment and Configuration

### Shared Team Configuration (`.mcp.json`, safe to commit)

```json
{
  "mcpServers": {
    "memory-bridge": {
      "type": "stdio",
      "command": "${CLAUDE_PROJECT_DIR}/bridge/.venv/bin/python",
      "args": ["${CLAUDE_PROJECT_DIR}/bridge/server.py"],
      "env": {
        "MEMORY_BRIDGE_DEPLOYMENT": "${CLAUDE_PROJECT_DIR}/build/poc-deployment.json",
        "MEMORY_BRIDGE_IDENTITY_POOL_ID": "${MEMORY_BRIDGE_IDENTITY_POOL_ID}"
      }
    }
  }
}
```

Project-level scope means the whole team shares one server definition while each person
authenticates as themselves. The file contains no secrets; each team member supplies the
`${VAR}` values locally.

### Validation Commands

```bash
# IAM isolation (creates an Identity Pool, shared role, and test users)
python3 poc/validate_identity_pool.py --deployment build/poc-deployment.json

# Bridge behaviour (drives real MCP protocol as two different users)
python3 bridge/validate_bridge.py --python "$PWD/bridge/.venv/bin/python"
```

### Choosing an Upstream IdP

This test used the project's existing Cognito User Pool. Production environments should
use the company's existing identity source:

| Option | When to use |
|---|---|
| Identity Center | Already using IdC for AWS access management; personnel lifecycle follows HR |
| Enterprise IdP direct federation (Okta / Entra ID) | Identity source lives in the enterprise IdP; no desire to introduce IdC |
| Cognito User Pool | POC / external contractors |

**Switching IdPs replaces only the upstream — the downstream IAM layer requires no
changes.** The isolation logic hangs on the session tag; it does not care which provider
signed it.

The decision rule is straightforward: use whatever path engineers already follow to sign
in to AWS, and do not invent a new identity source. A separate identity source means two
places to deactivate an account when someone leaves — real security debt.

## 10. Lessons from the Testing Methodology

Both validation rounds in this design started with "all passing" — and both times,
reviewing the raw evidence uncovered false positives.

### Trap 1: A Vacuous Pass

The check "Bob cannot find Alice's content" passed — but at the time Alice had **0**
preference records (async extraction had not finished), so both sides were empty. The test
proved that data did not exist; it did not prove isolation was working.

**Fix:** Replace with a direct cross-user read permission probe. AWS returns
AccessDeniedException immediately, with no dependency on async extraction.

This is the same class of trap documented in section 7 of [实験報告](实验报告.md) — a
sign of how easy this mistake is to repeat.

### Trap 2: Testing the Wrong Failure Reason

The check "low-confidence proposal is blocked" passed — but the actual response was a 403
caused by an undeployed route, not a policy rejection. API Gateway returns a misleadingly
worded SigV4 error for routes that do not exist.

**Fix:** Split into two assertions — locally determinable validation (unknown category,
confidence out of range) is asserted separately; a missing route is reported honestly
rather than counted as a success.

> **Methodology:** Security assertions must verify both "what should be blocked is blocked"
> and "what should exist actually exists." Testing only the former means a completely empty
> system passes every isolation test.
> Equally important: **check the failure reason code**, not just whether a failure occurred.

## 11. Production Gaps

| Gap | Description | Severity |
|---|---|---|
| No project membership authorization | The policy is tightened to a single project namespace (no longer using the `project:*` wildcard), but **project membership is fixed at deployment time, not evaluated per user**. Multi-project scenarios require encoding project membership in an IdP claim, mapping it to a dedicated session tag, and referencing that tag in the condition | High |
| Project membership cannot be inferred from `cwd` | It is tempting to infer the current project from the git remote or `cwd`, but `cwd` is client-declared and trivially forgeable. `cwd` may serve only as a **hint** for selecting a default project | High |
| Evidence covers explicit captures only | `memory_capture_evidence` requires the agent to call it proactively. If the model skips this step, the proposal is rejected on evidence validation — safe, but poor ergonomics. A hook to capture evidence automatically is worth considering | Medium |
| Bridge uses password login | The POC uses `USER_PASSWORD_AUTH`. Production should use a browser-based authorization code flow with PKCE to avoid passing credentials through MCP tool parameters | Medium |
| Token cached on local disk | The refresh token is stored in `~/.agentcore-memory-bridge/session.json` (mode 0600). Production should use the system keychain | Medium |
| No Guardrails | Bedrock Guardrails should be applied before writing to storage and before injecting memory into a prompt | Medium |
| Evidence bucket retention is 365 days | Must be aligned with compliance requirements; there is currently no Object Lock (compliance mode), only bucket policy DENY | Medium |
| Hook integration not implemented | Automatic memory write / retrieval requires hook invocation of the local bridge (hooks themselves cannot access identity and should not connect directly to the cloud) | Low |

## 12. Conclusion

Claude Code and Codex CLI can access cloud-hosted AgentCore Memory through a local bridge
and an Identity Pool. The design assumes that a desktop client is not a trustworthy
identity source.

The implementation proceeds as follows:

1. Have the user sign in to the enterprise IdP locally.
2. Have the Identity Pool map the verified `sub` to a session tag.
3. Use a **single shared IAM role** with `${aws:PrincipalTag/userId}` to enforce isolation.
4. Expose no tool capable of crossing isolation boundaries; team knowledge can only be
   proposed.

AWS controls enforce isolation without relying on correct client or bridge behavior. Mirror
testing with two real users confirmed this property.
