---
name: Feature request
about: Suggest a new lfguard workflow, resource shape, output, or integration
title: ""
labels: enhancement
assignees: ""
---

## Before filing

Read these first:

- `docs/library-embedding-boundary.md`
- `docs/service-integration.md`
- `docs/architecture.md`

Confirm the request is still a fit for `lfguard` core:

- [ ] This is not primarily a request-time mutation helper for one service endpoint.
- [ ] This does not add automatic apply, rollback orchestration, or approval workflow state into core.
- [ ] This keeps audit/plan/review behavior deterministic and reviewable.
- [ ] If this touches live AWS behavior, it is a narrow adapter expansion rather than a general browse/discovery SDK.
- [ ] If this request mixes multiple behaviors, I split them into separate issues.

## Problem

What Lake Formation guardrail workflow is difficult today?

## Proposed behavior

Describe the command, API, report shape, or documentation you would expect.

## Why this belongs in lfguard

Explain why this should live in `lfguard` instead of:

- the consuming service or approval workflow;
- a raw boto3 wrapper owned by the service;
- a broader infrastructure or portal integration layer.

## Example policy or output

Paste a sanitized desired-state, current-state, plan, audit, or apply example if
it helps explain the request.

## Safety expectations

Should this be additive by default, destructive only behind an allow flag, or
read-only?

## AWS scope expectations

If live AWS calls are involved, answer these:

- Is the scope explicit and narrow, or is this really account-wide browse/discovery?
- Can this stay in the adapter layer without changing audit/plan determinism?

## Alternatives considered

Describe whether you currently solve this with Terraform, CloudFormation, CDK,
raw boto3, the AWS console, or another workflow.
