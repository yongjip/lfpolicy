# State File Format

`lfguard` desired-state and current-snapshot files use the same JSON/YAML shape.
Desired files describe what should exist; current snapshots describe what exists
now.

```json
{
  "lf_tags": {},
  "lf_tag_expressions": {},
  "lf_tag_key_metadata": {},
  "resource_tags": [],
  "grants": [],
  "lint": {},
  "ownership": {},
  "ignore": {}
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

### Data Location

```json
{
  "kind": "data_location",
  "location": "arn:aws:s3:::analytics-lake/raw/"
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
`table_with_columns`. Use `{"kind": "database", "database": "legacy_*"}` when
the kind itself should also be constrained.

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
