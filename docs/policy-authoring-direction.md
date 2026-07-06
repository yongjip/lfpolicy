# Policy Authoring Direction

`lfguard` should stay small and opinionated. The high-level policy layer should
make common data governance roles easy to define while keeping dangerous Lake
Formation combinations out of normal authoring.

## Decision

Use a Python-native policy builder as the source of truth for permission groups.
Generate normal `DesiredState` JSON or YAML from it.

```text
policy.py -> generated desired.json -> lfguard check/audit/plan/review
```

Do not build a large YAML DSL. YAML is still useful as the generated review
artifact, but Python should own the reusable policy logic.

## Core Concepts

| Concept | Meaning |
| --- | --- |
| Tag key | LF-Tag key, allowed values, and where the tag may be assigned. |
| Resource tag assignment | Explicit LF-Tag assignment to a database, table, or set of columns. |
| Permission group | User-defined group name such as `dataconsumer`, `dataengineer`, `datasteward`, `operations`, or `catalog_admin`. |
| Permission template | Package-defined behavior such as `reader()`, `producer()`, `steward()`, `admin()`, or `data_location_access()`. |
| IAM role binding | Assignment from an IAM role to one or more permission groups. Treat IAM roles as the execution/user-group boundary. |
| Generated desired state | The normal `lfguard` desired policy produced by the builder. |

Permission group names are not enums. Companies should define their own group
names. The package only defines the safe behavior templates.

## Templates

| Template | Catalog permissions | Database permissions | Table permissions | Filter rule |
| --- | --- | --- | --- | --- |
| `reader()` | none | `DESCRIBE` | `SELECT`, `DESCRIBE` | May use tags that can narrow columns. |
| `editor()` | none | `DESCRIBE` | `SELECT`, `DESCRIBE`, `INSERT`, `DELETE` | Must not use tags assignable to columns. |
| `producer()` | none | `DESCRIBE`, `CREATE_TABLE` | `SELECT`, `DESCRIBE`, `INSERT`, `DELETE` | Must not use tags assignable to columns. |
| `table_creator()` | none | `DESCRIBE`, `CREATE_TABLE` | `SELECT`, `DESCRIBE`, `INSERT`, `DELETE` | Must not use tags assignable to columns. |
| `database_creator()` | `CREATE_DATABASE` | none directly | none directly | Cannot use LF-Tag filters. |
| `steward("expr")` | none | none directly | none directly | Direct named LF-Tag expression grant; cannot use LF-Tag filters. |
| `data_location_access("arn")` | none | none directly | none directly | Direct data-location grant; cannot use LF-Tag filters. |
| `admin()` | `CREATE_DATABASE`, `CREATE_LF_TAG`, `CREATE_LF_TAG_EXPRESSION`, `DESCRIBE` | none directly | none directly | Cannot use LF-Tag filters. |

No template grants `ALL`, `SUPER`, `ALTER`, `DROP`, grant option, broad-principal
access, or Lake Formation data lake administrator authority.

`database_creator()` and `admin()` are still powerful. AWS grants
`CREATE_DATABASE` on the catalog, and database creators receive follow-on
metadata authority on databases they create. Use self-describing group names
such as `catalog_onboarding`, `tag_stewards`, or `platform_admins`.

The hard rule is:

```text
reader may be column-filtered
editor, producer, and table_creator must stay whole-table
direct bundles cannot use LF-Tag filters
database_creator and admin are explicit catalog-level power
```

## Tag Scope

The tag assignment scope is enough to determine whether a tag can narrow
columns.

```python
from lakeformation_guard.policy import LakePolicy, TagAssignmentScope

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
```

`contains_pii` is valid catalog metadata at database, table, and column scope.
Because it may be assigned to columns, it can narrow table access to a subset of
columns. `reader()` may use it. `editor()`, `producer()`, and
`table_creator()` may not.
When a reader filter key is also assignable to databases, the builder can use
that same key for database `DESCRIBE` and table `SELECT`/`DESCRIBE`.

