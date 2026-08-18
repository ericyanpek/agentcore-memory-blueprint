# Positioning Rewrite and Exit Mechanism Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the six items in section 八 of the 2026-08-14 positioning review: correct a
factual error about record expiry, reposition the README around capture economics, wire the
broken promotion path, add an AgentCore-agnostic layering document, move and extend the
limitations section, and instrument shared-memory hit rate and query overlap.

**Architecture:** This repository is a documentation-heavy AWS reference implementation.
Four of the six items are prose edits to bilingual document pairs; two touch code (a CDK
EventBridge rule plus SQS queue, and retrieval instrumentation in the context builder with
an offline analyzer). Every prose change must be mirrored in its language pair, because
`scripts/check_doc_alignment.py` compares heading structure, table row counts, code fence
counts, `[PASS]`/`[FAIL]` evidence lines, and the *set of URLs* on each side, and a
pre-commit hook rejects a half-updated pair.

**Tech Stack:** Markdown (bilingual pairs), Python 3.12 + `unittest` (handlers, agent,
scripts), TypeScript + AWS CDK v2 + Jest (`infra/`), Amazon Bedrock AgentCore Memory.

---

## Critical context before you start

Read this section fully. Three claims in the source review are wrong or imprecise, and one
repository convention will reject your commits if you ignore it.

**1. `review_status` is already an indexed key.** The review says the indexed keys needed
for supersession "cannot be added now." Verified false: `infra/lib/memory-governance-stack.ts:86-91`
already declares `project_id`, `category`, `review_status`, `promotion_hint`. Since the
supersession design in `docs/roadmap.md:121` flips `review_status` to a terminal value, and
`src/agent/context_builder.py:87` already pre-filters on `review_status = approved`, a
superseded record leaves the retrievable set with **no new indexed key required**. The only
genuinely missing key is `superseded_by`, used to find the replacement record. Task 2 adds
that one key and nothing else. Do not add speculative keys.

**2. `indexedKeys` immutability has a deployment consequence you must document, not hide.**
Indexed keys are declared at `CreateMemory` time. The shared Memory resource carries
`RemovalPolicy.RETAIN` (`memory-governance-stack.ts:92`), so adding a key changes the
synthesized template but an already-deployed resource will not gain the key. Task 2's code
comment and doc text must say this plainly: the key is declared now so that a
*newly created* resource has it, and an existing deployment needs a new Memory resource to
pick it up. Do not claim the change retrofits an existing resource.

**3. Citation discipline is enforced, and two numbers in the source review are unverified.**
`CLAUDE.md` requires fetching each source and confirming the quote appears there.
The source review cites `arXiv:2607.02579` (GovMem, "0/133 safe for automatic promotion")
and `arXiv:2606.22721` ("Habituation at the Gate", "+14.5pp"). **Neither has been verified
in this repository.** Task 8 fetches both before writing them. If a fetch fails or the
numbers do not appear, Task 8 tells you exactly what to write instead — a claim sourced from
this repository's own measured evidence. Never paste an arXiv ID from the review into a doc
without fetching it first.

**4. The bilingual checker will reject asymmetric edits.** Before every documentation commit:

```bash
python3 scripts/check_doc_alignment.py
```

Expected on success: a line `ok       <zh> <-> <en>` for every pair and a final
`all N pairs aligned`. The four dimensions that break most often:

- Adding a heading to one side only → `heading structure differs`
- Adding a table row to one side only → `table rows differ`
- Citing a URL on one side only → `URLs only in README.md: [...]`
- Adding a fenced code block to one side only → `code fences differ`

If the hook blocks a commit and the divergence is intentional, use
`CODE_DEFENDER_SKIP_LOCAL_HOOKS=true git commit ...`. **Never `--no-verify`** — on a managed
machine that also skips the corporate security scan.

**5. Baseline check.** Run this before Task 1 and confirm it is green, so you can tell your
own breakage from pre-existing breakage:

```bash
python3 scripts/check_doc_alignment.py && python3 -m unittest discover -s tests -q
```

Note: the working tree already contains uncommitted changes (new enterprise governance docs
registered in `CLAUDE.md` and `scripts/check_doc_alignment.py`). Leave them alone; they are
not part of this plan.

---

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `README.md` / `README.en.md` | Positioning, limitations, doc index | 1, 3, 5, 7, 7b, 9, 12 |
| `docs/下一步演进.md` / `docs/roadmap.md` | Corrected expiry facts, trigger/promotion severity | 1, 6 |
| `infra/lib/memory-governance-stack.ts` | `superseded_by` indexed key; promotion rule + queue | 2, 4 |
| `infra/test/memory-governance-stack.test.ts` | Assertions for both infra changes | 2, 4 |
| `docs/为什么按写入权威分层.md` (new) | AgentCore-agnostic layering argument, Chinese primary | 7 |
| `docs/why-layer-by-write-authority.md` (new) | English translation of the above | 7 |
| `scripts/check_doc_alignment.py` | Register the new pair | 7 |
| `CLAUDE.md` | Register the new pair in the conventions table | 7 |
| `src/agent/context_builder.py` | Emit per-retrieval metrics | 9, 10 |
| `tests/test_retrieval_metrics.py` (new) | Fingerprinting and metric shape | 9 |
| `poc/analyze_retrieval_metrics.py` (new) | Offline hit-rate and overlap analysis | 11 |
| `tests/test_analyze_retrieval_metrics.py` (new) | Analyzer arithmetic | 11 |

---

## Task 1: Correct the record-expiry claim in the README pair

The README claims an approved false statement stays retrievable only "until the resource
expiry." No such backstop exists. Records written by `BatchCreateMemoryRecords` have no
source event, so no event TTL reaches them.

**Files:**
- Modify: `README.md:247`
- Modify: `README.en.md:293-294`

- [ ] **Step 1: Verify the API facts before writing them**

Fetch the AgentCore control-plane API reference for `CreateMemory` and the data-plane
reference for `BatchCreateMemoryRecords`, and confirm two things:

1. `eventExpiryDuration` is described as applying to **events**, not records.
2. `MemoryRecordCreateInput` has no expiry field — expected members are `content`,
   `namespaces`, `requestIdentifier`, `timestamp`, `memoryStrategyId`, `metadata`.

Start from the service documentation index:

```
https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-getting-started.html
```

Record the exact URL that confirms each fact. You will cite one of them in Step 2, and it
must be a URL you actually fetched. If neither page is reachable, verify locally against the
pinned service model instead:

```bash
python3 -c "
import boto3, json
m = boto3.client('bedrock-agentcore').meta.service_model
s = m.shape_for('MemoryRecordCreateInput')
print(sorted(s.members))
"
```

Expected: a member list with no expiry-like key. Use that as the evidence and cite no URL
(which keeps both sides of the pair URL-symmetric with zero effort).

- [ ] **Step 2: Rewrite the Chinese bullet**

In `README.md`, replace this line:

```markdown
- **已批准事实没有取代通路**，变为假的陈述仍可检索至资源过期。
```

with:

```markdown
- **已批准事实没有取代通路，且没有过期兜底。** 共享记录由
  `BatchCreateMemoryRecords` 直接创建，没有对应的 source event，因此按 event 生效的
  `eventExpiryDuration` 碰不到它，`MemoryRecordCreateInput` 上也没有任何 expiry 字段 ——
  变为假的陈述永久可检索，且带 `review_status=approved` 预过滤标签，在检索里是一等公民。
  记录级移除只有显式 `DeleteMemoryRecord` / `BatchDeleteMemoryRecords`。
```

