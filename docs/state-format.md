# State File Format

`lfguard` desired-state and current-snapshot files use the same JSON/YAML shape.
Desired files describe what should exist; current snapshots describe what exists
now.

```json
{
  "lf_tags": {},
  "lf_tag_expressions": {},
  "data_cells_filters": [],
  "lf_tag_key_metadata": {},
  "resource_tags": [],
  "grants": [],
  "lint": {},
  "ownership": {},
  "ignore": {},
  "exceptions": []
}
```

All top-level sections are optional, but real policies normally use at least one
of them.

## LF-Tag Definitions

Use `lf_tags` to define LF-Tag keys and allowed values:

```json
{
  "lf_tags": {
    "domain": ["sales", "finance"],
    "sensitivity": ["public", "internal", "restricted"]
  }
}
```

The equivalent list form is also accepted:

```json
{
  "lf_tags": [
    {"key": "domain", "values": ["sales", "finance"]},
    {"key": "sensitivity", "values": ["public", "internal", "restricted"]}
  ]
}
```

Use list form or object values when the same LF-Tag key must be managed in
multiple Glue Data Catalogs:

```json
{
  "lf_tags": [
    {"key": "domain", "catalog_id": "111122223333", "values": ["sales"]},
    {"key": "domain", "catalog_id": "444455556666", "values": ["finance"]}
  ]
}
```

The mapping form can also carry a catalog ID for one key:

```json
{
  "lf_tags": {
    "domain": {
      "catalog_id": "111122223333",
      "values": ["sales", "finance"]
    }
  }
}
```

## Named LF-Tag Expressions

Use `lf_tag_expressions` to manage AWS Lake Formation named LF-Tag expressions.
The name is later referenced from LF-Tag policy grants with `expression_name`.

```json
{
  "lf_tag_expressions": {
    "sales_internal": {
      "description": "Sales tables with public or internal sensitivity",
      "expression": {
        "domain": ["sales"],
        "sensitivity": ["public", "internal"]
      }
    }
  }
}
```

The equivalent list form is also accepted:

```json
{
  "lf_tag_expressions": [
    {
      "name": "sales_internal",
      "expression": [
        {"key": "domain", "values": ["sales"]},
        {"key": "sensitivity", "values": ["public", "internal"]}
      ]
    }
  ]
}
```

Single values may be written as strings anywhere a value list is accepted.

## Data Cells Filter Definitions

Use `data_cells_filters` to manage Lake Formation row and column filter
definitions. The `catalog_id` field maps to AWS `TableCatalogId` and is
required for data cells filter review/request evidence.

```json
{
  "data_cells_filters": [
    {
      "name": "orders_public",
      "catalog_id": "111122223333",
      "database": "analytics",
      "table": "orders",
      "row_filter": "country = 'US'",
      "columns": ["order_id", "status"]
    }
  ]
}
```

Use `all_rows: true` when the filter should not narrow rows, and use
`excluded_columns` when it should expose all columns except a denied subset:

```json
{
  "data_cells_filters": [
    {
      "name": "orders_internal",
      "catalog_id": "111122223333",
      "database": "analytics",
      "table": "orders",
      "all_rows": true,
      "excluded_columns": ["internal_notes"]
    }
  ]
}
```

`row_filter` and `all_rows` are mutually exclusive. `columns` and
`excluded_columns` are also mutually exclusive. Exact duplicate identities
`(catalog_id, database, table, name)` are rejected by validation and lint.
Imported AWS `VersionId` values may appear in snapshots or scaffolded state for
evidence, but they are treated as provider metadata rather than policy drift.

## LF-Tag Key Metadata

Generated policy files may include `lf_tag_key_metadata`. This section is not
read from AWS; it records where a tag key may be assigned so `lfguard` can tell
whether an LF-Tag table policy might narrow access to matching columns.

```json
{
  "lf_tag_key_metadata": {
    "domain": {"assignable_to": ["database", "table"]},
    "contains_pii": {"assignable_to": ["database", "table", "column"]}
  }
}
```

The equivalent list form is also accepted:

```json
{
  "lf_tag_key_metadata": [
    {"key": "domain", "assignable_to": ["database", "table"]},
    {"key": "contains_pii", "assignable_to": ["database", "table", "column"]}
  ]
}
```

