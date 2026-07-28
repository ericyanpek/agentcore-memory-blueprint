# Verified AWS References

These links were checked while building the blueprint:

- [Get started with AgentCore Memory](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-get-started.html)
- [AgentCore Memory types](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-types.html)
- [Memory organization: actor, session, namespace, and IAM](https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/memory-organization.html)
- [CreateEvent API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_CreateEvent.html)
- [RetrieveMemoryRecords API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_RetrieveMemoryRecords.html)
- [BatchCreateMemoryRecords API](https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_BatchCreateMemoryRecords.html)
- [AgentCore CDK construct library](https://docs.aws.amazon.com/cdk/api/v2/docs/aws-cdk-lib.aws_bedrockagentcore-readme.html)
- [AgentCore Memory official samples, reviewed commit](https://github.com/awslabs/agentcore-samples/tree/ff11ccbb89d391a7c2478160a1b66c63f0b63e59/01-features/04-manage-context-of-your-agent/memory)
- [Step Functions human approval tutorial](https://docs.aws.amazon.com/step-functions/latest/dg/tutorial-human-approval.html)
- [Step Functions execution details](https://docs.aws.amazon.com/step-functions/latest/dg/concepts-view-execution-details.html)
- [Amazon Bedrock Knowledge Bases](https://docs.aws.amazon.com/bedrock/latest/userguide/knowledge-base.html)

In this blueprint, "managed Knowledge Base" means Amazon Bedrock Knowledge Bases.
AgentCore Memory and Bedrock Knowledge Bases are separate services with separate
authority and lifecycle.