- [ ] **Step 3: Mirror it in English**

In `README.en.md`, replace:

```markdown
- **Approved facts have no supersession path**; a statement that becomes false stays
  retrievable until the resource expiry.
```

with:

```markdown
- **Approved facts have no supersession path, and no expiry backstop.** Shared records are
  created directly by `BatchCreateMemoryRecords` with no source event, so
  `eventExpiryDuration` — which applies per event — never reaches them, and
  `MemoryRecordCreateInput` carries no expiry field. A statement that becomes false stays
  retrievable indefinitely, carrying a `review_status=approved` pre-filter label that makes
  it a first-class retrieval result. Record-level removal exists only through an explicit
  `DeleteMemoryRecord` / `BatchDeleteMemoryRecords`.
```

- [ ] **Step 4: Verify alignment**

Run: `python3 scripts/check_doc_alignment.py`
Expected: `ok       README.md <-> README.en.md` and a final `all N pairs aligned`. If you see
`URLs only in ...`, you cited a URL on one side only — add it to both or remove it.

- [ ] **Step 5: Commit**

```bash
git add README.md README.en.md
git commit -m "$(cat <<'EOF'
Correct the claim that approved records expire with the resource

Records written by BatchCreateMemoryRecords have no source event, so
eventExpiryDuration never reaches them and MemoryRecordCreateInput has no
expiry field. The stated backstop does not exist, which makes the missing
supersession path a permanent condition rather than a 90-day one.
EOF
)"
```

---

## Task 2: Declare the `superseded_by` indexed key

**Files:**
- Modify: `infra/lib/memory-governance-stack.ts:86-91`
- Test: `infra/test/memory-governance-stack.test.ts:18-27`

- [ ] **Step 1: Write the failing test**

In `infra/test/memory-governance-stack.test.ts`, replace the body of the existing
`configures reviewed shared memory for direct indexed records` test with:

```typescript
  test("configures reviewed shared memory for direct indexed records", () => {
    template.hasResourceProperties("AWS::BedrockAgentCore::Memory", {
      Description: "Directly written, reviewed project experience only",
      IndexedKeys: [
        { Key: "project_id", Type: "STRING" },
        { Key: "category", Type: "STRING" },
        { Key: "review_status", Type: "STRING" },
        { Key: "promotion_hint", Type: "STRING" },
        { Key: "superseded_by", Type: "STRING" },
      ],
    });
  });
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
cd infra && npm test -- -t "direct indexed records"
```

Expected: FAIL, reporting that the template's `IndexedKeys` has four entries and does not
match the expected five.

- [ ] **Step 3: Add the key**

In `infra/lib/memory-governance-stack.ts`, replace:

```typescript
    sharedMemoryResource.indexedKeys = [
      { key: "project_id", type: "STRING" },
      { key: "category", type: "STRING" },
      { key: "review_status", type: "STRING" },
      { key: "promotion_hint", type: "STRING" },
    ];
```

with:

```typescript
    // Indexed keys are fixed at CreateMemory time and cannot be added later, and this
    // resource is RETAIN, so `superseded_by` is declared before supersession is
    // implemented (docs/roadmap.md item 4). An already-deployed resource does not gain
    // the key from this change; it reaches only a newly created Memory.
    sharedMemoryResource.indexedKeys = [
      { key: "project_id", type: "STRING" },
      { key: "category", type: "STRING" },
      { key: "review_status", type: "STRING" },
      { key: "promotion_hint", type: "STRING" },
      { key: "superseded_by", type: "STRING" },
    ];
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
cd infra && npm run build && npm test
```

Expected: PASS for all tests in `memory-governance-stack.test.ts`.

- [ ] **Step 5: Commit**

```bash
git add infra/lib/memory-governance-stack.ts infra/test/memory-governance-stack.test.ts
git commit -m "$(cat <<'EOF'
Declare superseded_by before the door closes

Indexed keys are fixed at CreateMemory time and the shared Memory resource is
RETAIN, so a key that supersession will need cannot be added once a resource
exists. review_status is already indexed and already pre-filtered on retrieval,
so this is the only key the design is missing.
EOF
)"
```

---

## Task 3: State the indexed-key constraint in the README pair

The constraint from Task 2 is a deployment-affecting fact that belongs in the docs, not only
in a code comment.

**Files:**
- Modify: `README.md` (the "部署" section, after the `cdk deploy` block)
- Modify: `README.en.md` (the "Deployment" section, same position)

- [ ] **Step 1: Add the Chinese paragraph**

In `README.md`, immediately before the paragraph beginning `Knowledge Base ID 是集成参数`,
insert:

```markdown
共享 Memory 的 `indexedKeys` 在 `CreateMemory` 时固定，不可增删、不回填，而该资源是
`RETAIN` 的。取代机制所需的 `superseded_by` 已提前声明，但已部署的资源不会因此获得该键 ——
只有新建的 Memory 资源才带上它。
```

- [ ] **Step 2: Mirror it in English**

In `README.en.md`, immediately before the paragraph beginning `The Knowledge Base ID is an
integration parameter`, insert:

```markdown
The shared Memory's `indexedKeys` are fixed at `CreateMemory` time — they cannot be added
or removed and are not backfilled — and the resource is `RETAIN`. The `superseded_by` key
that supersession needs is therefore declared ahead of use, but an already-deployed
resource does not gain it; only a newly created Memory carries it.
```

- [ ] **Step 3: Verify and commit**

```bash
python3 scripts/check_doc_alignment.py
```

Expected: `ok       README.md <-> README.en.md`.

```bash
git add README.md README.en.md
git commit -m "$(cat <<'EOF'
Record that indexed keys cannot be added to a deployed Memory

The superseded_by key reaches only newly created resources, and a reader
planning a deployment needs that before they plan one.
EOF
)"
```

---

## Task 4: Wire the promotion event to a subscriber

`src/handlers/mark_status.py:52` emits `memory.promotion.proposed`, and the README
architecture diagram draws two arrows from it to the Knowledge Base and Skills. Verified:
the only `events.Rule` in the stack is `CandidateRule` at
`memory-governance-stack.ts:352`, matching `memory.candidate.proposed`. Nothing subscribes
to the promotion event, so it is emitted into nothing. `docs/roadmap.md` and
`docs/demo-runbook.md:139` both call for a one-time promotion queue; this task builds it.

**Files:**
- Modify: `infra/lib/memory-governance-stack.ts` (after the `CandidateRule` block, ending
  around line 369)
- Test: `infra/test/memory-governance-stack.test.ts`

- [ ] **Step 1: Write the failing tests**

Append to the `describe` block in `infra/test/memory-governance-stack.test.ts`:

```typescript
  test("routes promotion proposals to a durable queue", () => {
    template.hasResourceProperties("AWS::Events::Rule", {
      EventPattern: {
        source: ["demo.memory-governance"],
        "detail-type": ["memory.promotion.proposed"],
        detail: { project_id: ["analytics-poc"] },
      },
    });
  });

  test("the promotion queue is encrypted with the memory key", () => {
    template.hasResourceProperties("AWS::SQS::Queue", {
      QueueName: "analytics-poc-test-promotion-queue",
      KmsMasterKeyId: Match.anyValue(),
    });
  });
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd infra && npm test -- -t "promotion"
```

Expected: FAIL on both — no `AWS::Events::Rule` matches the promotion detail-type, and no
queue named `analytics-poc-test-promotion-queue` exists.

- [ ] **Step 3: Add the queue and rule**

