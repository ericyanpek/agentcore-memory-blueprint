from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError


AWS_CONFIG = Config(
    retries={"total_max_attempts": 8, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=60,
)
RUNTIME_NAME = "memory_poc_agent"
ENDPOINT_NAME = "default"
ROLE_NAME = "agentcore-memory-poc-runtime-role"
POLICY_NAME = "agentcore-memory-poc-runtime"


def output_values(path: pathlib.Path) -> dict[str, str]:
    document = json.loads(path.read_text())
    stack = document["AgentCoreMemoryGovernance"]
    return {key: str(value) for key, value in stack.items()}


def ensure_bucket(s3: Any, bucket: str, region: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
        return
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        if str(code) not in {"404", "NoSuchBucket", "NotFound"}:
            raise
    if region == "us-east-1":
        s3.create_bucket(Bucket=bucket)
    else:
        s3.create_bucket(
            Bucket=bucket,
            CreateBucketConfiguration={"LocationConstraint": region},
        )
    s3.put_public_access_block(
        Bucket=bucket,
        PublicAccessBlockConfiguration={
            "BlockPublicAcls": True,
            "IgnorePublicAcls": True,
            "BlockPublicPolicy": True,
            "RestrictPublicBuckets": True,
        },
    )
    s3.put_bucket_encryption(
        Bucket=bucket,
        ServerSideEncryptionConfiguration={
            "Rules": [
                {
                    "ApplyServerSideEncryptionByDefault": {
                        "SSEAlgorithm": "AES256"
                    }
                }
            ]
        },
    )


def ensure_role(
    iam: Any,
    *,
    account_id: str,
    region: str,
    bucket: str,
    key: str,
    memory_key_arn: str,
    personal_memory_id: str,
    shared_memory_id: str,
    project_id: str,
) -> str:
    trust = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {
                    "Service": "bedrock-agentcore.amazonaws.com"
                },
                "Action": "sts:AssumeRole",
                "Condition": {
                    "StringEquals": {"aws:SourceAccount": account_id},
                    "ArnLike": {
                        "aws:SourceArn": (
                            f"arn:aws:bedrock-agentcore:{region}:"
                            f"{account_id}:runtime/*"
                        )
                    },
                },
            }
        ],
    }
    try:
        role = iam.create_role(
            RoleName=ROLE_NAME,
            AssumeRolePolicyDocument=json.dumps(trust),
            Description="Execution role for the AgentCore Memory POC runtime",
            Tags=[
                {"Key": "Project", "Value": "agentcore-memory-poc"},
                {"Key": "Environment", "Value": "poc"},
            ],
        )["Role"]
    except iam.exceptions.EntityAlreadyExistsException:
        iam.update_assume_role_policy(
            RoleName=ROLE_NAME,
            PolicyDocument=json.dumps(trust),
        )
        role = iam.get_role(RoleName=ROLE_NAME)["Role"]

    personal_arn = (
        f"arn:aws:bedrock-agentcore:{region}:{account_id}:memory/"
        f"{personal_memory_id}"
    )
    shared_arn = (
        f"arn:aws:bedrock-agentcore:{region}:{account_id}:memory/"
        f"{shared_memory_id}"
    )
    project_namespace = f"/projects/project:{project_id}/shared/"
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "InvokeModel",
                "Effect": "Allow",
                "Action": [
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                "Resource": (
                    f"arn:aws:bedrock:{region}::foundation-model/"
                    "amazon.nova-micro-v1:0"
                ),
            },
            {
                "Sid": "PersonalMemory",
                "Effect": "Allow",
                "Action": [
                    "bedrock-agentcore:CreateEvent",
                    "bedrock-agentcore:GetEvent",
                    "bedrock-agentcore:ListEvents",
                    "bedrock-agentcore:RetrieveMemoryRecords",
                    "bedrock-agentcore:GetMemoryRecord",
                ],
                "Resource": personal_arn,
            },
            {
                "Sid": "SharedMemoryRead",
                "Effect": "Allow",
                "Action": "bedrock-agentcore:RetrieveMemoryRecords",
                "Resource": shared_arn,
                "Condition": {
                    "StringEquals": {
                        "bedrock-agentcore:namespace": project_namespace
                    }
                },
            },
            {
                "Sid": "MemoryEncryptionKey",
                "Effect": "Allow",
                "Action": [
                    "kms:Decrypt",
                    "kms:DescribeKey",
                    "kms:Encrypt",
                    "kms:GenerateDataKey",
                ],
                "Resource": memory_key_arn,
            },
            {
                "Sid": "ReadCode",
                "Effect": "Allow",
                "Action": "s3:GetObject",
                "Resource": f"arn:aws:s3:::{bucket}/{key}",
            },
            {
                "Sid": "RuntimeTelemetry",
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams",
                    "logs:PutLogEvents",
                    "xray:PutTraceSegments",
                    "xray:PutTelemetryRecords",
                ],
                "Resource": "*",
            },
            {
                "Sid": "RuntimeMetrics",
                "Effect": "Allow",
                "Action": "cloudwatch:PutMetricData",
                "Resource": "*",
                "Condition": {
                    "StringEquals": {
                        "cloudwatch:namespace": "bedrock-agentcore"
                    }
                },
            },
        ],
    }
    iam.put_role_policy(
        RoleName=ROLE_NAME,
        PolicyName=POLICY_NAME,
        PolicyDocument=json.dumps(policy),
    )
    return role["Arn"]


