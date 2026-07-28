---
name: validate-revenue-metric
description: Validate project revenue analyses against the governed metric definition and refund handling rules.
version: 1
---

# Validate Revenue Metric

Use this Skill when a project member asks for revenue, bookings, net revenue, or
refund analysis.

## Procedure

1. Retrieve the current revenue metric definition from the managed Knowledge Base.
2. Inspect the dataset or view metadata using the approved catalog tool.
3. Determine whether the requested metric is net revenue or gross booked revenue.
4. For net revenue, use the curated revenue view.
5. For gross booked revenue, use the booking ledger and account for refunds
   explicitly.
6. Report the source, effective date, filters, and row-count validation.
7. Stop and ask for clarification if the Knowledge Base definition conflicts with
   the dataset schema. Never resolve the conflict from shared memory alone.

## Evidence

This procedure was promoted from reviewed project memory. Future changes require a
Git review and a validation test against a representative dataset.