In `infra/lib/memory-governance-stack.ts`, immediately after the closing `});` of the
`new events.Rule(this, "CandidateRule", {...})` block, insert:

```typescript
    // The promotion hint on an approved candidate says where the knowledge should end up,
    // but a Knowledge Base ingestion job and a Git review are both outside this stack.
    // The event is therefore parked in a queue a human drains, rather than emitted into
    // nothing: an unsubscribed event is indistinguishable from a promotion that was
    // considered and declined.
    const promotionQueue = new sqs.Queue(this, "PromotionQueue", {
      queueName: this.resourceName(prefix, "promotion-queue"),
      encryption: sqs.QueueEncryption.KMS,
      encryptionMasterKey: memoryKey,
      retentionPeriod: Duration.days(14),
    });
    new events.Rule(this, "PromotionRule", {
      eventBus,
      ruleName: this.resourceName(prefix, "memory-promotion"),
      eventPattern: {
        source: ["demo.memory-governance"],
        detailType: ["memory.promotion.proposed"],
        detail: {
          project_id: [props.projectId],
        },
      },
      targets: [new targets.SqsQueue(promotionQueue)],
    });
    new CfnOutput(this, "PromotionQueueUrl", {
      value: promotionQueue.queueUrl,
    });
```

`sqs`, `events`, `targets`, `Duration`, and `CfnOutput` are already imported for the
workflow DLQ and other outputs; do not add imports.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd infra && npm run build && npm test && npx cdk synth > /dev/null
```

Expected: all tests PASS, and `cdk synth` exits 0 without contacting AWS.

- [ ] **Step 5: Commit**

```bash
git add infra/lib/memory-governance-stack.ts infra/test/memory-governance-stack.test.ts
git commit -m "$(cat <<'EOF'
Give the promotion event a subscriber

mark_status.py emitted memory.promotion.proposed and the architecture diagram
drew two arrows out of it, but no rule matched the detail-type, so an approved
candidate marked for promotion went nowhere. A queue a human drains is the
honest version of a path that ends outside this stack.
EOF
)"
```

---

## Task 5: Correct the promotion arrows in the README architecture pair

The diagram implies automatic promotion. It is now a queue, and the diagram should say so.

**Files:**
- Modify: `README.md:157-159` (mermaid block)
- Modify: `README.en.md` (the matching mermaid block in the Architecture section)

- [ ] **Step 1: Update the Chinese diagram**

In `README.md`, replace these three lines inside the mermaid block:

```
    SF --> P["晋升事件"]
    P --> KB["托管 Knowledge Base<br/>权威文档"]
    P --> SK["Git 中的团队 Skills<br/>可执行流程"]
```

with:

```
    SF --> P["晋升事件 → 晋升队列"]
    P --> KB["托管 Knowledge Base<br/>权威文档（人工摄取）"]
    P --> SK["Git 中的团队 Skills<br/>可执行流程（人工评审）"]
```

- [ ] **Step 2: Update the English diagram identically in structure**

In `README.en.md:191-193`, replace:

```
    SF --> P["Promotion event"]
    P --> KB["Managed Knowledge Base<br/>authoritative documents"]
    P --> SK["Team Skills in Git<br/>executable procedures"]
```

with:

```
    SF --> P["Promotion event → promotion queue"]
    P --> KB["Managed Knowledge Base<br/>authoritative documents (manual ingestion)"]
    P --> SK["Team Skills in Git<br/>executable procedures (manual review)"]
```

The node IDs (`SF`, `P`, `KB`, `SK`) and arrow syntax stay byte-identical to the Chinese
version, since Mermaid source is code.

- [ ] **Step 3: Verify alignment**

Run: `python3 scripts/check_doc_alignment.py`
Expected: `ok       README.md <-> README.en.md`. Code fence counts are unchanged because you
edited inside an existing fence.

- [ ] **Step 4: Commit**

```bash
git add README.md README.en.md
git commit -m "$(cat <<'EOF'
Show promotion as a queue a human drains

The diagram's bare arrows to Knowledge Base and Skills read as automation. Both
destinations are outside this stack and both need a person.
EOF
)"
```

---

## Task 6: Raise the trigger and promotion items to the mainline in the roadmap pair

Roadmap item 5 ("When to propose, and what qualifies", severity high) contains the
observation that candidates in the experiment "were produced by a script calling the API
directly." Per the positioning review, the capture trigger is not a nice-to-have but a
precondition for the whole argument. This task states that, and records that the promotion
path is now a queue.

**Files:**
- Modify: `docs/下一步演进.md:98-105` (item 4 current-behaviour paragraph)
- Modify: `docs/roadmap.md:121-131` (the same paragraph in English)
- Modify: `docs/下一步演进.md:184` and `docs/roadmap.md:228` (item 5 severity line)

- [ ] **Step 1: Correct item 4's expiry claim in Chinese**

In `docs/下一步演进.md`, replace:

```markdown
**当前行为。** 已批准的共享记录不可变，且在 90 天资源过期期限内实质上永久有效。没有
任何方式将其标记为不再为真。
```

with:

```markdown
**当前行为。** 已批准的共享记录不可变，且**永久**有效 —— 先前此处写作"在 90 天资源过期
期限内"，该兜底不存在：`eventExpiryDuration` 按 event 在写入时生效，而共享记录经
`BatchCreateMemoryRecords` 直接创建，没有对应的 source event，`MemoryRecordCreateInput`
也没有任何 expiry 字段。记录级移除只有显式 `DeleteMemoryRecord` /
`BatchDeleteMemoryRecords`。没有任何方式将其标记为不再为真。
```

- [ ] **Step 2: Mirror it in English**

In `docs/roadmap.md`, replace:

```markdown
**Current behaviour.** An approved shared record is immutable and effectively
permanent within the 90-day resource expiry. There is no way to mark it as no longer
true.
```

with:

```markdown
**Current behaviour.** An approved shared record is immutable and **permanent**. This
paragraph previously said "within the 90-day resource expiry"; that backstop does not
exist. `eventExpiryDuration` applies per event at write time, and a shared record created
directly by `BatchCreateMemoryRecords` has no source event, while
`MemoryRecordCreateInput` carries no expiry field. Record-level removal exists only
through an explicit `DeleteMemoryRecord` / `BatchDeleteMemoryRecords`. There is no way to
mark a record as no longer true.
```

- [ ] **Step 3: Note in item 4 that `superseded_by` is now declared**

In `docs/下一步演进.md`, at the end of the `**涉及文件。**` paragraph of item 4, append:

```markdown
`superseded_by` 已作为索引键声明（`infra/lib/memory-governance-stack.ts`），因为索引键在
`CreateMemory` 时固定、不可后加。
```

In `docs/roadmap.md`, append to the matching `**Files.**` paragraph:

```markdown
`superseded_by` is already declared as an indexed key
(`infra/lib/memory-governance-stack.ts`), because indexed keys are fixed at
`CreateMemory` time and cannot be added afterwards.
```

- [ ] **Step 4: Restate item 5 as a precondition, not a to-do**

In `docs/下一步演进.md`, replace the opening paragraph of item 5, which currently begins
`**当前行为。** 提案契约本身是完整的`, by inserting this sentence immediately before it:

```markdown
**这一项是整套论证的前提，不是待办。** 审批链路完整而捕获触发点缺失，意味着治理链路的
瓶颈从来不在中间那一段；本仓库自身即为标本 —— 实验报告中的候选项均由脚本产生，而
`skills/` 目录自创建以来只有新增、没有一次修改。
```

In `docs/roadmap.md`, insert before `**Current behaviour.** The proposal contract itself is
complete`:

```markdown
**This item is a precondition of the argument, not a backlog entry.** The approval chain is
complete while the capture trigger is missing, which means the bottleneck was never the
middle segment. This repository is its own specimen: every candidate in the experiment
report was produced by a script, and the `skills/` directory has only ever been added to,
never modified.
```

- [ ] **Step 5: Verify alignment**

Run: `python3 scripts/check_doc_alignment.py`
Expected: `ok       docs/下一步演进.md <-> docs/roadmap.md`. You added no headings, no table
rows, no code fences, and no URLs, so only prose changed.

- [ ] **Step 6: Commit**

```bash
git add docs/下一步演进.md docs/roadmap.md
git commit -m "$(cat <<'EOF'
Correct the roadmap's expiry backstop and name the real bottleneck

