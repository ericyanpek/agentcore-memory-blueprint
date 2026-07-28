import * as path from "node:path";
import {
  ArnFormat,
  CfnOutput,
  CfnResource,
  Duration,
  RemovalPolicy,
  Stack,
  StackProps,
} from "aws-cdk-lib";
import * as agentcore from "aws-cdk-lib/aws-bedrockagentcore";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as events from "aws-cdk-lib/aws-events";
import * as targets from "aws-cdk-lib/aws-events-targets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as kms from "aws-cdk-lib/aws-kms";
import * as lambda from "aws-cdk-lib/aws-lambda";
import * as logs from "aws-cdk-lib/aws-logs";
import * as apigateway from "aws-cdk-lib/aws-apigateway";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as sns from "aws-cdk-lib/aws-sns";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as sfn from "aws-cdk-lib/aws-stepfunctions";
import * as tasks from "aws-cdk-lib/aws-stepfunctions-tasks";
import { Construct } from "constructs";

export interface MemoryGovernanceStackProps extends StackProps {
  readonly projectId: string;
  readonly environmentName: string;
  readonly reviewerOrigin: string;
}

export class MemoryGovernanceStack extends Stack {
  public constructor(
    scope: Construct,
    id: string,
    props: MemoryGovernanceStackProps,
  ) {
    super(scope, id, props);

    const prefix = `${props.projectId}-${props.environmentName}`;
    const memoryKey = new kms.Key(this, "MemoryKey", {
      alias: `alias/${prefix}-agentcore-memory`,
      enableKeyRotation: true,
      description: "Encrypts AgentCore personal and project memory",
      removalPolicy: RemovalPolicy.RETAIN,
    });
    const currentSdkLayer = new lambda.LayerVersion(this, "CurrentSdkLayer", {
      code: lambda.Code.fromAsset(path.join(__dirname, "../layer")),
      compatibleArchitectures: [lambda.Architecture.ARM_64],
      compatibleRuntimes: [lambda.Runtime.PYTHON_3_12],
      description:
        "Pinned boto3 service model for AgentCore long-term record metadata",
    });

    const personalMemory = new agentcore.Memory(this, "PersonalMemory", {
      memoryName: this.memoryName(prefix, "personal"),
      description: "Per-user conversations, summaries, and preferences",
      expirationDuration: Duration.days(30),
      kmsKey: memoryKey,
      memoryStrategies: [
        agentcore.MemoryStrategy.usingUserPreference({
          strategyName: "PersonalPreferences",
          namespaces: ["/users/{actorId}/preferences/"],
        }),
        agentcore.MemoryStrategy.usingSummarization({
          strategyName: "PersonalSessionSummary",
          namespaces: ["/users/{actorId}/sessions/{sessionId}/summary/"],
        }),
      ],
    });
    (personalMemory.node.findChild("Memory") as CfnResource).applyRemovalPolicy(
      RemovalPolicy.RETAIN,
    );

    const sharedMemory = new agentcore.Memory(this, "SharedProjectMemory", {
      memoryName: this.memoryName(prefix, "shared"),
      description: "Directly written, reviewed project experience only",
      expirationDuration: Duration.days(90),
      kmsKey: memoryKey,
    });
    const sharedMemoryResource = sharedMemory.node.findChild(
      "Memory",
    ) as agentcore.CfnMemory;
    sharedMemoryResource.indexedKeys = [
      { key: "project_id", type: "STRING" },
      { key: "category", type: "STRING" },
      { key: "review_status", type: "STRING" },
      { key: "promotion_hint", type: "STRING" },
    ];
    sharedMemoryResource.applyRemovalPolicy(RemovalPolicy.RETAIN);

    const eventBus = new events.EventBus(this, "ProjectEventBus", {
      eventBusName: this.resourceName(prefix, "events"),
    });
    eventBus.applyRemovalPolicy(RemovalPolicy.DESTROY);

    // Evidence for a shared-memory claim must outlive and out-trust the client
    // that produced it. Desktop agents may add objects but hold no permission to
    // overwrite or delete them, and versioning plus a retention lock means an
    // approved statement can always be traced back to what was actually said.
    const evidenceBucket = new s3.Bucket(this, "EvidenceBucket", {
      bucketName: `${prefix}-memory-evidence-${this.account}`,
      encryption: s3.BucketEncryption.KMS,
      encryptionKey: memoryKey,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
      enforceSSL: true,
      versioned: true,
      objectOwnership: s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
      lifecycleRules: [{ expiration: Duration.days(365) }],
      removalPolicy: RemovalPolicy.RETAIN,
    });
    // A bucket policy cannot stop an author from re-PUTting their own key, and S3
    // then serves the newer version to anyone following a bare s3://bucket/key
    // reference. Immutability therefore comes from two things together: this DENY
    // on version deletion, and an `evidence_ref` that pins a specific versionId
    // (see bridge/server.py memory_capture_evidence).
    evidenceBucket.addToResourcePolicy(
      new iam.PolicyStatement({
        sid: "EvidenceVersionsAreImmutable",
        effect: iam.Effect.DENY,
        // Excludes the account itself so lifecycle pruning and break-glass
        // recovery stay possible; a blanket AnyPrincipal deny locks out root.
        notPrincipals: [new iam.AccountRootPrincipal()],
        actions: [
          "s3:DeleteObject",
          "s3:DeleteObjectVersion",
          "s3:PutObjectAcl",
        ],
        resources: [evidenceBucket.arnForObjects("*")],
      }),
    );
    new CfnOutput(this, "EvidenceBucketName", {
      value: evidenceBucket.bucketName,
    });

    const candidateTable = new dynamodb.Table(this, "CandidateTable", {
      tableName: this.resourceName(prefix, "memory-candidates"),
      partitionKey: {
        name: "candidate_id",
        type: dynamodb.AttributeType.STRING,
      },
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: memoryKey,
      pointInTimeRecoverySpecification: {
        pointInTimeRecoveryEnabled: true,
      },
      removalPolicy: RemovalPolicy.RETAIN,
    });

    const callbackTable = new dynamodb.Table(this, "CallbackTable", {
      tableName: this.resourceName(prefix, "review-callbacks"),
      partitionKey: {
        name: "candidate_id",
        type: dynamodb.AttributeType.STRING,
      },
      timeToLiveAttribute: "expires_at_epoch",
      billingMode: dynamodb.BillingMode.PAY_PER_REQUEST,
      encryption: dynamodb.TableEncryption.CUSTOMER_MANAGED,
      encryptionKey: memoryKey,
      removalPolicy: RemovalPolicy.DESTROY,
    });

    const reviewTopic = new sns.Topic(this, "ReviewTopic", {
      topicName: this.resourceName(prefix, "memory-review"),
      masterKey: memoryKey,
    });

    const reviewerPool = new cognito.UserPool(this, "ReviewerPool", {
      userPoolName: this.resourceName(prefix, "reviewers"),
      selfSignUpEnabled: false,
      signInAliases: { email: true },
      mfa: cognito.Mfa.OPTIONAL,
      mfaSecondFactor: { sms: false, otp: true },
      accountRecovery: cognito.AccountRecovery.EMAIL_ONLY,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    const reviewerClient = reviewerPool.addClient("ReviewerClient", {
      userPoolClientName: this.resourceName(prefix, "reviewer-client"),
      authFlows: { userPassword: true, userSrp: true },
      preventUserExistenceErrors: true,
      disableOAuth: true,
    });
    const reviewerGroupName = this.resourceName(
      "memory-reviewers",
      props.projectId,
    );
    new cognito.CfnUserPoolGroup(this, "ReviewerGroup", {
      userPoolId: reviewerPool.userPoolId,
      groupName: reviewerGroupName,
      description: "Users allowed to review shared memory candidates",
    });

    const reviewerFunction = this.pythonFunction("ReviewerFunction", {
      handler: "handlers.reviewer_api.handler",
      environment: {
        CANDIDATE_TABLE_NAME: candidateTable.tableName,
        CALLBACK_TABLE_NAME: callbackTable.tableName,
        REVIEWER_GROUP: reviewerGroupName,
        REVIEWER_ORIGIN: props.reviewerOrigin,
      },
    });
    candidateTable.grantReadData(reviewerFunction);
    callbackTable.grantReadWriteData(reviewerFunction);
    // Scoped by name rather than by `workflow.stateMachineArn`: the state machine
    // already depends on this Lambda's API URL, so referencing it here would form
    // a CloudFormation cycle. A wildcard would let a compromised reviewer resolve
    // the task token of any waitForTaskToken execution in the account.
    reviewerFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["states:SendTaskSuccess", "states:SendTaskFailure"],
        resources: [
          Stack.of(this).formatArn({
            service: "states",
            resource: "stateMachine",
            resourceName: this.resourceName(prefix, "memory-review"),
            arnFormat: ArnFormat.COLON_RESOURCE_NAME,
          }),
        ],
      }),
    );

