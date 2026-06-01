# Policy Authoring Direction

`lfguard` should stay small and opinionated. The high-level policy layer should
make common data governance roles easy to define while keeping dangerous Lake
Formation combinations out of normal authoring.

## Decision

Use a Python-native policy builder as the source of truth for permission groups.
Generate normal `DesiredState` JSON or YAML from it.

```text
policy.py -> generated desired.json -> lfguard check/audit/plan/apply
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