Item 4 asserted a 90-day resource expiry that does not apply to directly
written records. Item 5 was filed as a to-do when a missing capture trigger is
what the governance argument rests on, and this repository demonstrates the
failure it describes.
EOF
)"
```

---

## Task 7: Add the AgentCore-agnostic layering document

The layering-by-write-authority argument is the most portable idea in the repository and is
currently only readable as an AgentCore feature. This task extracts it into a standalone
pair that a reader on any platform can cite.

**Files:**
- Create: `docs/为什么按写入权威分层.md` (Chinese, primary)
- Create: `docs/why-layer-by-write-authority.md` (English translation)
- Modify: `scripts/check_doc_alignment.py:23-47` (register the pair)
- Modify: `CLAUDE.md` (the "Current pairs" table)
- Modify: `README.md` and `README.en.md` (the document index table)

- [ ] **Step 1: Write the Chinese document**

Create `docs/为什么按写入权威分层.md` with exactly this heading structure and no others:

```markdown
# 为什么按写入权威分层

> 本文档为主版本。English: **[why-layer-by-write-authority.md](why-layer-by-write-authority.md)**。
> 本文不涉及任何具体平台。此处的论证在任何具备多层记忆的系统上成立。

## 问题：episodic/semantic 回答不了唯一要紧的那个问题

## 六层与它们的写入者

## 冲突裁决因此变成查表

## 检索优先级必须是全序

## 共享层是知识资产的预备区

## 这套分层不承诺什么
```

Content requirements for each section, in order:

1. **问题** — State that the standard taxonomy (episodic / semantic / procedural) classifies
   memory by *what it contains*, and that the operational question is always *may this
   override that*. A containment taxonomy has no answer to it. Adapt the reasoning already
   in `docs/设计取舍依据.md`; do not introduce new external citations.
2. **六层与它们的写入者** — A table with one row per layer, columns: 层 / 写入者 / 智能体可
   否直接检索 / 变更成本. The six layers, matching `README.md:48-51`: 日志（观测）、短期记忆
   （原始交互）、个人长期记忆（抽取所得）、共享长期记忆（已审核）、Knowledge Base（文档
   所有者）、Skills（Git 评审）. Six data rows plus one header row.
3. **冲突裁决因此变成查表** — Because each layer has exactly one class of writer, "which
   wins" is answered by position, not by semantic judgment at query time. Name the
   alternative explicitly: asking a model to adjudicate contradictions, which is the
   weakest link in comparable systems.
4. **检索优先级必须是全序** — A partial order leaves ties, and a tie is resolved by
   similarity score, which measures topical relevance and not authority or recency. State
   the precedence from `README.md:52-54`: 实时数据 > Skills > 权威文档 > 已审团队记忆 >
   个人偏好, and that preferences may affect presentation only.
5. **共享层是知识资产的预备区** — The shared tier's purpose is to be a staging area with
   less friction than a document review and more governance than a vector store, from which
   stable knowledge is promoted upward. Say plainly that promotion is manual and that a
   staging area whose contents never graduate has failed.
6. **这套分层不承诺什么** — The honest boundary. It does not improve answer quality, is not
   measured against QA accuracy, and does not deduplicate. Its objective function is blast
   radius, attributability, and revocability. This mirrors the line held in
   `docs/design-rationale.md` section 5 — do not break it.

Constraints: no AWS service names, no API names, no IAM strings, no `bedrock-agentcore`
anywhere in this file. Cross-link with `[[]]`-free standard Markdown to
`设计取舍依据.md` and `架构设计.md` only — both are siblings in `docs/`, so relative links
are bare filenames. Add no external URLs; that keeps the pair URL-symmetric.

- [ ] **Step 2: Write the English translation**

Create `docs/why-layer-by-write-authority.md` with the same seven headings at the same
levels, the same single table with the same row count, and the same link targets translated
to `design-rationale.md` and `architecture.md`. Headings:

```markdown
# Why Layer by Write Authority

> Chinese is the primary version: **[为什么按写入权威分层.md](为什么按写入权威分层.md)**.
> This document names no platform. The argument holds on any system with layered memory.

## The problem: episodic/semantic cannot answer the only question that matters

## Six layers and who writes them

## Conflict resolution becomes a table lookup

## Retrieval precedence must be a total order

## The shared tier is a staging area for knowledge assets

## What this layering does not promise
```

- [ ] **Step 3: Register the pair in the checker**

In `scripts/check_doc_alignment.py`, add to `PAIRS` immediately after the
`docs/桌面客户端集成设计.md` entry:

```python
    ("docs/为什么按写入权威分层.md", "docs/why-layer-by-write-authority.md"),
```

- [ ] **Step 4: Register the pair in CLAUDE.md**

In `CLAUDE.md`, add this row to the "Current pairs" table immediately after the
`docs/桌面客户端集成设计.md` row:

```markdown
| `docs/为什么按写入权威分层.md` | `docs/why-layer-by-write-authority.md` |
```

- [ ] **Step 5: Add the document to both README index tables**

In `README.md`, add this row to the document index table (the one whose header is
`| 中文（主） | English | 内容 |`), immediately after the `设计取舍依据` row:

```markdown
| [为什么按写入权威分层](docs/为什么按写入权威分层.md) | [why-layer-by-write-authority](docs/why-layer-by-write-authority.md) | 不依赖任何平台的分层论证与承重边界 |
```

In `README.en.md`, add the matching row at the same position in its index table:

```markdown
| [为什么按写入权威分层](docs/为什么按写入权威分层.md) | [why-layer-by-write-authority](docs/why-layer-by-write-authority.md) | The layering argument and its load-bearing limits, with no platform dependency |
```

Both tables gain exactly one row, so the pair stays balanced.

- [ ] **Step 6: Verify the checker accepts the new pair**

```bash
python3 scripts/check_doc_alignment.py
```

Expected: a new line `ok       docs/为什么按写入权威分层.md <-> docs/why-layer-by-write-authority.md`,
`ok` for `README.md <-> README.en.md`, and a final `all N pairs aligned` where N grew by one.
If you see `UNPAIRED docs/...`, Step 3 was skipped. If you see `heading structure differs`,
compare the two heading lists — they must match in count and level.

- [ ] **Step 7: Commit**

```bash
git add docs/为什么按写入权威分层.md docs/why-layer-by-write-authority.md \
        scripts/check_doc_alignment.py CLAUDE.md README.md README.en.md
git commit -m "$(cat <<'EOF'
Extract the layering argument from the platform it runs on