    const reviewApi = new apigateway.RestApi(this, "ReviewApi", {
      restApiName: this.resourceName(prefix, "memory-review-api"),
      description: "Cognito-protected API for shared memory review",
      deployOptions: {
        stageName: props.environmentName,
        tracingEnabled: true,
        metricsEnabled: false,
        loggingLevel: apigateway.MethodLoggingLevel.OFF,
        dataTraceEnabled: false,
      },
      defaultCorsPreflightOptions: {
        allowOrigins: [props.reviewerOrigin],
        allowMethods: ["GET", "POST", "OPTIONS"],
        allowHeaders: ["authorization", "content-type"],
      },
    });
    const authorizer = new apigateway.CognitoUserPoolsAuthorizer(
      this,
      "ReviewerAuthorizer",
      { cognitoUserPools: [reviewerPool] },
    );
    const reviews = reviewApi.root.addResource("reviews");
    const candidate = reviews.addResource("{candidate_id}");
    const reviewerIntegration = new apigateway.LambdaIntegration(
      reviewerFunction,
    );
    reviews.addMethod("GET", reviewerIntegration, {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO,
    });
    candidate.addMethod("GET", reviewerIntegration, {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO,
    });
    candidate.addMethod("POST", reviewerIntegration, {
      authorizer,
      authorizationType: apigateway.AuthorizationType.COGNITO,
    });

