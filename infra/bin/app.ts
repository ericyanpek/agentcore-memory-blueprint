#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { MemoryGovernanceStack } from "../lib/memory-governance-stack";

const app = new cdk.App();

// Resource names derive from these two values, so a missing context value must
// fail the synth instead of silently renaming (and replacing) live resources.
function requiredContext(key: string): string {
  const value = app.node.tryGetContext(key);
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`context "${key}" is required; set it in cdk.json or pass -c ${key}=<value>`);
  }
  return value;
}

const projectId = requiredContext("projectId");
const environmentName = requiredContext("environmentName");
const reviewerOrigin =
  app.node.tryGetContext("reviewerOrigin") ?? "http://localhost:3000";

new MemoryGovernanceStack(app, "AgentCoreMemoryGovernance", {
  projectId,
  environmentName,
  reviewerOrigin,
  description:
    "Event-driven personal and reviewed shared memory blueprint for AgentCore",
});