Layering by write authority is the most portable idea here and was only
readable as an AgentCore feature. Stated without a platform, someone who will
never deploy this stack can still cite or refute it.
EOF
)"
```

---

## Task 7b: Rewrite the README positioning statement

The strongest idea in the repository is not in the strongest position. The README opens by
describing what the system does; the review argues it should open with why the problem
exists. Do this after Task 7, so the opening can link to the portable argument.

**Files:**
- Modify: `README.md:5-9` (the opening paragraph, before `## 企业治理入口`)
- Modify: `README.en.md:5-13` (the matching opening)
- Modify: `README.md` (the `## 核心特点` lead-in paragraph)
- Modify: `README.en.md` (the `## What Is Distinctive` lead-in paragraph)

- [ ] **Step 1: Replace the Chinese opening paragraph**

In `README.md`, replace:

```markdown
多用户共用一个智能体（agent）时，个人记忆严格隔离，而有价值的经验经人工审核后成为团队
共享知识。基于 Amazon Bedrock AgentCore Memory 的 AWS 参考实现。
```

with:

```markdown
多用户共用一个智能体（agent）时，个人记忆严格隔离，而有价值的经验经人工审核后成为团队
共享知识。基于 Amazon Bedrock AgentCore Memory 的 AWS 参考实现。

企业里稀缺的不是记忆存储，是让经验被写下来的那一刻。Knowledge Base 与 Skills 的困难从来
不在存储或检索，而在于**没有自然的写入触发点** —— 所以本项目治理的是共享记忆的**写入
边界**：结构化提案 → 策略闸门 → 人工审核 → 逐字入库 → 可归因、可撤销。KB 与 Skills 不是
它的竞品，是它的下游。

> **承重边界：记忆治理是记忆域内的承重，不是整个智能体生态的承重。** 智能体效果由观测 →
> 评估 → 优化闭环负责，记忆治理是那个闭环的输入之一。治理的目标函数是爆炸半径、可归因性
> 与可撤销性，不是单次问答的正确性 —— 本项目不声称治理提升回答质量。
```

- [ ] **Step 2: Mirror it in English**

In `README.en.md`, immediately after the opening paragraph that ends
`implementation on Amazon Bedrock AgentCore Memory.`, insert:

```markdown
What is scarce in an enterprise is not memory storage but the moment an experience gets
written down. The difficulty with a Knowledge Base or a Skills directory was never storage
or retrieval — it is that **nothing naturally triggers the write**. So what this project
governs is the shared tier's **write boundary**: structured proposal → policy gate → human
review → verbatim storage → attributable and revocable. A Knowledge Base and Skills are not
its competitors; they are downstream of it.

> **Load-bearing limit: memory governance is load-bearing within the memory domain, not
> across the whole agent stack.** Agent effectiveness belongs to an observe → evaluate →
> optimize loop, and governed memory is one input to that loop. Governance optimizes blast
> radius, attributability, and revocability, not single-answer correctness — this project
> makes no claim that governance improves answer quality.
```

Both sides gain one paragraph and one block quote, and neither adds a heading, table row,
code fence, or URL.

- [ ] **Step 3: Add the three core judgments to the Chinese lead-in**

In `README.md`, replace the `## 核心特点` lead-in:

```markdown
记忆是**带权威等级的受治理资产**，不是一个更聪明的向量库。四条设计判断，依据与反向证据
见[设计取舍依据](docs/设计取舍依据.md)：
```

with:

```markdown
记忆是**带权威等级的受治理资产**，不是一个更聪明的向量库。三句概括，不依赖任何平台
（完整论证见[为什么按写入权威分层](docs/为什么按写入权威分层.md)）：知识分层按**「谁有权
改」**而非按 episodic/semantic 划分，冲突裁决因此从语义判断变成查表；检索优先级是**全序**
且随上下文交给模型，把"哪些记忆相关"（无解）换成"哪种权威胜出"（有解）；共享层是**知识
资产的预备区**，比向量库有治理、比写文档摩擦小，稳定后向上晋升。

下列四条设计判断给出实现层的取舍，依据与反向证据见[设计取舍依据](docs/设计取舍依据.md)：
```

- [ ] **Step 4: Mirror the lead-in in English**

In `README.en.md`, replace:

```markdown
Memory is a **governed asset with an authority level**, not a smarter vector store.
Four design judgments; reasoning and counter-evidence in
[design rationale](docs/design-rationale.md):
```

with:

```markdown
Memory is a **governed asset with an authority level**, not a smarter vector store. Three
sentences, none of which depend on a platform (full argument in
[why-layer-by-write-authority](docs/why-layer-by-write-authority.md)): layers are divided by
**who is entitled to change them** rather than by episodic/semantic, which turns conflict
resolution from a semantic judgment into a table lookup; retrieval precedence is a **total
order** carried into the context, replacing "which memories are relevant" (no answer) with
"which authority wins" (one answer); and the shared tier is a **staging area for knowledge
assets** — more governed than a vector store, less friction than authoring a document, and
promoted upward once stable.

The four design judgments below record the implementation trade-offs; reasoning and
counter-evidence in [design rationale](docs/design-rationale.md):
```

- [ ] **Step 5: Verify alignment**

```bash
python3 scripts/check_doc_alignment.py
```

Expected: `ok       README.md <-> README.en.md`. A `doc_links` failure means Task 7 has not
run yet — the new paragraphs link to `docs/为什么按写入权威分层.md` and
`docs/why-layer-by-write-authority.md`, and the checker verifies link targets exist.

- [ ] **Step 6: Commit**

```bash
git add README.md README.en.md
git commit -m "$(cat <<'EOF'
Lead with why the problem exists, not what the system does

The capture argument is the load-bearing idea and it was buried. This also
states the load-bearing limit up front, so a reader does not have to reach the
last section to learn that governance makes no answer-quality claim.
EOF
)"
```

---

## Task 8: Verify the two external claims the limitations section needs

Do this before Task 9 touches the README. Task 9 needs to know which of two variants to
write, and that depends on whether these sources check out.

**Files:** none — this task produces a verified note you carry into Task 9.

- [ ] **Step 1: Fetch the GovMem claim**

Fetch `https://arxiv.org/abs/2607.02579`. Confirm all four of:

- the paper concerns governance or gating of agent memory promotion,
- an external evaluation set of ~133 high-impact coding-agent candidates,
- a human adjudication finding that none are safe for automatic promotion,
- an internal false-promotion reduction from ~0.371 to ~0.032.

- [ ] **Step 2: Fetch the reviewer-habituation claim**

Fetch `https://arxiv.org/abs/2606.22721`. Confirm all four of:

- the study covers repeated human review of AI-agent pull requests,
- approval rate rising from ~30.1% to ~36.8%,
- a within-reviewer increase of ~14.5 percentage points across experience quantiles,
- inline comments falling ~22%.

- [ ] **Step 3: Decide which variant Task 9 writes**

Record one of these outcomes explicitly before continuing:

- **Both verified** → Task 9 Step 2 writes variant A (three bullets, two cited).
- **Either fails to verify, or a fetch fails** → Task 9 Step 2 writes **variant B**, which
  cites neither paper and instead states the reviewer-load risk without a number. Do not
  substitute a different paper you found instead; an unverified citation is the exact
  failure mode `CLAUDE.md` records three prior instances of.

- [ ] **Step 4: Confirm the third claim from this repository's own evidence**

The duplicate-record finding needs no external source. Verify it locally:

```bash
grep -n "0.6626" docs/实验报告.md
```

Expected: two lines, one for `mem-5f417b6c-...` and one for `mem-d9d4444b-...`, both with
score `0.6626`, the second annotated as produced by a previous run. This is measured
evidence in this repository and is citable as-is.