    // Lets desktop coding agents propose shared knowledge without holding
    // permission to write shared memory. Proposals rejoin the same review flow.
    const proposeFunction = this.pythonFunction("ProposeCandidateFunction", {
      handler: "handlers.propose_candidate.handler",
      environment: {
        EVENT_BUS_NAME: eventBus.eventBusName,
        PROJECT_ID: props.projectId,
        REVIEWER_ORIGIN: props.reviewerOrigin,
      },
    });
    eventBus.grantPutEventsTo(proposeFunction);
    reviewApi.root
      .addResource("proposals")
      .addMethod("POST", new apigateway.LambdaIntegration(proposeFunction), {
        authorizer,
        authorizationType: apigateway.AuthorizationType.COGNITO,
      });

    const registerFunction = this.pythonFunction("RegisterCandidateFunction", {
      handler: "handlers.register_candidate.handler",
      environment: {
        CANDIDATE_TABLE_NAME: candidateTable.tableName,
      },
    });
    candidateTable.grantReadWriteData(registerFunction);

    const requestReviewFunction = this.pythonFunction(
      "RequestReviewFunction",
      {
        handler: "handlers.request_review.handler",
        environment: {
          CALLBACK_TABLE_NAME: callbackTable.tableName,
          REVIEW_TOPIC_ARN: reviewTopic.topicArn,
          REVIEW_API_URL: reviewApi.url,
        },
      },
    );
    callbackTable.grantWriteData(requestReviewFunction);
    reviewTopic.grantPublish(requestReviewFunction);

