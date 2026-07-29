# Security Notes

> Translation. The primary document is [SECURITY.md](SECURITY.md) (Chinese).

## Data Handling

- Shared Memory receives only approved, sanitized statements.
- Task tokens are encrypted in DynamoDB and never placed in notifications or logs.
- Step Functions execution data logging is disabled.
- AgentCore event and record metadata contain classification and linkage identifiers
  only. Raw evidence, personal data, and secrets stay out of metadata.
- The runtime must derive actor and project IDs from authenticated claims.
- Use immutable Cognito `sub` values for personal actors. Email and username are
  mutable display attributes, not durable security identifiers.
- The shared publisher and runtime read policy are restricted to the exact project
  namespace. A multi-user server-side runtime still needs application authorization
  for personal actors; use Cognito federated temporary credentials when IAM-bound
  per-user isolation is required.

## Dependency Audit

`npm audit --omit=dev` currently reports `GHSA-mh99-v99m-4gvg` in
`brace-expansion@5.0.7`, bundled inside `aws-cdk-lib@2.262.1`. npm cannot override
or automatically replace that bundled copy.

This dependency is used only while synthesizing infrastructure and is not packaged
into the Lambda assets. CDK context and project configuration must still be treated
as trusted input. Track the next `aws-cdk-lib` patch and remove this note after the
bundled dependency is updated. Do not use `npm audit fix --force`.

For reproducible CDK tooling, use Node.js 22 LTS. The blueprint was also synthesized
successfully with Node.js 24.8.0, although one CDK CLI validation dependency declares
the narrower Node 22 engine range.
