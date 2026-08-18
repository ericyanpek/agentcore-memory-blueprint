import { App } from "aws-cdk-lib";
import { Match, Template } from "aws-cdk-lib/assertions";
import { MemoryGovernanceStack } from "../lib/memory-governance-stack";

describe("MemoryGovernanceStack", () => {
  const app = new App();
  const stack = new MemoryGovernanceStack(app, "TestStack", {
    projectId: "analytics-poc",
    environmentName: "test",
    reviewerOrigin: "https://review.example.com",
  });
  const template = Template.fromStack(stack);

  test("creates two isolated AgentCore memory resources", () => {
    template.resourceCountIs("AWS::BedrockAgentCore::Memory", 2);
  });

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

  test("publisher can only batch-write the project namespace", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: "bedrock-agentcore:BatchCreateMemoryRecords",
            Condition: {
              StringEquals: {
                "bedrock-agentcore:namespace":
                  "/projects/project:analytics-poc/shared/",
              },
            },
          }),
        ]),
      },
    });
  });

  test("publisher can use the customer managed memory key", () => {
    template.hasResourceProperties("AWS::IAM::Policy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Action: Match.arrayWith(["kms:Decrypt", "kms:Encrypt"]),
          }),
        ]),
      },
    });
  });

  test("packages a current AgentCore SDK layer for direct record metadata", () => {
    template.resourceCountIs("AWS::Lambda::LayerVersion", 1);
    template.hasResourceProperties("AWS::Lambda::Function", {
      FunctionName: "TestStack-PublishSharedFunction",
      Layers: Match.anyValue(),
    });
  });

  test("uses a Standard workflow with callback logging protection", () => {
    template.hasResourceProperties("AWS::StepFunctions::StateMachine", {
      StateMachineType: "STANDARD",
      LoggingConfiguration: Match.objectLike({
        IncludeExecutionData: false,
        Level: "ERROR",
      }),
    });
  });

  test("waits for callback without an unimplemented heartbeat", () => {
    const rendered = JSON.stringify(template.toJSON());
    expect(rendered).toContain("WaitForHumanReview");
    expect(rendered).toContain("waitForTaskToken");
    expect(rendered).toContain("TimeoutSeconds");
    expect(rendered).not.toContain("HeartbeatSeconds");
  });

  test("tracks the published long-term record id", () => {
    const rendered = JSON.stringify(template.toJSON());
    expect(rendered).toContain("shared_memory_record_id");
    expect(rendered).toContain("PUBLISH_FAILED");
    expect(rendered).not.toContain("shared_memory_event_id");
  });

  test("ignores duplicate EventBridge deliveries without changing status", () => {
    const rendered = JSON.stringify(template.toJSON());
    expect(rendered).toContain("workflow_execution_id");
    expect(rendered).toContain("DuplicateIgnored");
  });

  test("routes only project memory candidates", () => {
    template.hasResourceProperties("AWS::Events::Rule", {
      EventPattern: {
        source: ["demo.analytics-agent"],
        "detail-type": ["memory.candidate.proposed"],
        detail: {
          project_id: ["analytics-poc"],
          schema_version: ["1.0"],
        },
      },
    });
  });

  test("protects review methods with Cognito", () => {
    template.hasResourceProperties("AWS::ApiGateway::Method", {
      AuthorizationType: "COGNITO_USER_POOLS",
    });
  });

  test("exposes an authenticated candidate list route", () => {
    template.hasResourceProperties("AWS::ApiGateway::Method", {
      HttpMethod: "GET",
      AuthorizationType: "COGNITO_USER_POOLS",
      ResourceId: {
        Ref: Match.stringLikeRegexp("ReviewApireviews"),
      },
    });
  });

  test("exposes a Cognito-protected proposal route for desktop clients", () => {
    template.hasResourceProperties("AWS::ApiGateway::Method", {
      HttpMethod: "POST",
      AuthorizationType: "COGNITO_USER_POOLS",
      ResourceId: {
        Ref: Match.stringLikeRegexp("ReviewApiproposals"),
      },
    });
  });

  test("proposal route may publish events but cannot reach memory or candidates", () => {
    const policies = template.findResources("AWS::IAM::Policy");
    const proposalPolicy = Object.entries(policies).find(([logicalId]) =>
      logicalId.startsWith("ProposeCandidateFunctionServiceRoleDefaultPolicy"),
    );
    expect(proposalPolicy).toBeDefined();
    const rendered = JSON.stringify(proposalPolicy?.[1]);
    expect(rendered).toContain("events:PutEvents");
    expect(rendered).not.toContain("bedrock-agentcore:");
    expect(rendered).not.toContain("dynamodb:");
  });

  test("scopes the review callback grant to the review state machine", () => {
    const rendered = JSON.stringify(template.toJSON());
    expect(rendered).toContain("states:SendTaskSuccess");
    expect(rendered).not.toContain(
      '"Action":["states:SendTaskSuccess","states:SendTaskFailure"],"Effect":"Allow","Resource":"*"',
    );
  });

  test("denies deletion of evidence object versions", () => {
    template.hasResourceProperties("AWS::S3::BucketPolicy", {
      PolicyDocument: {
        Statement: Match.arrayWith([
          Match.objectLike({
            Effect: "Deny",
            Action: Match.arrayWith(["s3:DeleteObjectVersion"]),
          }),
        ]),
      },
    });
  });

  test("does not require an account-level API Gateway log role", () => {
    template.hasResourceProperties("AWS::ApiGateway::Stage", {
      MethodSettings: Match.arrayWith([
        Match.objectLike({
          LoggingLevel: "OFF",
          MetricsEnabled: false,
          DataTraceEnabled: false,
        }),
      ]),
    });
  });

  test("does not use wildcard CORS for the reviewer API", () => {
    const rendered = JSON.stringify(template.toJSON());
    expect(rendered).toContain("https://review.example.com");
    expect(rendered).not.toContain(
      "method.response.header.Access-Control-Allow-Origin\":\"'*'\"",
    );
  });

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
});