    const publishFunction = this.pythonFunction("PublishSharedFunction", {
      handler: "handlers.publish_shared.handler",
      timeout: Duration.seconds(30),
      layers: [currentSdkLayer],
      environment: {
        CANDIDATE_TABLE_NAME: candidateTable.tableName,
        SHARED_MEMORY_ID: sharedMemory.memoryId,
      },
    });
    candidateTable.grantReadData(publishFunction);
    memoryKey.grantEncryptDecrypt(publishFunction);
    publishFunction.addToRolePolicy(
      new iam.PolicyStatement({
        actions: ["bedrock-agentcore:BatchCreateMemoryRecords"],
        resources: [sharedMemory.memoryArn],
        conditions: {
          StringEquals: {
            "bedrock-agentcore:namespace":
              `/projects/project:${props.projectId}/shared/`,
          },
        },
      }),
    );

    const markFunction = this.pythonFunction("MarkStatusFunction", {
      handler: "handlers.mark_status.handler",
      environment: {
        CANDIDATE_TABLE_NAME: candidateTable.tableName,
        PROJECT_EVENT_BUS_NAME: eventBus.eventBusName,
      },
    });
    candidateTable.grantWriteData(markFunction);
    eventBus.grantPutEventsTo(markFunction);

    const workflow = this.createReviewWorkflow({
      prefix,
      registerFunction,
      requestReviewFunction,
      publishFunction,
      markFunction,
    });

    const workflowDlq = new sqs.Queue(this, "WorkflowDlq", {
      queueName: this.resourceName(prefix, "workflow-dlq"),
      encryption: sqs.QueueEncryption.KMS,
      encryptionMasterKey: memoryKey,
      retentionPeriod: Duration.days(14),
    });
    new events.Rule(this, "CandidateRule", {
      eventBus,
      ruleName: this.resourceName(prefix, "candidate-review"),
      eventPattern: {
        source: ["demo.analytics-agent"],
        detailType: ["memory.candidate.proposed"],
        detail: {
          project_id: [props.projectId],
          schema_version: ["1.0"],
        },
      },
      targets: [
        new targets.SfnStateMachine(workflow, {
          deadLetterQueue: workflowDlq,
          retryAttempts: 3,
          maxEventAge: Duration.hours(2),
        }),
      ],
    });

    const runtimePolicy = new iam.ManagedPolicy(
      this,
      "AgentRuntimeMemoryPolicy",
      {
        managedPolicyName: this.resourceName(prefix, "agent-memory-access"),
        description:
          "Attach to the analytics Runtime role; app derives user actors and the shared read is namespace-scoped",
        statements: [
          // This role serves every user, so it cannot be pinned to one actorId
          // the way the desktop-client role is; ownership is enforced in
          // application code. That trade-off is the open decision recorded in
          // docs/architecture.md. Retrieval is at least confined to user
          // namespaces so this role can never read the project's shared records
          // through the personal resource.
          new iam.PolicyStatement({
            actions: [
              "bedrock-agentcore:CreateEvent",
              "bedrock-agentcore:ListEvents",
            ],
            resources: [personalMemory.memoryArn],
          }),
          new iam.PolicyStatement({
            actions: ["bedrock-agentcore:RetrieveMemoryRecords"],
            resources: [personalMemory.memoryArn],
            conditions: {
              StringLike: { "bedrock-agentcore:namespace": "/users/*" },
            },
          }),
          new iam.PolicyStatement({
            actions: ["bedrock-agentcore:RetrieveMemoryRecords"],
            resources: [sharedMemory.memoryArn],
            conditions: {
              StringEquals: {
                "bedrock-agentcore:namespace":
                  `/projects/project:${props.projectId}/shared/`,
              },
            },
          }),
          new iam.PolicyStatement({
            actions: ["events:PutEvents"],
            resources: [eventBus.eventBusArn],
          }),
        ],
      },
    );

