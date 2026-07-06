# Library Embedding Boundary

`lfguard` is a Lake Formation policy review engine first. It is not intended to
become a request-time mutation SDK for every service that manages Lake
Formation.

Use this document when evaluating feature requests from services that want to
embed `lfguard` as a library.

## Core Stance

- Keep advisory evidence as the center of the product.
- Keep desired/current state, lint, audit, explain, review, and plan
  deterministic and reviewable.
- Keep `apply` explicit, conservative, and separate from approval workflow
  orchestration.
- Keep service IAM layout, approval identity, runtime credentials, customer
  language, and request-state ownership outside `lfguard`.

## Preferred Integration Paths

Choose the smallest integration that solves the problem:

1. Service or workflow integration:
   invoke `python -m lakeformation_guard ...` and consume JSON artifacts.
2. Offline policy or evidence reuse:
   use the public top-level Python API for models, `lint_desired()`, `audit()`,
   `plan()`, `explain()`, providers, and the policy builder.
3. Scoped live AWS helpers:
   use `lakeformation_guard.aws.AWSLakeFormationAdapter` only when a caller
   explicitly needs live inventory or explicit apply helpers and accepts that
   this is not the primary service integration contract.

## Changes That Fit Core

These requests usually belong in `lfguard`:

- New Lake Formation state shapes, planner actions, and explanation logic for
  supported LF resources.
- Small normalization and parsing fixes that make desired/current state inputs
  more robust without changing the product boundary.
- Conservative apply improvements that keep destructive behavior explicit behind
  planner options and CLI flags.
- Narrow boto3 adapter coverage expansions for already modeled Lake Formation
  operations.
- Documentation for multi-catalog usage, cache scoping, and provider context.

## Changes Usually Kept Outside Core

These requests are usually declined or redirected:

- Per-request imperative convenience helpers such as `grant()`, `revoke()`,
  `upsert_*()`, or `convert_to_*()` that are designed around one HTTP handler
  rather than reviewed desired state and plans.
- Automatic apply flows, rollback engines, or HTTP-response-oriented execution
  orchestration that turn `lfguard` into a service mutation runtime.
- Dynamic desired-state expansion from live AWS at plan time, such as "all
  current values of this LF-Tag key". Desired policy should stay explicit and
  reviewable.
- Broad public export of internal helper modules only to stabilize downstream
  imports. The stable service contract is the CLI plus JSON artifacts.
- Organization-specific request statuses, approval workflow states, Jira/Slack
  portal semantics, or service IAM role architecture.

## Multi-Catalog Guidance

`lfguard` does not provide a catalog-orchestration engine. Treat each catalog as
an explicit review scope:

- Put `catalog_id` on desired resources, LF-Tags, expressions, and filters when
  the scope is catalog-specific.
- Keep one cache file or provider context per `(profile, region, catalog_id)`
  tuple.
- Run review or apply once per reviewed catalog scope, or save a plan and apply
  only the approved change IDs.

Example CLI pattern:

```bash
lfguard snapshot \
  --desired policy/desired.json \
  --profile prod \
  --region us-east-1 \
  --catalog-id 111122223333 \
  --output-file snapshots/prod-111122223333.json

lfguard review \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-111122223333.json \
  --output-dir artifacts/review-111122223333
```

If a service needs to fan out across catalogs, keep that loop in the service or
workflow layer rather than adding a catalog scheduler to `lfguard` core.

## When Raw boto3 Is The Right Tool

Use raw boto3 or a service-owned wrapper when you need:

- Lake Formation features that `lfguard` does not model.
- Request-time imperative mutations that intentionally bypass the review-bundle
  workflow.
- Full control over retries, rollback, batching, or portal-specific execution
  semantics.

`lfguard` should remain the place for policy correctness, stable evidence, and
explicit reviewed changes, not the place for every service-specific control
plane abstraction.