---

## Task 9: Move the limitations section forward and add three items

The limitations section is last in the README. The positioning review argues honesty is a
primary differentiator, which means it should be read, not found.

**Files:**
- Modify: `README.md` (move `## 适用范围与限制` to directly after the `## 核心特点` section)
- Modify: `README.en.md` (move `## Scope and Limitations` to directly after
  `## What Is Distinctive`)

- [ ] **Step 1: Move the section in both files**

In `README.md`, cut the entire `## 适用范围与限制` section — from the heading through the
final paragraph ending `[下一步演进](docs/下一步演进.md)。` — and paste it immediately before
`## 与业内产品的关系`.

In `README.en.md`, cut `## Scope and Limitations` through the paragraph ending
`[roadmap](docs/roadmap.md).` and paste it immediately before `## Against the Field`.

Both files must end up with the same heading order, since the checker compares heading level
sequences positionally.

- [ ] **Step 2: Add three bullets — variant A (only if Task 8 verified both sources)**

Append these three bullets to the Chinese list, after the
`**已验证的是治理属性，未测量回答质量。**` bullet:

```markdown
- **闸门管不了去重。** 实验中共享层 4 条记录里有 2 条是同一句话，相关度分数同为 0.6626
  （[实验报告](docs/实验报告.md)检查 13）。闸门判断"够不够格"，天然不判断"是不是已经有了"，
  而共享层的全部价值来自信噪比。
- **够格的团队知识可能极其稀少。** 一项针对记忆晋升闸门的研究报告称，闸门把内部 false
  promotion 从 0.371 降到 0.032，但在 133 条外部高影响力候选上，人工裁决认为**没有一条**
  适合自动晋升（[arXiv:2607.02579](https://arxiv.org/abs/2607.02579)）。若如此，审核队列
  长期为空可能不是链路故障，而是真实产出率。
- **审核者会疲劳，且疲劳是有方向的。** 一项覆盖 400 名重复审核者、11,429 次 AI 智能体 PR
  审核的研究报告称，批准率从 30.1% 升至 36.8%，同一审核者跨经验分位上升 14.5 个百分点，
  同时行内评论减少 22%（[arXiv:2606.22721](https://arxiv.org/abs/2606.22721)）。人工闸门
  的有效性随使用而衰减，本项目未测量这一衰减。
```

Append the English mirrors, after the
`**Governance properties are validated; answer quality is not measured.**` bullet:

```markdown
- **The gate cannot deduplicate.** Two of the four shared records in the experiment are the
  same sentence, scoring an identical 0.6626 ([实验报告](docs/实验报告.md) check 13). A gate
  judges whether a statement qualifies; it does not judge whether the tier already holds it,
  and the shared tier's entire value is its signal-to-noise ratio.
- **Team knowledge that qualifies may be extremely rare.** A study of memory promotion gates
  reports internal false promotion falling from 0.371 to 0.032, yet across 133 external
  high-impact candidates human adjudication found **none** safe for automatic promotion
  ([arXiv:2607.02579](https://arxiv.org/abs/2607.02579)). If that holds, a persistently
  empty review queue may be the real production rate rather than a broken path.
- **Reviewers habituate, and the drift has a direction.** A study of 400 repeat reviewers
  across 11,429 AI-agent pull request reviews reports approval rates rising from 30.1% to
  36.8%, a 14.5 percentage point increase within the same reviewer across experience
  quantiles, alongside 22% fewer inline comments
  ([arXiv:2606.22721](https://arxiv.org/abs/2606.22721)). A human gate's effectiveness
  decays with use, and this project does not measure that decay.
```

Both URLs appear on both sides, which keeps the URL sets equal.

- [ ] **Step 3: Add three bullets — variant B (only if Task 8 failed to verify)**

Use the first bullet from Step 2 verbatim in both languages — it is sourced from this
repository. Replace the two cited bullets with these uncited ones.

Chinese:

```markdown
- **审核队列的真实产出率未知。** 本仓库尚未积累足够的候选项来判断"够格的团队知识"有多稀少。
  若产出率很低，审核队列长期为空可能不是链路故障，而是常态 —— 而本项目目前无法区分这两者。
- **人工闸门的疲劳未被测量。** 审核注意力是有限资源，而本项目对审核者随时间放松的程度
  没有任何埋点。以人工审核为唯一入口的设计，其有效性依赖于这一点，因此这是承重的未知项。
```

English:

```markdown
- **The review queue's real production rate is unknown.** This repository has not
  accumulated enough candidates to tell how rare qualifying team knowledge is. If the rate
  is low, a persistently empty queue may be normal rather than a broken path — and this
  project cannot currently tell those apart.
- **Reviewer fatigue is not measured.** Review attention is a finite resource, and nothing
  here instruments how much a reviewer relaxes over time. A design whose only entrance is
  human review depends on that, which makes it a load-bearing unknown.
```

- [ ] **Step 4: Verify alignment**

```bash
python3 scripts/check_doc_alignment.py
```

Expected: `ok       README.md <-> README.en.md`. A `URLs only in README.en.md` failure means
one variant-A citation reached only one side.

- [ ] **Step 5: Commit**

```bash
git add README.md README.en.md
git commit -m "$(cat <<'EOF'
Put the limitations where they get read, and add three

Honesty about boundaries is a primary differentiator here, and it was the last
section in the file. The gate cannot deduplicate — two of four shared records in
the experiment are the same sentence — and neither the queue's real production
rate nor reviewer fatigue is measured.
EOF
)"
```

---

## Task 10: Emit shared-retrieval metrics from the context builder

Nothing currently records whether shared memory was used. Without a hit rate, there is no
way to tell whether the shared tier repays its governance cost. Query text may be sensitive,
so the fingerprint is a set of per-token hashes: enough to compute overlap between queries,
not enough to reconstruct one.

**Files:**
- Modify: `src/agent/context_builder.py`
- Test: `tests/test_retrieval_metrics.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_retrieval_metrics.py`:

```python
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent.context_builder import RetrievalMetrics, fingerprint_query  # noqa: E402


class FingerprintQueryTests(unittest.TestCase):
    def test_is_order_and_case_insensitive(self) -> None:
        self.assertEqual(
            fingerprint_query("How is Revenue calculated?"),
            fingerprint_query("calculated revenue how IS"),
        )

    def test_drops_short_tokens(self) -> None:
        self.assertEqual(
            fingerprint_query("revenue"),
            fingerprint_query("is revenue"),
        )

    def test_does_not_contain_the_original_words(self) -> None:
        fingerprint = fingerprint_query("quarterly revenue")
        self.assertNotIn("revenue", fingerprint)
        self.assertNotIn("quarterly", fingerprint)

    def test_different_queries_differ(self) -> None:
        self.assertNotEqual(
            fingerprint_query("revenue definition"),
            fingerprint_query("churn definition"),
        )


class RetrievalMetricsTests(unittest.TestCase):
    def test_reports_a_hit_with_the_top_score(self) -> None:
        metrics = RetrievalMetrics.from_records(
            query="How is revenue calculated?",
            records=[{"score": 0.42}, {"score": 0.91}],
        )
        record = metrics.as_log_record()
        self.assertEqual(record["metric"], "shared_memory_retrieval")
        self.assertTrue(record["shared_hit"])
        self.assertEqual(record["shared_candidates"], 2)
        self.assertEqual(record["shared_top_score"], 0.91)

    def test_reports_a_miss_without_a_score(self) -> None:
        metrics = RetrievalMetrics.from_records(query="anything", records=[])
        record = metrics.as_log_record()
        self.assertFalse(record["shared_hit"])
        self.assertEqual(record["shared_candidates"], 0)
        self.assertIsNone(record["shared_top_score"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m unittest tests.test_retrieval_metrics -v
```

