# Where lfguard Fits

`lfguard` is built for Lake Formation policy guardrails, not general AWS
infrastructure provisioning. It is most useful when LF-Tag policy should be
reviewed as code, checked for drift, explained, and attached to approval or
audit records before any optional apply step.

## Use lfguard when

- You want pull-request, Jira, service approval, or audit evidence for LF-Tags,
  resource tag assignments, and Lake Formation grants.
- You need CI jobs that fail on drift or non-empty change plans.
- You want one review bundle containing lint, audit, plan, and planned grant
  evidence.
- You need a small Python API around Lake Formation policy decisions without
  writing one-off boto3 orchestration.
- You want destructive changes, such as permission revokes, to require explicit
  flags and a separate review path.

## Use infrastructure tools for

Terraform, CloudFormation, and CDK are still the right place for foundational
resources such as accounts, VPCs, IAM roles, S3 buckets, Glue databases, and
registered data lake locations.

`lfguard` can sit next to those tools when the Lake Formation policy layer needs
its own audit and approval workflow. A common pattern is:

1. Provision infrastructure and IAM principals with your infrastructure tool.
2. Store desired LF-Tag policy in the application or platform repository.
3. Run `lfguard review` in CI to produce machine-readable JSON plus Markdown
   evidence.
4. Run `lfguard apply` first as a dry run, then with `--execute` only after
   the review bundle is approved.

See [`lake-formation-guide.md`](lake-formation-guide.md) for the Lake Formation
concepts, best practices, and antipatterns that inform this split.
See [`terraform-cdk-coexistence.md`](terraform-cdk-coexistence.md) for a
detailed ownership matrix and pipeline pattern.

## Use raw boto3 when

Raw boto3 is appropriate for custom workflows that need full control over every
AWS API call or that cover Lake Formation features outside `lfguard`'s supported
surface.

`lfguard` is a better fit when the problem is repeated policy comparison,
reviewable reports, conservative defaults, and a reusable package API.

## Use the AWS console when

The console is useful for exploration and one-off inspection. It is less useful
as the source of truth for production access policy because changes can be hard
to review, reproduce, or gate in CI.

Use `lfguard snapshot` when you need to capture current Lake Formation state for
review before moving policy into version control.

## When not to use lfguard

Do not use `lfguard` as the only control for account security or data access. It
does not create IAM principals, register data lake locations, configure
cross-account sharing, or replace Lake Formation administration.

Do not use `lfguard apply --execute` without reviewing the generated plan and
running it with a principal that has only the permissions needed for the planned
operation.