Catalog-scoped policies can attach `catalog_id` to tag definitions, resource
tag assignments, and permission templates:

```python
policy.tag_key(
    "domain",
    catalog_id="111122223333",
    values=["sales"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
)
policy.tag_database("sales_curated", catalog_id="111122223333", domain="sales")
policy.group("dataconsumer", reader(catalog_id="111122223333").where(domain="sales"))
```

Use `catalog_id` on `reader()`, `editor()`, `producer()`, and
`table_creator()` when the generated LF-Tag policy grants must target a
specific catalog. `database_creator(catalog_id=...)`, `admin(catalog_id=...)`,
`steward(..., catalog_id=...)`, and `data_location_access(..., catalog_id=...)`
produce scoped direct grants. If the same tag key is defined in multiple
catalogs, unscoped permission groups must be made explicit with `catalog_id`.

Resource tags use the same scope declaration:

```python
policy.tag_database("sales_curated", domain="sales", contains_pii="false")
policy.tag_table("sales_curated", "customers", contains_pii="false")
policy.tag_columns("sales_curated", "customers", "phone_number", contains_pii="true")
```

Use mapping form when an LF-Tag key is not a valid Python keyword argument:

```python
policy.group("dataconsumer", reader().where({"data-domain": "sales"}))
policy.tag_database("sales_curated", tags={"data-domain": "sales"})
```

The builder rejects a resource assignment when the tag key is undefined, the
value is not in the tag definition, or the tag key is not assignable to that
resource level.

## Named LF-Tag Expressions

Some services treat a named LF-Tag expression as the reusable governance object:
define the expression once, then grant principals by `ExpressionName`. Use
`as_named_expression(...)` on a filtered permission group when that shape is the
desired contract:

```python
policy.group("analytics", reader().where(domain="sales")).as_named_expression(
    name="AnalyticsReaders",
    description="Reusable analytics reader expression",
)
policy.bind_role("arn:aws:iam::111122223333:role/Analyst", "analytics")
```

The compile step emits both:

- `lf_tag_expressions.AnalyticsReaders` with the group's declared filter; and
- database/table LF-Tag policy grants whose resources reference
  `expression_name: "AnalyticsReaders"`.

This remains pure desired-state authoring. It does not call AWS and does not
change the service boundary: the consuming service owns approval, IAM
credentials, audit storage, and any eventual grant execution. Since one named
expression backs both the database and table grants, every filter key in that
group must be assignable to databases.

## Import to Python Migration

Use `lfguard import` as a scaffold, then convert only the owned surface into
Python policy. Keep the import beside the new policy until reviewers agree the
generated desired state covers the intended resources and grants.

```bash
lfguard import \
  --catalog-id 111122223333 \
  --include lf-tags,lf-tag-expressions,data-cells-filters,resource-tags,grants \
  --output policy/imported-desired.json

lfguard generate policy.py --output-file policy/desired.json --force
lfguard check --desired policy/desired.json --fail-on-findings
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --output json \
  --output-file artifacts/lfguard-plan.json
```

Convert in this order:

1. Copy LF-Tag keys and allowed values into `policy.tag_key(...)`.
2. Copy database, table, and column tag assignments into `tag_database()`,
   `tag_table()`, and `tag_columns()`.
3. Replace repeated LF-Tag policy grants with group definitions such as
   `reader().where(...)` or `producer().where(...)`.
4. Replace direct data-location grants with `data_location_access(...)`.
5. Bind reviewed principals with `bind_role(...)`.
6. Compare generated `policy/desired.json` with the imported scaffold and keep
   unmanaged legacy grants outside the generated policy.

See [`../examples/policy-from-import.py`](../examples/policy-from-import.py)
for a runnable example that keeps an `IMPORTED_DESIRED_REFERENCE` dictionary in
the source file while modeling the owned policy as `LakePolicy` declarations.

## Generic Example

Use neutral examples in public docs and tests. Avoid company-specific database
names, role names, and data domains.