Expected: FAIL with `ImportError: cannot import name 'RetrievalMetrics'`.

- [ ] **Step 3: Implement the metrics**

In `src/agent/context_builder.py`, add `hashlib`, `json`, and `re` to the imports at the top,
then insert this after the `ContextBundle` class definition:

```python
def fingerprint_query(query: str) -> list[str]:
    """Per-token hashes: enough to measure overlap between two queries, not enough to
    reconstruct either. A query can contain the thing the memory tier exists to protect."""
    tokens = {
        token
        for token in re.findall(r"[a-z0-9]+", query.lower())
        if len(token) > 2
    }
    return sorted(
        hashlib.sha256(token.encode("utf-8")).hexdigest()[:12] for token in tokens
    )


@dataclass(frozen=True)
class RetrievalMetrics:
    query_fingerprint: list[str]
    shared_candidates: int
    shared_top_score: float | None

    @classmethod
    def from_records(
        cls,
        *,
        query: str,
        records: list[dict[str, Any]],
    ) -> "RetrievalMetrics":
        scores = [
            record["score"] for record in records if record.get("score") is not None
        ]
        return cls(
            query_fingerprint=fingerprint_query(query),
            shared_candidates=len(records),
            shared_top_score=max(scores) if scores else None,
        )

    def as_log_record(self) -> dict[str, Any]:
        return {
            "metric": "shared_memory_retrieval",
            "query_fingerprint": self.query_fingerprint,
            "shared_candidates": self.shared_candidates,
            "shared_hit": self.shared_candidates > 0,
            "shared_top_score": self.shared_top_score,
        }
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m unittest tests.test_retrieval_metrics -v
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Emit the metric from `build`**

In `src/agent/context_builder.py`, in `ContextBuilder.build`, replace the final `return`:

```python
        return ContextBundle(
            authoritative_documents=documents,
            shared_project_memory=shared,
            personal_preferences=preferences,
        )
```

with:

```python
        LOGGER.info(
            json.dumps(
                RetrievalMetrics.from_records(query=query, records=shared).as_log_record()
            )
        )
        return ContextBundle(
            authoritative_documents=documents,
            shared_project_memory=shared,
            personal_preferences=preferences,
        )
```

`ContextBundle`'s shape is unchanged, so `tests/test_context_builder.py` and every caller
keep working.

- [ ] **Step 6: Run the whole suite**

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS, with `test_context_builder` still green.

- [ ] **Step 7: Commit**

```bash
git add src/agent/context_builder.py tests/test_retrieval_metrics.py
git commit -m "$(cat <<'EOF'
Record whether the shared tier was actually used

Nothing measured whether governed memory is ever retrieved, so there was no way
to tell whether the tier repays its cost. Queries are fingerprinted per token
rather than logged, because a query can contain what the tier exists to protect.
EOF
)"
```

---

## Task 11: Add the offline analyzer for hit rate and query overlap

The per-turn log lines answer nothing on their own. Hit rate and repeat-question rate are
aggregate.

**Files:**
- Create: `poc/analyze_retrieval_metrics.py`
- Test: `tests/test_analyze_retrieval_metrics.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_analyze_retrieval_metrics.py`:

```python
import pathlib
import sys
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "poc"))

from analyze_retrieval_metrics import summarize  # noqa: E402


class SummarizeTests(unittest.TestCase):
    def test_reports_hit_rate(self) -> None:
        summary = summarize(
            [
                {"shared_hit": True, "query_fingerprint": ["aaa"]},
                {"shared_hit": False, "query_fingerprint": ["bbb"]},
                {"shared_hit": True, "query_fingerprint": ["ccc"]},
                {"shared_hit": False, "query_fingerprint": ["ddd"]},
            ]
        )
        self.assertEqual(summary["retrievals"], 4)
        self.assertEqual(summary["shared_hit_rate"], 0.5)

    def test_identical_queries_are_fully_overlapping_repeats(self) -> None:
        summary = summarize(
            [
                {"shared_hit": True, "query_fingerprint": ["aaa", "bbb"]},
                {"shared_hit": True, "query_fingerprint": ["bbb", "aaa"]},
            ]
        )
        self.assertEqual(summary["mean_pairwise_overlap"], 1.0)
        self.assertEqual(summary["repeat_query_rate"], 1.0)

    def test_disjoint_queries_do_not_overlap(self) -> None:
        summary = summarize(
            [
                {"shared_hit": True, "query_fingerprint": ["aaa"]},
                {"shared_hit": True, "query_fingerprint": ["bbb"]},
            ]
        )
        self.assertEqual(summary["mean_pairwise_overlap"], 0.0)
        self.assertEqual(summary["repeat_query_rate"], 0.0)

    def test_half_overlap_is_not_counted_as_a_repeat(self) -> None:
        summary = summarize(
            [
                {"shared_hit": True, "query_fingerprint": ["aaa", "bbb"]},
                {"shared_hit": True, "query_fingerprint": ["bbb", "ccc"]},
            ]
        )
        self.assertAlmostEqual(summary["mean_pairwise_overlap"], 1 / 3)
        self.assertEqual(summary["repeat_query_rate"], 0.0)

    def test_a_single_retrieval_has_no_pairs(self) -> None:
        summary = summarize([{"shared_hit": True, "query_fingerprint": ["aaa"]}])
        self.assertIsNone(summary["mean_pairwise_overlap"])
        self.assertIsNone(summary["repeat_query_rate"])

    def test_no_retrievals_is_not_a_crash(self) -> None:
        summary = summarize([])
        self.assertEqual(summary["retrievals"], 0)
        self.assertIsNone(summary["shared_hit_rate"])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test to verify it fails**

```bash
python3 -m unittest tests.test_analyze_retrieval_metrics -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'analyze_retrieval_metrics'`.

- [ ] **Step 3: Implement the analyzer**

Create `poc/analyze_retrieval_metrics.py`:

```python
#!/usr/bin/env python3
"""Aggregate shared_memory_retrieval log records into a hit rate and a repeat rate.

Two numbers decide whether a governed shared tier repays its cost. The hit rate says
whether approved memory is retrieved at all. The repeat rate says whether the same
question keeps being asked, which is what makes writing an answer down worth the
review it costs. Both are aggregate, so neither is visible in a single turn.

Usage: python3 poc/analyze_retrieval_metrics.py <log-file> [<log-file> ...]

Input is JSON Lines. Lines that are not shared_memory_retrieval records are ignored, so
a raw CloudWatch export can be passed without pre-filtering.
"""

from __future__ import annotations

import json
import pathlib
import sys
from itertools import combinations
from typing import Any


REPEAT_THRESHOLD = 0.5


def load_records(paths: list[pathlib.Path]) -> list[dict[str, Any]]:
    records = []
    for path in paths:
        for line in path.read_text().splitlines():
            start = line.find("{")
            if start < 0:
                continue
            try:
                candidate = json.loads(line[start:])
            except json.JSONDecodeError:
                continue
            if candidate.get("metric") == "shared_memory_retrieval":
                records.append(candidate)
    return records


def jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    if not union:
        return 0.0
    return len(left & right) / len(union)


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    if not total:
        return {
            "retrievals": 0,
            "shared_hit_rate": None,
            "mean_pairwise_overlap": None,
            "repeat_query_rate": None,
        }

    hits = sum(1 for record in records if record.get("shared_hit"))
    fingerprints = [set(record.get("query_fingerprint", [])) for record in records]
    pairs = [jaccard(a, b) for a, b in combinations(fingerprints, 2)]

    return {
        "retrievals": total,
        "shared_hit_rate": hits / total,
        "mean_pairwise_overlap": sum(pairs) / len(pairs) if pairs else None,
        "repeat_query_rate": (
            sum(1 for value in pairs if value >= REPEAT_THRESHOLD) / len(pairs)
            if pairs
            else None
        ),
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    paths = [pathlib.Path(argument) for argument in argv[1:]]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        print(f"no such file: {missing}")
        return 2
    print(json.dumps(summarize(load_records(paths)), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
```