def wait_for_runtime(control: Any, runtime_id: str) -> dict[str, Any]:
    deadline = time.time() + 900
    while time.time() < deadline:
        runtime = control.get_agent_runtime(agentRuntimeId=runtime_id)
        status = runtime["status"]
        if status == "READY":
            return runtime
        if status.endswith("FAILED"):
            raise RuntimeError(
                f"runtime deployment failed: {runtime.get('failureReason')}"
            )
        time.sleep(15)
    raise TimeoutError("runtime did not become READY within 15 minutes")


def wait_for_endpoint(
    control: Any,
    runtime_id: str,
    endpoint_name: str,
) -> dict[str, Any]:
    deadline = time.time() + 900
    while time.time() < deadline:
        endpoint = control.get_agent_runtime_endpoint(
            agentRuntimeId=runtime_id,
            endpointName=endpoint_name,
        )
        status = endpoint["status"]
        if status == "READY":
            return endpoint
        if status.endswith("FAILED"):
            raise RuntimeError(
                f"endpoint deployment failed: {endpoint.get('failureReason')}"
            )
        time.sleep(15)
    raise TimeoutError("runtime endpoint did not become READY within 15 minutes")


def deploy(
    *,
    outputs_path: pathlib.Path,
    zip_path: pathlib.Path,
    region: str,
    project_id: str,
) -> dict[str, Any]:
    outputs = output_values(outputs_path)
    session = boto3.Session(region_name=region)
    sts = session.client("sts", config=AWS_CONFIG)
    s3 = session.client("s3", config=AWS_CONFIG)
    iam = session.client("iam", config=AWS_CONFIG)
    control = session.client("bedrock-agentcore-control", config=AWS_CONFIG)
    account_id = sts.get_caller_identity()["Account"]
    bucket = f"agentcore-memory-poc-{account_id}-{region}"
    key = "runtime/memory-poc-runtime.zip"
    personal_memory = control.get_memory(
        memoryId=outputs["PersonalMemoryId"]
    )["memory"]
    memory_key_arn = personal_memory["encryptionKeyArn"]

    ensure_bucket(s3, bucket, region)
    s3.upload_file(str(zip_path), bucket, key)
    role_arn = ensure_role(
        iam,
        account_id=account_id,
        region=region,
        bucket=bucket,
        key=key,
        memory_key_arn=memory_key_arn,
        personal_memory_id=outputs["PersonalMemoryId"],
        shared_memory_id=outputs["SharedMemoryId"],
        project_id=project_id,
    )
    time.sleep(10)

    artifact = {
        "codeConfiguration": {
            "code": {"s3": {"bucket": bucket, "prefix": key}},
            "runtime": "PYTHON_3_13",
            "entryPoint": ["runtime_agent.py"],
        }
    }
    environment = {
        "PERSONAL_MEMORY_ID": outputs["PersonalMemoryId"],
        "SHARED_MEMORY_ID": outputs["SharedMemoryId"],
        "PROJECT_ID": project_id,
        "MODEL_ID": "amazon.nova-micro-v1:0",
    }
    existing = next(
        (
            runtime
            for runtime in control.list_agent_runtimes().get(
                "agentRuntimes", []
            )
            if runtime.get("agentRuntimeName") == RUNTIME_NAME
        ),
        None,
    )
    if existing:
        runtime_id = existing["agentRuntimeId"]
        control.update_agent_runtime(
            agentRuntimeId=runtime_id,
            agentRuntimeArtifact=artifact,
            roleArn=role_arn,
            networkConfiguration={"networkMode": "PUBLIC"},
            protocolConfiguration={"serverProtocol": "HTTP"},
            description="AgentCore Memory multi-user validation POC",
            environmentVariables=environment,
        )
    else:
        created = control.create_agent_runtime(
            agentRuntimeName=RUNTIME_NAME,
            agentRuntimeArtifact=artifact,
            roleArn=role_arn,
            networkConfiguration={"networkMode": "PUBLIC"},
            protocolConfiguration={"serverProtocol": "HTTP"},
            description="AgentCore Memory multi-user validation POC",
            environmentVariables=environment,
            tags={
                "Project": "agentcore-memory-poc",
                "Environment": "poc",
            },
        )
        runtime_id = created["agentRuntimeId"]
    runtime = wait_for_runtime(control, runtime_id)

    endpoints = control.list_agent_runtime_endpoints(
        agentRuntimeId=runtime_id
    ).get("runtimeEndpoints", [])
    endpoint = next(
        (item for item in endpoints if item.get("name") == ENDPOINT_NAME),
        None,
    )
    if endpoint:
        control.update_agent_runtime_endpoint(
            agentRuntimeId=runtime_id,
            endpointName=ENDPOINT_NAME,
            agentRuntimeVersion=runtime["agentRuntimeVersion"],
        )
    else:
        created_endpoint = control.create_agent_runtime_endpoint(
            agentRuntimeId=runtime_id,
            name=ENDPOINT_NAME,
            agentRuntimeVersion=runtime["agentRuntimeVersion"],
            description="Default endpoint for the Memory POC",
            tags={
                "Project": "agentcore-memory-poc",
                "Environment": "poc",
            },
        )
    endpoint = wait_for_endpoint(control, runtime_id, ENDPOINT_NAME)
    return {
        "account_id": account_id,
        "region": region,
        "project_id": project_id,
        "runtime_id": runtime_id,
        "runtime_arn": runtime["agentRuntimeArn"],
        "runtime_version": runtime["agentRuntimeVersion"],
        "endpoint_id": endpoint["id"],
        "endpoint_arn": endpoint["agentRuntimeEndpointArn"],
        "endpoint_status": endpoint["status"],
        "personal_memory_id": outputs["PersonalMemoryId"],
        "shared_memory_id": outputs["SharedMemoryId"],
        "review_api_url": outputs["ReviewApiUrl"],
        "reviewer_user_pool_id": outputs["ReviewerUserPoolId"],
        "reviewer_client_id": outputs["ReviewerClientId"],
        "reviewer_group_name": outputs["ReviewerGroupName"],
        "event_bus_name": outputs["ProjectEventBusName"],
        "candidate_table_name": outputs["CandidateTableName"],
        "evidence_bucket_name": outputs["EvidenceBucketName"],
        "artifact_bucket": bucket,
        "artifact_key": key,
        "runtime_role_arn": role_arn,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outputs", type=pathlib.Path, required=True)
    parser.add_argument("--zip", type=pathlib.Path, required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--project-id", required=True)
    parser.add_argument(
        "--result",
        type=pathlib.Path,
        default=pathlib.Path("build/poc-deployment.json"),
    )
    args = parser.parse_args()
    try:
        result = deploy(
            outputs_path=args.outputs,
            zip_path=args.zip,
            region=args.region,
            project_id=args.project_id,
        )
        args.result.parent.mkdir(parents=True, exist_ok=True)
        args.result.write_text(json.dumps(result, indent=2) + "\n")
        print(json.dumps(result, indent=2))
        return 0
    except (ClientError, RuntimeError, TimeoutError, KeyError) as error:
        print(f"Deployment failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
