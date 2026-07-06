---
name: Feature request
about: Suggest a new lfguard workflow, resource shape, output, or integration
title: ""
labels: enhancement
assignees: ""
---

Read these first:

- [`docs/library-embedding-boundary.md`](../../docs/library-embedding-boundary.md)
- [`docs/service-integration.md`](../../docs/service-integration.md)
- [`docs/architecture.md`](../../docs/architecture.md)

If the request mixes multiple behaviors, split it into separate issues.
Maintainers will triage requests with
[`docs/request-screening.md`](../../docs/request-screening.md).

## Problem

What Lake Formation guardrail workflow is difficult today?

## Proposed change

Describe the command, API, report shape, or documentation you expect.

## Why this belongs in lfguard

Explain why this should live in `lfguard` instead of the consuming service,
approval workflow, or a raw boto3 wrapper.

## Example policy or output

Paste a sanitized desired-state, current-state, plan, audit, or apply example
if it helps explain the request.

## Alternatives considered

Describe whether you currently solve this with Terraform, CloudFormation, CDK,
raw boto3, the AWS console, or another workflow.