    new CfnOutput(this, "PersonalMemoryId", {
      value: personalMemory.memoryId,
    });
    new CfnOutput(this, "SharedMemoryId", {
      value: sharedMemory.memoryId,
    });
    new CfnOutput(this, "ProjectEventBusName", {
      value: eventBus.eventBusName,
    });
    new CfnOutput(this, "CandidateTableName", {
      value: candidateTable.tableName,
    });
    new CfnOutput(this, "ReviewApiUrl", { value: reviewApi.url });
    new CfnOutput(this, "ReviewerUserPoolId", {
      value: reviewerPool.userPoolId,
    });
    new CfnOutput(this, "ReviewerClientId", {
      value: reviewerClient.userPoolClientId,
    });
    new CfnOutput(this, "ReviewerGroupName", {
      value: reviewerGroupName,
    });
    new CfnOutput(this, "ReviewTopicArn", {
      value: reviewTopic.topicArn,
    });
    new CfnOutput(this, "ReviewWorkflowArn", {
      value: workflow.stateMachineArn,
    });
    new CfnOutput(this, "AgentRuntimeMemoryPolicyArn", {
      value: runtimePolicy.managedPolicyArn,
    });
  }

  private createReviewWorkflow(props: {
    readonly prefix: string;
    readonly registerFunction: lambda.IFunction;
    readonly requestReviewFunction: lambda.IFunction;
    readonly publishFunction: lambda.IFunction;
    readonly markFunction: lambda.IFunction;
  }): sfn.StateMachine {
    const register = new tasks.LambdaInvoke(this, "RegisterCandidate", {
      lambdaFunction: props.registerFunction,
      payload: sfn.TaskInput.fromObject({
        event: sfn.JsonPath.entirePayload,
        workflow_execution_id: sfn.JsonPath.stringAt("$$.Execution.Id"),
      }),
      outputPath: "$.Payload",
      retryOnServiceExceptions: true,
    });

    const requestReview = new tasks.LambdaInvoke(this, "WaitForHumanReview", {
      lambdaFunction: props.requestReviewFunction,
      integrationPattern: sfn.IntegrationPattern.WAIT_FOR_TASK_TOKEN,
      payload: sfn.TaskInput.fromObject({
        candidate_id: sfn.JsonPath.stringAt("$.candidate_id"),
        project_id: sfn.JsonPath.stringAt("$.project_id"),
        task_token: sfn.JsonPath.taskToken,
      }),
      resultPath: "$.review",
      taskTimeout: sfn.Timeout.duration(Duration.days(7)),
    });

    const publish = new tasks.LambdaInvoke(this, "PublishSharedMemory", {
      lambdaFunction: props.publishFunction,
      payload: sfn.TaskInput.fromObject({
        candidate_id: sfn.JsonPath.stringAt("$.candidate_id"),
        project_id: sfn.JsonPath.stringAt("$.project_id"),
        reviewer_id: sfn.JsonPath.stringAt("$.review.reviewer_id"),
      }),
      outputPath: "$.Payload",
      retryOnServiceExceptions: true,
    });
    publish.addRetry({
      errors: [
        "TransientSharedMemoryPublishError",
        "ThrottledException",
        "ServiceException",
      ],
      interval: Duration.seconds(2),
      backoffRate: 2,
      maxAttempts: 4,
    });
    publish.addCatch(
      this.markStatusTask(
        "MarkPublishFailed",
        props.markFunction,
        "PUBLISH_FAILED",
        false,
      ),
      { resultPath: "$.publish_error" },
    );

    const markPublished = this.markStatusTask(
      "MarkPublished",
      props.markFunction,
      "PUBLISHED",
      true,
    );
    const markRejected = this.markStatusTask(
      "MarkRejected",
      props.markFunction,
      "REJECTED_REVIEW",
      true,
    );
    const markPolicyRejected = this.markStatusTask(
      "MarkPolicyRejected",
      props.markFunction,
      "REJECTED_POLICY",
      false,
    );

    const decision = new sfn.Choice(this, "Approved");
    decision.when(
      sfn.Condition.stringEquals("$.review.decision", "APPROVED"),
      publish.next(markPublished),
    );
    decision.otherwise(markRejected);

    const eligible = new sfn.Choice(this, "CandidateEligible");
    eligible.when(
      sfn.Condition.booleanEquals("$.eligible", true),
      requestReview.next(decision),
    );
    eligible.when(
      sfn.Condition.stringEquals("$.status", "REJECTED_POLICY"),
      markPolicyRejected,
    );
    eligible.otherwise(new sfn.Succeed(this, "DuplicateIgnored"));

    const definition = register.next(eligible);
    const logGroup = new logs.LogGroup(this, "WorkflowLogGroup", {
      logGroupName: `/aws/vendedlogs/states/${props.prefix}-memory-review`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    return new sfn.StateMachine(this, "ReviewWorkflow", {
      stateMachineName: this.resourceName(props.prefix, "memory-review"),
      definitionBody: sfn.DefinitionBody.fromChainable(definition),
      stateMachineType: sfn.StateMachineType.STANDARD,
      tracingEnabled: true,
      logs: {
        destination: logGroup,
        level: sfn.LogLevel.ERROR,
        includeExecutionData: false,
      },
      timeout: Duration.days(8),
    });
  }

  private markStatusTask(
    id: string,
    fn: lambda.IFunction,
    status: string,
    includeReview: boolean,
  ): tasks.LambdaInvoke {
    const payload: Record<string, unknown> = {
      candidate_id: sfn.JsonPath.stringAt("$.candidate_id"),
      project_id: sfn.JsonPath.stringAt("$.project_id"),
      target_status: status,
    };
    if (includeReview) {
      payload.reviewer_id = sfn.JsonPath.stringAt(
        status === "PUBLISHED" ? "$.reviewer_id" : "$.review.reviewer_id",
      );
    }
    if (status === "PUBLISHED") {
      payload.shared_memory_record_id = sfn.JsonPath.stringAt(
        "$.shared_memory_record_id",
      );
      payload.promotion_hint = sfn.JsonPath.stringAt("$.promotion_hint");
    }
    return new tasks.LambdaInvoke(this, id, {
      lambdaFunction: fn,
      payload: sfn.TaskInput.fromObject(payload),
      outputPath: "$.Payload",
      retryOnServiceExceptions: true,
    });
  }

  private pythonFunction(
    id: string,
    props: {
      readonly handler: string;
      readonly environment: Record<string, string>;
      readonly timeout?: Duration;
      readonly layers?: lambda.ILayerVersion[];
    },
  ): lambda.Function {
    const functionName = this.resourceName(this.stackName, id);
    const logGroup = new logs.LogGroup(this, `${id}LogGroup`, {
      logGroupName: `/aws/lambda/${functionName}`,
      retention: logs.RetentionDays.ONE_MONTH,
      removalPolicy: RemovalPolicy.DESTROY,
    });
    return new lambda.Function(this, id, {
      functionName,
      runtime: lambda.Runtime.PYTHON_3_12,
      architecture: lambda.Architecture.ARM_64,
      code: lambda.Code.fromAsset(path.join(__dirname, "../../src")),
      handler: props.handler,
      timeout: props.timeout ?? Duration.seconds(10),
      memorySize: 256,
      tracing: lambda.Tracing.ACTIVE,
      logGroup,
      layers: props.layers,
      environment: {
        ...props.environment,
        POWERTOOLS_SERVICE_NAME: "agentcore-memory-governance",
      },
    });
  }

  private resourceName(prefix: string, suffix: string): string {
    return `${prefix}-${suffix}`
      .replace(/[^A-Za-z0-9_-]/g, "-")
      .slice(0, 64);
  }

  private memoryName(prefix: string, suffix: string): string {
    const name = `${prefix}_${suffix}`.replace(/[^A-Za-z0-9_]/g, "_");
    return /^[A-Za-z]/.test(name) ? name.slice(0, 48) : `m_${name}`.slice(0, 48);
  }
}