```python
from lakeformation_guard.policy import (
    LakePolicy,
    TagAssignmentScope,
    admin,
    data_location_access,
    database_creator,
    editor,
    producer,
    reader,
    steward,
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
policy.tag_database("platform_ops", domain="platform", contains_pii="false")
policy.tag_table("platform_ops", "jobs", contains_pii="false")

policy.group("dataconsumer", reader().where(domain="sales", contains_pii="false"))
policy.group("dataengineer", producer().where(domain="sales"))
policy.group("operations", editor().where(domain="platform"))
policy.group("tag_stewards", steward("sales_tables"))
policy.group("ingest_locations", data_location_access("arn:aws:s3:::analytics-lake/raw/"))
policy.group("catalog_onboarding", database_creator())
policy.group("platform_admins", admin())

policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")
policy.bind_role("arn:aws:iam::111122223333:role/DataEngineer", "dataengineer")
policy.bind_role("arn:aws:iam::111122223333:role/Operations", "operations")
policy.bind_role("arn:aws:iam::111122223333:role/DataSteward", "tag_stewards")
policy.bind_role("arn:aws:iam::111122223333:role/IngestRole", "ingest_locations")
policy.bind_role("arn:aws:iam::111122223333:role/CatalogAdmin", "catalog_onboarding")
policy.bind_role("arn:aws:iam::111122223333:role/PlatformAdmin", "platform_admins")

policy.write_desired("policy/desired.json")
```

Or generate through the CLI:

```bash
lfguard generate policy.py --output-file policy/desired.json
lfguard generate policy.py --output-file policy/desired.json --check
lfguard check --desired policy/desired.json --fail-on-findings
```

Generated YAML includes a header when you choose a `.yaml` or `.yml` output
file:

```yaml
# Generated by policy.py. Do not edit directly.
```

## Validation Feedback

Use `validate_findings()` when an internal platform wants structured authoring
feedback before writing generated desired state:

```python
findings = policy.validate_findings()
for finding in findings:
    print(finding.code, finding.path, finding.message)
```

`validate()` and `to_desired_state()` raise `PolicyValidationError` when those
findings are present. The error includes stable finding codes, field paths such
as `groups.dataconsumer.filters.domain`, the human message, and a suggested
fix. `lfguard generate` prints that same detail without a Python traceback.

## Guardrails

The builder fails before generating desired state when it sees:

- `editor()`, `producer()`, or `table_creator()` using a tag key assignable to
  columns;
- `database_creator()` with LF-Tag filters;
- direct bundles such as `steward()`, `admin()`, or `data_location_access()`
  with LF-Tag filters;
- permission groups without tag filters, except `database_creator()`;
- role bindings to undefined permission groups;
- tag filters using undefined tag keys or values;
- resource tag assignments using undefined keys, undefined values, or a scope
  the tag key does not support;
- generated desired state that fails `lint_desired()` with errors.

The generated desired state writes optional `lf_tag_key_metadata` so the
low-level linter can distinguish table-wide generated grants from grants that
may narrow columns. The linter remains conservative for hand-written desired
state. If it does not have tag assignment metadata, it treats LF-Tag table
grants that combine `SELECT` with `INSERT`, `DELETE`, `ALTER`, or `DROP` as
potentially column-filtered and blocks them.

## Current Scope

- `lakeformation_guard.policy` module.
- `LakePolicy`, `TagKey`, `PermissionGroup`, `RoleBinding`.
- `TagAssignmentScope` enum.
- Templates: `reader()`, `editor()`, `producer()`, `table_creator()`,
  `database_creator()`, `steward()`, `admin()`, and
  `data_location_access()`.
- Resource tagging helpers: `tag_database()`, `tag_table()`, `tag_columns()`.
- `LakePolicy.to_desired_state()`.
- `LakePolicy.write_desired()`.
- Optional LF-Tag assignment metadata in generated desired state.
- Documentation and tests with generic examples.

Defer UI, SQL analysis, account-wide discovery, and organization-specific
permission templates.
