# lfguard

[![CI](https://github.com/yongjip/aws-datalake-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/yongjip/aws-datalake-guard/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/lfguard.svg)](https://pypi.org/project/lfguard/)
[![Python](https://img.shields.io/pypi/pyversions/lfguard.svg)](https://pypi.org/project/lfguard/)

`lfguard` is a strict framework for defining, validating, explaining, planning,
and safely applying AWS Lake Formation data permissions. It compares a desired
LF-Tag and permission policy against current state, reports drift, produces a
conservative change plan, and can apply only the changes that you explicitly
allow.

The import package is `lakeformation_guard`; the CLI command is `lfguard`.

## What it manages

- LF-Tag definitions and allowed values.
- Named LF-Tag expressions.
- LF-Tag assignments on Lake Formation Data Catalog resources.
- Lake Formation data cells filter definitions for row and column scoped
  access.
- Lake Formation grants on catalog, database, table, column, data location,
  LF-Tag policy, and data cells filter resources.
- Python-native permission groups that generate reviewable desired state.
- Offline audit and plan workflows from JSON or YAML snapshots.
- Offline effective-access explanations from JSON or YAML snapshots.
- Live AWS inventory and apply workflows through the optional `boto3` adapter.
- Live AWS import for starter desired-state scaffolds.

By default, plans only add missing definitions, tag assignments, and permissions.
Potentially destructive changes, such as revoking permissions or removing tag
values, are omitted unless the matching allow flag is set.

## What it does not manage

`lfguard` is deliberately scoped to Lake Formation policy guardrails. It does
not create IAM principals, register data lake locations, configure
cross-account sharing, crawl the whole Glue Data Catalog, or replace Terraform,
CloudFormation, CDK, or IAM administration. Live inventory is scoped by the
desired-state file so drift checks stay focused and reviewable.

## Why use it

- Reviewable plans before touching production Lake Formation state.
- Conservative defaults that avoid accidental revokes and tag removals.
- Works offline from snapshots, which makes CI drift checks possible.
- Lints desired policy for undefined LF-Tag keys and values before AWS access.
- Explains why access exists or is missing before changing policy.
- Captures risky access exceptions with reason, owner or approver, expiry, and
  scoped rules instead of forcing broad lint ignores.
- Keeps the Python API dependency-light while isolating boto3 in the AWS adapter.
- Produces text, JSON, Markdown, and SARIF output suitable for pull request
  comments, release checks, code scanning, and platform automation.
- Leaves stable CI evidence for audits, permission requests, and exception
  reviews without requiring console screenshots.

## Core workflow

`lfguard` is useful when it keeps the workflow small:

| Step | Command | Purpose |
| --- | --- | --- |
| 1 | `lfguard check` | Validate and lint desired policy before AWS access. |
| 2 | `lfguard audit` | Compare desired policy with current state and report drift. |
| 3 | `lfguard plan` | Produce the conservative change set reviewers should approve. |
| 4 | `lfguard apply` | Dry-run by default; execute only after review. |

Everything else is supporting workflow: Python policy generation, sample files,
repository bootstrap, schema export, install diagnostics, IAM policy starters,
effective-access explanation, and report formatting. Those helpers are optional.
The core value is still check, audit, plan, and conservative apply.

`lfguard check --fail-on-findings` is deliberately rigid: it blocks undefined
tags, mixed-case LF-Tags, multiple values for one key on a resource, broad
principals, `ALL`/`SUPER`, LF-Tag table policies that mix `SELECT` with
`ALTER`/`DELETE`/`DROP`/`INSERT`, and other patterns that make a lake harder to
govern like a controlled database.
Existing environments can tune lint severities in desired state with a top-level
`lint` section, or use scoped `exceptions` when one risky grant is intentional
and should carry approval evidence.

## Common use cases

- Fail a CI check when production Lake Formation state drifts from a reviewed
  desired-state file.
- Import live Lake Formation state into a starter desired-state file that a
  platform owner can review and then commit.
- Generate a safe change plan for new LF-Tag values, table tag assignments, and
  LF-Tag policy grants, including grants that reference named LF-Tag
  expressions.
- Explain why a role can see a database, table, column set, row/column-filtered
  table view, or data location from direct grants, LF-Tag policies, named LF-Tag
  expressions, data cells filters, and effective LF-Tags.
- Let platform teams review destructive operations separately from additive
  changes.
- Keep data access policy as code without writing direct boto3 orchestration for
  every grant and tag assignment.
- Coexist with Terraform, CloudFormation, or CDK by letting infrastructure tools
  own resources while `lfguard` owns reviewed Lake Formation policy.

## Lake Formation operating model

If you are adopting Lake Formation or LF-Tag based access control for the first
time, start with [`docs/lake-formation-guide.md`](docs/lake-formation-guide.md).
It explains how IAM, Glue Data Catalog resources, Lake Formation grants,
LF-Tags, `IAMAllowedPrincipals`, hybrid access mode, and data filters fit
together, then calls out the small set of best practices and antipatterns that
shape `lfguard`'s conservative defaults.

For the framework lifecycle, provider boundary, exception model, and stable
evidence outputs, see
[`docs/permission-framework.md`](docs/permission-framework.md).

## Install

```bash
python -m pip install lfguard
```

For an isolated CLI install:

```bash
pipx install lfguard
uv tool install lfguard
```

For live AWS usage:

```bash
python -m pip install "lfguard[aws]"
```

For YAML policy files:

```bash
python -m pip install "lfguard[yaml]"
```

## Quickstart

Generate a runnable offline demo with no AWS credentials:

```bash
lfguard sample --output-dir lfguard-demo
```

The command writes `desired.json`, `current-snapshot.json`, and a short
`README.md` with copy-paste commands.

Check that the generated files are valid and lint-clean:

```bash
lfguard check \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

Audit the deliberately incomplete snapshot:

```bash
lfguard audit \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

Plan the additive changes that would close the gap:

```bash
lfguard plan \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

Expected output:

```text
Plan: 4 change(s), 4 safe, 0 destructive.
- [safe] lf_tag.add_values lf_tag:sensitivity: LF-Tag is missing allowed values
- [safe] resource_tag.add_values table:database=analytics:table=orders: Resource is missing desired LF-Tag assignments
- [safe] grant.add_permissions arn:aws:iam::111122223333:role/Analyst -> lf_tag_policy:resource_type=TABLE:expression=domain=sales,sensitivity=internal|public: Principal is missing desired Lake Formation permissions
- [safe] grant.add_permissions arn:aws:iam::111122223333:role/FilteredAnalyst -> data_cells_filter:database=analytics:table=orders:filter_name=orders_public: Principal is missing desired Lake Formation permissions
```

Explain the sample row/column-filtered grant:

```bash
lfguard explain \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json \
  --principal arn:aws:iam::111122223333:role/FilteredAnalyst \
  --database analytics \
  --table orders \
  --data-cells-filter orders_public \
  --permissions SELECT
```

For repeated live reads, use a cache path scoped to the AWS context and pass the
context explicitly:

```bash
lfguard plan \
  --desired lfguard-demo/desired.json \
  --profile prod \
  --region us-east-1 \
  --catalog-id 111122223333 \
  --current-cache .lfguard/prod-us-east-1-111122223333-current.json \
  --current-cache-max-age 900
```

## Desired state format

For permission-group workflows, author `policy.py` and generate desired state:

```python
from lakeformation_guard.policy import (
    LakePolicy,
    TagAssignmentScope,
    database_creator,
    reader,
    table_creator,
)

policy = LakePolicy()
policy.tag_key(
    "domain",
    values=["sales", "finance", "platform"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
)
policy.tag_key(
    "contains_pii",
    values=["false", "true"],
    assignable_to=[
        TagAssignmentScope.DATABASE,
        TagAssignmentScope.TABLE,
        TagAssignmentScope.COLUMN,
    ],
)

policy.tag_database("sales_curated", domain="sales", contains_pii="false")
policy.tag_table("sales_curated", "customers", contains_pii="false")
policy.tag_columns("sales_curated", "customers", "phone_number", contains_pii="true")

policy.group("dataconsumer", reader().where(domain="sales", contains_pii="false"))
policy.group("dataengineer", table_creator().where(domain="sales"))
policy.group("catalog_admin", database_creator())

policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")
policy.bind_role("arn:aws:iam::111122223333:role/DataEngineer", "dataengineer")
policy.bind_role("arn:aws:iam::111122223333:role/CatalogAdmin", "catalog_admin")
```

`tag_database()`, `tag_table()`, and `tag_columns()` write normal
`resource_tags` entries. Their tag keys must be declared with an assignment
scope that includes that resource level.
For LF-Tag keys that are not valid Python identifiers, use mapping form:

```python
policy.group("dataconsumer", reader().where({"data-domain": "sales"}))
policy.tag_database("sales_curated", tags={"data-domain": "sales"})
```

```bash
lfguard generate policy.py --output-file policy/desired.json --force
lfguard generate policy.py --output-file policy/desired.json --check
lfguard check --desired policy/desired.json --fail-on-findings
```

The built-in templates are intentionally small:

| Template | Lake Formation intent |
| --- | --- |
| `reader()` | `DESCRIBE` databases and `DESCRIBE`/`SELECT` matching tables. Column-narrowing LF-Tags are allowed. |
| `editor()` | `DESCRIBE` databases and `DESCRIBE`/`SELECT`/`INSERT`/`DELETE` matching whole tables. Column-narrowing LF-Tags are rejected. |
| `producer()` | `DESCRIBE`/`CREATE_TABLE` matching databases and editor-style table access for producer workflows. Column-narrowing LF-Tags are rejected. |
| `table_creator()` | `DESCRIBE`/`CREATE_TABLE` matching databases and editor-style table access. Column-narrowing LF-Tags are rejected. |
| `database_creator()` | Catalog-level `CREATE_DATABASE`. No LF-Tag filter is used because AWS grants this on the catalog. Use sparingly; AWS gives database creators follow-on metadata authority on databases they create. |
| `steward("expr")` | `DESCRIBE` and `GRANT_WITH_LF_TAG_EXPRESSION` on one named LF-Tag expression. No LF-Tag filter is used. |
| `data_location_access("arn")` | `DATA_LOCATION_ACCESS` on one registered data location. No LF-Tag filter is used. |
| `admin()` | Catalog-level `CREATE_DATABASE`, `CREATE_LF_TAG`, `CREATE_LF_TAG_EXPRESSION`, and `DESCRIBE`. It does not grant `ALL`, `SUPER`, or grant option. |

Raw JSON and YAML remain supported for lower-level workflows and use the same
shape:

```json
{
  "lf_tags": {
    "sensitivity": ["public", "internal", "restricted"],
    "domain": ["sales", "finance"]
  },
  "lf_tag_expressions": {
    "sales_tables": {
      "expression": {
        "domain": ["sales"],
        "sensitivity": ["public", "internal"]
      }
    }
  },
  "data_cells_filters": [
    {
      "name": "orders_public",
      "database": "analytics",
      "table": "orders",
      "row_filter": "country = 'US'",
      "columns": ["order_id", "status"]
    }
  ],
  "resource_tags": [
    {
      "resource": {
        "kind": "table",
        "database": "analytics",
        "table": "orders"
      },
      "tags": {
        "sensitivity": ["internal"],
        "domain": ["sales"]
      }
    }
  ],
  "grants": [
    {
      "principal": "arn:aws:iam::111122223333:role/Analyst",
      "resource": {
        "kind": "lf_tag_policy",
        "resource_type": "TABLE",
        "expression_name": "sales_tables"
      },
      "permissions": ["SELECT", "DESCRIBE"]
    },
    {
      "principal": "arn:aws:iam::111122223333:role/FilteredAnalyst",
      "resource": {
        "kind": "data_cells_filter",
        "database": "analytics",
        "table": "orders",
        "filter_name": "orders_public"
      },
      "permissions": ["SELECT"]
    }
  ]
}
```

Supported resource kinds are `catalog`, `database`, `table`,
`table_with_columns`, `data_location`, `data_cells_filter`, `lf_tag_policy`,
and `lf_tag_expression`.
Write LF-Tag keys and values in lower case. AWS stores them in lower case, and
allows only one value for a given LF-Tag key on a single resource.
See [`docs/state-format.md`](docs/state-format.md) for copyable examples of
each resource kind and grant shape.

## CLI

Show version and command help:

```bash
lfguard --version
lfguard --help
```

Core commands:

```bash
lfguard check --desired desired.json --current-snapshot current.json --fail-on-findings
lfguard audit --desired desired.json --current-snapshot current.json --fail-on-findings
lfguard plan --desired desired.json --current-snapshot current.json
lfguard apply --desired desired.json --profile prod --region ap-northeast-2
```

Starter and support commands:

```bash
lfguard init --output-file policy/desired.json
lfguard generate policy.py --output-file policy/desired.json
lfguard generate policy.py --output-file policy/desired.json --check
lfguard sample --output-dir lfguard-demo
lfguard bootstrap --output-dir lfguard-policy
lfguard import --catalog-id 123456789012 \
  --output policy/imported-desired.json \
  --review-notes policy/import-review.md
lfguard explain \
  --desired desired.json \
  --current-snapshot current.json \
  --principal role \
  --database analytics \
  --table orders
lfguard schema --output-file policy/lfguard.schema.json
lfguard doctor --require aws
lfguard permissions --template read-only --include-glue-read
```

Keep optional scaffolds secondary. Add them only when someone owns the workflow:

```bash
lfguard bootstrap --output-dir lfguard-policy --include-live-drift
lfguard bootstrap --output-dir lfguard-policy --include-code-scanning
lfguard bootstrap --output-dir lfguard-policy --include-review-template
lfguard bootstrap --output-dir lfguard-policy --include-editor-config
```

Allow revokes only when that is the intended maintenance operation:

```bash
lfguard plan \
  --desired desired.json \
  --current-snapshot current.json \
  --allow-permission-revokes
```

## Python API

```python
from lakeformation_guard import (
    CurrentState,
    DesiredState,
    PlanOptions,
    ResourceRef,
    audit,
    explain,
    lint_desired,
    plan,
)

desired = DesiredState.from_dict({
    "lf_tags": {"sensitivity": ["public", "internal"]},
    "grants": [
        {
            "principal": "arn:aws:iam::111122223333:role/Analyst",
            "resource": {"kind": "database", "database": "analytics"},
            "permissions": ["DESCRIBE"],
        }
    ],
})

current = CurrentState.empty()
lint_findings = lint_desired(desired)
findings = audit(desired, current)
change_plan = plan(desired, current, PlanOptions())
access_report = explain(
    desired,
    current,
    principal="arn:aws:iam::111122223333:role/Analyst",
    resource=ResourceRef(kind="database", database_name="analytics"),
)

for finding in lint_findings:
    print(finding.code, finding.message)

for finding in findings:
    print(finding.code, finding.message)

for change in change_plan.changes:
    print(change.action, change.target)
```

## Live AWS apply

The live adapter only depends on `boto3` when you instantiate it:

```python
from lakeformation_guard import DesiredState, PlanOptions, plan
from lakeformation_guard.aws import AWSLakeFormationAdapter

desired = DesiredState.from_file("desired.json")
adapter = AWSLakeFormationAdapter.from_boto3(profile_name="prod", region_name="ap-northeast-2")
current = adapter.load_current_state_for(desired)
change_plan = plan(desired, current, PlanOptions())
adapter.apply(change_plan, dry_run=False)
```

For repeated live reads, keep caching outside the planner by wrapping the live
adapter as a provider:

```python
from lakeformation_guard import CachedCurrentStateProvider

provider = CachedCurrentStateProvider.for_aws(
    adapter,
    ".lfguard/prod-ap-northeast-2-111122223333-current.json",
    max_age_seconds=900,
    profile_name="prod",
    region_name="ap-northeast-2",
    catalog_id="111122223333",
)
current = provider.load_current_state_for(desired)
```

Cache entries are keyed by both desired-state scope and provider context. Use
`CachedCurrentStateProvider.for_aws(...)` for live AWS caches, and pass an
explicit `provider_context` for custom providers. Keep separate cache files for
stage/prod, regions, and catalogs.

Use an IAM principal with the minimum Lake Formation permissions required for the
actions you intend to run. The package does not bypass AWS authorization and does
not turn destructive changes on by default. Use `lfguard permissions` to
generate starter IAM policies and `lfguard permissions --check` to preflight the
role before live inventory or apply workflows.

## Release and Trust

The repository includes GitHub Actions for CI and PyPI Trusted Publishing. See
[`docs/publishing.md`](docs/publishing.md) for the release path and the exact
PyPI publisher settings. The latest release notes are in
[`docs/release-notes/v0.6.4.md`](docs/release-notes/v0.6.4.md), with prior
release notes under [`docs/release-notes/`](docs/release-notes/).

## More docs

- [`docs/cli.md`](docs/cli.md): command reference, common options, and exit
  codes.
- [`docs/recipes.md`](docs/recipes.md): audit-only, CI, and controlled apply
  workflows.
- [`docs/ci-evidence-workflows.md`](docs/ci-evidence-workflows.md): artifact
  sets and gates for pull requests, drift checks, plans, explains, and dry-run
  apply evidence.
- [`docs/adoption-checklist.md`](docs/adoption-checklist.md): step-by-step
  rollout from offline demo to CI and controlled apply.
- [`docs/import-adoption-recipes.md`](docs/import-adoption-recipes.md):
  practical import, ownership, data cells filter, and environment promotion
  recipes.
- [`docs/exception-lifecycle.md`](docs/exception-lifecycle.md): request,
  review, CI, expiry, and removal workflow for risky access exceptions.
- [`docs/permission-request-bundles.md`](docs/permission-request-bundles.md):
  modeling repeated access requests as policy data without building approval UI
  into core.
- [`docs/lake-formation-guide.md`](docs/lake-formation-guide.md): Lake
  Formation mental model, LF-Tag best practices, hybrid access notes, and
  antipatterns.
- [`docs/tag-permission-matrix.md`](docs/tag-permission-matrix.md): effective
  LF-Tag inheritance, expression matching, grant shapes, column override cases,
  and permission/resource combinations.
- [`docs/policy-authoring-direction.md`](docs/policy-authoring-direction.md):
  Python-native permission group authoring layer with reader, editor,
  table creator, and database creator templates.
- [`docs/report-formats.md`](docs/report-formats.md): JSON and Markdown report
  shapes for audits, explains, plans, applies, and CI artifacts.
- [`docs/architecture.md`](docs/architecture.md): package boundaries, data
  flow, public API, and AWS adapter responsibilities.
- [`docs/roadmap.md`](docs/roadmap.md): release scope, near-term priorities,
  non-goals, and good first contribution areas.
- [`docs/safety-model.md`](docs/safety-model.md): conservative defaults,
  destructive-change flags, apply behavior, and production patterns.
- [`docs/positioning.md`](docs/positioning.md): where `lfguard` fits next to
  Terraform, CloudFormation, CDK, raw boto3, and console workflows.
- [`docs/terraform-cdk-coexistence.md`](docs/terraform-cdk-coexistence.md):
  detailed ownership split and pipeline pattern for IaC-managed environments.
- [`docs/state-format.md`](docs/state-format.md): desired/current state file
  shape with examples for each supported resource kind.
- [`docs/schema.json`](docs/schema.json): JSON Schema for desired/current state
  files.
- [`docs/aws-api-coverage.md`](docs/aws-api-coverage.md): exact boto3 Lake
  Formation calls used for live inventory and apply.
- [`docs/faq.md`](docs/faq.md): answers for safety, AWS credentials, scope, and
  adoption questions.
- [`docs/troubleshooting.md`](docs/troubleshooting.md): common install, AWS,
  planning, and CI issues.
- [`docs/github-actions.md`](docs/github-actions.md): copy-paste drift check
  and Code Scanning workflows using GitHub OIDC, job summaries, SARIF, and
  uploaded report artifacts.
- [`docs/aws-permissions.md`](docs/aws-permissions.md): suggested minimum IAM
  permissions and preflight checks for read-only and apply roles.
- [`docs/testing.md`](docs/testing.md): default tests, botocore Stubber
  contract tests, Moto emulator tests, and opt-in live AWS contract tests.
- [`examples/README.md`](examples/README.md): offline files, commands,
  copyable GitHub Actions workflows, and a pre-commit hook example.

## Development

```bash
python -m pip install -e ".[dev,aws,yaml]"
python -m unittest discover -s tests
python -m build
```

See [`docs/testing.md`](docs/testing.md) for the layered test strategy:
botocore `Stubber` contract tests, optional Moto emulator tests, and opt-in
live AWS contract tests for Lake Formation behavior that emulators cannot prove.