When this metadata is absent, the linter stays conservative for LF-Tag table
grants that combine `SELECT` with mutation permissions.
When this metadata is present, the linter also checks resource tag assignments
against the declared scopes. For example, a key declared as assignable only to
`database` and `table` cannot be assigned to a `table_with_columns` resource.

## Resource Tag Assignments

Use `resource_tags` to attach LF-Tags to Data Catalog resources:

```json
{
  "resource_tags": [
    {
      "resource": {
        "kind": "table",
        "database": "analytics",
        "table": "orders"
      },
      "tags": {
        "domain": ["sales"],
        "sensitivity": ["internal"]
      }
    }
  ]
}
```

AWS Lake Formation stores LF-Tag keys and values in lower case and allows only
one value for a given LF-Tag key on a single resource. Keep desired resource
assignments to one lower-case value per key. Use multiple values only in
`lf_tags` definitions or LF-Tag policy expressions.

Supported resource kinds are shown below. `catalog_id` is optional for each
resource kind when you need to target a specific Glue Data Catalog. LF-Tag
assignments are valid on databases, tables, and columns; `lfguard` lints
resource tag assignments on other resource kinds as errors.

### Catalog

```json
{"kind": "catalog"}
```

With an explicit catalog:

```json
{"kind": "catalog", "catalog_id": "111122223333"}
```

### Database

```json
{
  "kind": "database",
  "database": "analytics"
}
```

### Table

```json
{
  "kind": "table",
  "database": "analytics",
  "table": "orders"
}
```

### Table Columns

```json
{
  "kind": "table_with_columns",
  "database": "analytics",
  "table": "orders",
  "columns": ["order_id", "customer_id"]
}
```

For AWS `TableWithColumns` grants that use `ColumnWildcard`, use
`column_wildcard: true`. Add `excluded_columns` when the grant exposes all
columns except a denied subset:

```json
{
  "kind": "table_with_columns",
  "database": "analytics",
  "table": "orders",
  "column_wildcard": true,
  "excluded_columns": ["internal_notes"]
}
```

### Data Location

```json
{
  "kind": "data_location",
  "location": "arn:aws:s3:::analytics-lake/raw/"
}
```

### Data Cells Filter

Data cells filter resources are used for grants on existing Lake Formation row
and column filters. `catalog_id` maps to the filter's `TableCatalogId` and must
be explicit because lfguard does not infer it from runtime AWS credentials.

```json
{
  "kind": "data_cells_filter",
  "catalog_id": "111122223333",
  "database": "analytics",
  "table": "orders",
  "filter_name": "orders_public"
}
```

### LF-Tag Policy

LF-Tag policy resources are used for grants. `resource_type` must be `DATABASE`
or `TABLE`. Multiple values for one key are OR, multiple keys are AND, and `*`
means all values for a key in an LF-Tag policy grant. Use either inline
`expression` or a named `expression_name`, but not both.
See [`tag-permission-matrix.md`](tag-permission-matrix.md) for inheritance and
permission examples.

```json
{
  "kind": "lf_tag_policy",
  "resource_type": "TABLE",
  "expression": {
    "domain": ["sales"],
    "sensitivity": ["public", "internal"]
  }
}
```

Named-expression form:

```json
{
  "kind": "lf_tag_policy",
  "resource_type": "TABLE",
  "expression_name": "sales_internal"
}
```

Expression list form is also accepted:

```json
{
  "kind": "lf_tag_policy",
  "resource_type": "TABLE",
  "expression": [
    {"key": "domain", "values": ["sales"]},
    {"key": "sensitivity", "values": ["public", "internal"]}
  ]
}
```

### LF-Tag Expression

LF-Tag expression resources are used when granting permissions on a named
LF-Tag expression itself, for example stewardship permissions that let another
principal delegate access through that expression.

```json
{
  "kind": "lf_tag_expression",
  "expression_name": "sales_internal"
}
```

## Grants

Use `grants` to declare Lake Formation permissions for a principal and resource:

```json
{
  "grants": [
    {
      "principal": "arn:aws:iam::111122223333:role/Analyst",
      "resource": {
        "kind": "database",
        "database": "analytics"
      },
      "permissions": ["DESCRIBE"]
    }
  ]
}
```

Grantable permissions are optional. They are automatically included in
`permissions` during normalization:

```json
{
  "principal": "arn:aws:iam::111122223333:role/DataAdmin",
  "resource": {
    "kind": "table",
    "database": "analytics",
    "table": "orders"
  },
  "permissions": ["SELECT", "DESCRIBE"],
  "grantable_permissions": ["SELECT"]
}
```

Use LF-Tag policy grants for attribute-based access:

```json
{
  "principal": "arn:aws:iam::111122223333:role/Analyst",
  "resource": {
    "kind": "lf_tag_policy",
    "resource_type": "TABLE",
    "expression": {
      "domain": ["sales"],
      "sensitivity": ["public", "internal"]
    }
  },
  "permissions": ["SELECT", "DESCRIBE"]
}
```

Use named LF-Tag expressions when the same expression is shared by multiple
grants:

```json
{
  "principal": "arn:aws:iam::111122223333:role/Analyst",
  "resource": {
    "kind": "lf_tag_policy",
    "resource_type": "TABLE",
    "expression_name": "sales_internal"
  },
  "permissions": ["SELECT", "DESCRIBE"]
}
```

## Lint, Ownership, and Ignore Config

Strict lint severities remain the default. Override a rule only when an existing
environment needs gradual cleanup:

```json
{
  "lint": {
    "lf_tag_case_normalization": "warning",
    "broad_permission_grant": "error",
    "named_resource_grant_review": "ignore"
  }
}
```

Use ownership boundaries and ignore rules to keep unmanaged current-state drift
visible only where `lfguard` is intended to manage it:

```json
{
  "ownership": {
    "managed_principals": ["arn:aws:iam::*:role/data-*"],
    "managed_resources": [{"kind": "database", "database": "analytics_*"}],
    "unmanaged_action": "warn"
  },
  "ignore": {
    "principals": ["IAM_ALLOWED_PRINCIPALS"],
    "resources": [{"database": "legacy_*"}]
  }
}
```

`unmanaged_action` accepts `warn`, `error`, or `ignore`. Principal and resource
patterns use shell-style wildcards. A resource pattern can constrain only the
fields it names, so `{"database": "legacy_*"}` matches database-scoped resources
with that database name even when the resource kind is `table` or
`table_with_columns`. Patterns can also use `filter_name` for
`data_cells_filter` grants. Use `{"kind": "database", "database": "legacy_*"}`
when the kind itself should also be constrained.

## Policy Exceptions

Use `exceptions` for intentional governance exceptions that should be reviewable
without globally weakening a lint rule. Exceptions are scoped to one principal
pattern, may also constrain a resource pattern and permissions, and must include
a reason, ticket, owner, approver, and expiry date.

```json
{
  "exceptions": [
    {
      "principal": "arn:aws:iam::111122223333:role/DataAdmin",
      "resource": {
        "kind": "database",
        "database": "analytics"
      },
      "permissions": ["ALL"],
      "rules": [
        "allow_broad_permissions",
        "allow_named_resource_grants"
      ],
      "reason": "break-glass database administration",
      "ticket": "SEC-123",
      "owner": "data-platform",
      "expires_at": "2099-12-31",
      "approved_by": "data-governance"
    }
  ]
}
```

Supported rules are:

- `allow_broad_principals`
- `allow_broad_permissions`
- `allow_mutating_permissions`
- `allow_grantable_permissions`
- `allow_named_resource_grants`
- `allow_lf_tag_policy_select_mutation`
- `allow_column_filter_mutation`

Expired exceptions do not suppress lint findings and are reported as
`POLICY_EXCEPTION_EXPIRED`. Exceptions expiring within 14 days are reported as
`POLICY_EXCEPTION_EXPIRING_SOON`. Undefined LF-Tags, undefined named LF-Tag
expressions, duplicate identities, and malformed state remain hard errors rather
than exception-controlled policy choices.

## Normalization

`lfguard` normalizes state files before auditing or planning:

- resource kinds are lowercased and hyphen-insensitive, so `table-with-columns`
  is read as `table_with_columns`;
- permissions are uppercased;
- repeated values are deduplicated and sorted;
- empty strings are ignored in value lists;
- unsupported resource kinds or missing required fields fail validation with
  exit code `2`.

Run this before CI drift checks:

```bash
lfguard validate --desired policy/desired.json
```

For editor integration, export the JSON Schema:

```bash
lfguard schema --output-file policy/lfguard.schema.json
```