- [ ] **Step 4: Run the test to verify it passes**

```bash
python3 -m unittest tests.test_analyze_retrieval_metrics -v
```

Expected: PASS, 6 tests.

- [ ] **Step 5: Verify the script end to end**

```bash
cd /Users/yabolin/claude-code/agentcore-memory-blueprint
python3 - <<'PY'
import pathlib
lines = [
    '{"metric":"shared_memory_retrieval","query_fingerprint":["aaa","bbb"],"shared_candidates":2,"shared_hit":true,"shared_top_score":0.9}',
    'INFO 2026-08-18 {"metric":"shared_memory_retrieval","query_fingerprint":["bbb","aaa"],"shared_candidates":0,"shared_hit":false,"shared_top_score":null}',
    'unrelated log line',
]
pathlib.Path("/tmp/retrieval.jsonl").write_text("\n".join(lines) + "\n")
PY
python3 poc/analyze_retrieval_metrics.py /tmp/retrieval.jsonl
```

Expected output:

```json
{
  "retrievals": 2,
  "shared_hit_rate": 0.5,
  "mean_pairwise_overlap": 1.0,
  "repeat_query_rate": 1.0
}
```

This also confirms the log-prefix tolerance and that non-matching lines are skipped.

- [ ] **Step 6: Run the whole suite and clean up**

```bash
python3 -m unittest discover -s tests -v && rm /tmp/retrieval.jsonl
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add poc/analyze_retrieval_metrics.py tests/test_analyze_retrieval_metrics.py
git commit -m "$(cat <<'EOF'
Aggregate retrieval logs into a hit rate and a repeat rate

Whether the shared tier repays its review cost depends on two aggregate
numbers: how often approved memory is retrieved, and how often the same
question recurs. Neither is visible in a single turn's log line.
EOF
)"
```

---

## Task 12: Document the instrumentation in the README pair

An analyzer nobody knows about produces no measurement.

**Files:**
- Modify: `README.md` (the "适用范围与限制" section, which Task 9 moved)
- Modify: `README.en.md` (the matching "Scope and Limitations" section)

- [ ] **Step 1: Replace the answer-quality bullet in Chinese**

In `README.md`, replace:

```markdown
- **已验证的是治理属性，未测量回答质量。**
```

with:

```markdown
- **已验证的是治理属性，未测量回答质量。** 治理的目标函数是爆炸半径、可归因性与可撤销性，
  不是单次问答的正确性。共享层是否回本由两个聚合数决定 —— 共享命中率与重复提问率 ——
  `src/agent/context_builder.py` 现在为每次检索记录一条指标，
  `poc/analyze_retrieval_metrics.py` 将其汇总；查询以逐 token 哈希留存，不落原文。
  尚未积累足够运行来给出这两个数。
```

- [ ] **Step 2: Mirror it in English**

In `README.en.md`, replace:

```markdown
- **Governance properties are validated; answer quality is not measured.**
```

with:

```markdown
- **Governance properties are validated; answer quality is not measured.** Governance
  optimizes blast radius, attributability, and revocability, not single-answer
  correctness. Whether the shared tier repays its cost turns on two aggregate numbers —
  shared hit rate and repeat-question rate — so `src/agent/context_builder.py` now logs a
  metric per retrieval and `poc/analyze_retrieval_metrics.py` aggregates them. Queries are
  retained as per-token hashes, never as text. There are not yet enough runs to report
  either number.
```

- [ ] **Step 3: Verify and commit**

```bash
python3 scripts/check_doc_alignment.py && python3 -m unittest discover -s tests -q
```

Expected: `all N pairs aligned` and an OK test summary.

```bash
git add README.md README.en.md
git commit -m "$(cat <<'EOF'
Say which two numbers decide whether the shared tier repays its cost

The instrumentation exists now, and an analyzer nobody knows about measures
nothing. This also states plainly that neither number has enough runs yet.
EOF
)"
```

---

## Task 13: Final verification

- [ ] **Step 1: Run every check the repository has**

```bash
cd /Users/yabolin/claude-code/agentcore-memory-blueprint
python3 scripts/check_doc_alignment.py
python3 -m unittest discover -s tests -v
cd infra && npm run build && npm test && npx cdk synth > /dev/null
```

Expected: `all N pairs aligned`; Python suite OK; Jest all green; `cdk synth` exits 0.

- [ ] **Step 2: Confirm no stale expiry claim survives**

```bash
cd /Users/yabolin/claude-code/agentcore-memory-blueprint
grep -rn "资源过期\|resource expiry\|90-day resource" README.md README.en.md docs/*.md
```

Expected: no hit that asserts records expire with the resource. Hits that *deny* the
backstop, or that describe `eventExpiryDuration` applying to events, are correct — read each
one rather than assuming.

- [ ] **Step 3: Confirm the promotion event has a subscriber**

```bash
grep -n "memory.promotion.proposed" infra/lib/memory-governance-stack.ts src/handlers/mark_status.py
```

Expected: one hit in each file — the emitter in the handler and the rule in the stack.

- [ ] **Step 4: Confirm the new document names no platform**

```bash
grep -in "agentcore\|bedrock\|aws\|lambda\|dynamodb" docs/为什么按写入权威分层.md docs/why-layer-by-write-authority.md
```

Expected: no output. Any hit means the document is not portable and Task 7's constraint was
violated.

- [ ] **Step 5: Review the full diff before reporting completion**

```bash
git log --oneline master..HEAD
git diff master...HEAD --stat
```

Confirm every commit corresponds to a task above and that no unrelated file was swept in —
in particular, the pre-existing uncommitted enterprise-governance work must remain
uncommitted unless the user asked otherwise.

---

## Deliberately out of scope

Recorded so the next reader knows these were decided, not missed:

- **Implementing supersession.** Task 2 declares the indexed key it needs; the workflow
  branch, the `supersedes` candidate field, and the `BatchUpdateMemoryRecords` path stay in
  `docs/roadmap.md` item 4. Declaring the key is time-sensitive because indexed keys are
  immutable; implementing the mechanism is not.
- **Building the capture hook.** Task 6 raises it to a precondition in the roadmap. Writing
  it means designing a hook contract in `.mcp.json` and the desktop bridge, which is its own
  plan.
- **Deduplication at the gate.** Task 9 documents the gap with measured evidence from this
  repository. Closing it requires a similarity check against the existing shared tier at
  proposal time — a design decision, not an edit.
- **Replacing the repository's one-line subtitle.** Task 7b rewrites the opening framing and
  the core-judgments lead-in, but leaves the first sentence — the description of what the
  system does — in place. A reader arriving from a link needs to learn what this is before
  they are told why it matters.
