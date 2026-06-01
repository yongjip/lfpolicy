# LF-Tag and Permission Matrix

This guide maps the practical combinations of AWS Lake Formation LF-Tags,
resource grants, and permissions. Use it when reviewing a desired-state file or
explaining why a principal can see a database, a table, only some columns, or
nothing.

## Fast Answer

When a table has `k=a` and one column has `k=b` for the same LF-Tag key:

- the table's effective value is `k=a`;
- normal columns inherit `k=a`;
- the explicitly tagged column's effective value is `k=b`;
- the explicitly tagged column does not have both `k=a` and `k=b`;
- an LF-Tag policy grant for `k=a` can match the table and inherited columns,
  but not the overridden column;
- an LF-Tag policy grant for `k=b` can match the overridden column.

If the table has `k=a` and the column has a different key such as `j=b`, the
column keeps inherited `k=a` and also has explicit `j=b`.

## Reading Rules

- IAM and Lake Formation both matter. IAM must allow the API call, and Lake
  Formation must allow the catalog resource or data access.
- Named resource grants ignore LF-Tags. They apply to the named catalog,
  database, table, column set, or data location.
- LF-Tag policy grants match effective LF-Tags on databases, tables, views, or
  columns.
- LF-Tag keys and values are stored lower-case by AWS. Keep desired state
  lower-case.
- A resource can have at most one value for a given LF-Tag key.
- Multiple values for one key in an LF-Tag expression are OR.
- Multiple keys in one LF-Tag expression are AND.
- `*` in an LF-Tag policy grant means all values for that key.
- Named grants and LF-TBAC grants union together. A named table grant can add
  permissions even when an LF-Tag policy would not match that table.

## Assignment Possibilities

LF-Tags can be defined, assigned, inherited, overridden, and used in grants.
Those are separate operations.

| Operation | Resource | Result |
| --- | --- | --- |
| Define LF-Tag key/value | LF-Tag catalog | Makes a key and its allowed values available for assignment or LF-Tag policy expressions. |
| Assign tag | Database | Database has the tag; tables inherit it unless they override the same key; columns inherit through their table. |
| Assign tag | Table | Table has the tag; columns inherit it unless they override the same key. A table assignment overrides a database assignment for the same key. |
| Assign tag | Column | Only that column has the explicit tag. A column assignment overrides a table assignment for the same key. |
| Remove explicit tag | Database/table/column | The resource falls back to inherited values from its parent, if any. |
| Delete LF-Tag value/key | LF-Tag catalog | AWS does not first check whether the value/key is still assigned. Matching grants can stop matching. |
| Grant on named resource | Catalog/database/table/columns/location | Applies to that named resource shape without evaluating LF-Tags. |
| Grant on LF-Tag policy | Matching databases/tables/views/columns | Applies when the resource's effective LF-Tags match the expression. |

## Effective Tag Values

Effective tag values are the values AWS evaluates after inheritance and
overrides are applied.

## Same-Key Inheritance Matrix

For one LF-Tag key, the nearest explicit assignment wins.

| Database tag | Table tag | Column tag | Effective table value | Effective column value |
| --- | --- | --- | --- | --- |
| none | none | none | none | none |
| `k=a` | none | none | `a` | `a` |
| `k=a` | `k=b` | none | `b` | `b` |
| `k=a` | none | `k=c` | `a` | `c` |
| `k=a` | `k=b` | `k=c` | `b` | `c` |
| none | `k=b` | none | `b` | `b` |
| none | `k=b` | `k=c` | `b` | `c` |

Same key: table `k=a`, column `k=b` means `k=b` replaces `k=a` for that column.
It is not a two-value tag assignment.

## Different-Key Inheritance Matrix

If the lower-level resource uses a different key, it keeps inherited keys and
adds the new key.

| Table tag | Column tag | Effective column tags |
| --- | --- | --- |
| `sensitivity=internal` | `domain=sales` | `sensitivity=internal`, `domain=sales` |
| `domain=sales` | `sensitivity=restricted` | `domain=sales`, `sensitivity=restricted` |

Removing an explicit lower-level assignment restores inheritance from the
parent. For example, if a table has `k=a`, a column override has `k=b`, and the
column assignment is removed, the column goes back to effective `k=a`.

## Expression Matching

| LF-Tag expression | Matches |
| --- | --- |
| `domain=sales` | Resources with effective `domain=sales`. |
| `domain=sales|finance` | Resources with effective `domain=sales` OR `domain=finance`. |
| `domain=sales AND sensitivity=internal` | Resources with both effective tags. |
| `domain=sales|finance AND sensitivity=internal` | Sales or finance resources that are also internal. |
| `domain=*` | Resources with the `domain` key and any value. |
| `domain=sales` and separate grant `sensitivity=internal` | Resources that match either grant. Separate grants union; they are not one AND expression. |
| `domain=sales AND region=us` | Does not match a resource that has only `domain=sales`. Missing keys fail the expression. |

An expression does not match resources where the key is absent. `domain=*`
matches any value for `domain`, but it still requires the resource to have the
`domain` key.

## Grant Shape Matrix

| Grant shape | Tag evaluation | Typical use | `lfguard` stance |
| --- | --- | --- | --- |
| Named catalog grant | None. The grant names the catalog. | Catalog-level administration such as `CREATE_DATABASE`. | Supported, but broad grants are linted when risky. |
| Named database grant | None. The grant names the database. | Small exceptions or migration support. | Supported as an exception; routine named database grants are lint errors unless excepted. |
| Named table grant | None. The grant names the table. | Small exceptions or emergency repair. | Supported as an exception; routine named table grants are lint errors unless excepted. |
| Named table-with-columns grant | None. The grant names included columns. | Column-filtered `SELECT`. | Supported with included columns. |
| Named data-location grant | None. The grant names an S3 location resource. | Registering and writing table data in controlled workflows. | Supported. |
| LF-Tag policy for `DATABASE` | Matches effective database LF-Tags. | Attribute-based database `DESCRIBE`, `CREATE_TABLE`, or controlled database administration. | Preferred for scalable database access. |
| LF-Tag policy for `TABLE` | Matches effective table, view, and column LF-Tags. | Attribute-based table/view access and column-sensitive `SELECT`. | Preferred for scalable table access. |
| LF-Tag value permission | Grants authority on the tag/value itself, not data. | Allowing stewards to describe, assign, or delegate tag expressions. | Not modeled as desired grants. |

Named and LF-TBAC grants union together. For example, a principal with
`SELECT` from an LF-Tag policy and `INSERT` from a named table grant can have
both effective permissions on that table.

## Table and Column Scenarios

Assume table `orders` has columns `id`, `amount`, and `email`.

| Scenario | Grant | Result |
| --- | --- | --- |
| Table has `sensitivity=internal`; no column overrides. | `SELECT` on LF-Tag policy `sensitivity=internal` | Principal can select `id`, `amount`, and `email`. |
| Table has `sensitivity=internal`; column `email` has `sensitivity=restricted`. | `SELECT` on `sensitivity=internal` | Principal can select `id` and `amount`, not `email`. |
| Same table and column tags. | `SELECT` on `sensitivity=restricted` | Principal can select `email` only. |
| Same table and column tags. | `DESCRIBE` on `sensitivity=restricted` | Principal can see matching column metadata, subject to the calling service's metadata behavior. |
| Same table and column tags. | `ALTER`, `DROP`, `INSERT`, or `DELETE` through only the restricted column match | AWS does not grant those full-table permissions from a partial-column LF-Tag match; only `DESCRIBE` is granted. `lfguard` blocks LF-Tag table policies that combine `SELECT` with these permissions. |
| Same table and column tags. | `ALL`/`SUPER` through only the restricted column match | AWS reduces the effective LF-TBAC result to `SELECT` and `DESCRIBE` for the matching subset. `lfguard` still blocks `ALL`/`SUPER` in desired policy. |
| Table has `domain=sales`; column `email` has `sensitivity=restricted`. | `SELECT` on `domain=sales AND sensitivity=restricted` | Matches `email` only if the column also effectively has `domain=sales` through inheritance. |
| Table has `domain=sales`; column `email` has `domain=privacy`. | `SELECT` on `domain=sales` | Does not match `email`; the column override changes the effective value for that key. |
| Table has `domain=sales`; column `email` has `domain=privacy`. | `SELECT` on `domain=privacy` | Matches `email` only. |
| Table has `domain=sales`; column `email` has `domain=privacy`; named table grant gives `SELECT`. | Named `SELECT` on table | Principal can select all table columns because the named grant does not evaluate LF-Tags. |

Column-level access is primarily a `SELECT` concern. AWS allows `SELECT` with
column filtering, but a principal with partial-column `SELECT` cannot also be
granted `ALTER`, `DROP`, `DELETE`, or `INSERT` on the same table. The reverse is
also true: table-level `ALTER`, `DROP`, `DELETE`, or `INSERT` conflicts with
column-filtered `SELECT`.

## Effective Access Matrix

This matrix answers the common same-key table/column override case.

| Table tags | Column `email` tags | Grant | Effective result |
| --- | --- | --- | --- |
| `k=a` | none | LF-Tag policy `k=a`, `SELECT` | All columns match. |
| `k=a` | `k=b` | LF-Tag policy `k=a`, `SELECT` | All inherited `k=a` columns match; `email` does not. |
| `k=a` | `k=b` | LF-Tag policy `k=b`, `SELECT` | Only `email` matches. |
| `k=a` | `k=b` | LF-Tag policy `k=a|b`, `SELECT` | All columns match because either value is accepted. |
| `k=a` | `k=b` | LF-Tag policy `k=*`, `SELECT` | All columns with key `k` match, including `email`. |
| `k=a` | `j=b` | LF-Tag policy `k=a AND j=b`, `SELECT` | Only `email` matches because it inherits `k=a` and has `j=b`. |
| `k=a` | `j=b` | LF-Tag policy `j=b`, `SELECT` | Only `email` matches. |
| `k=a` | none | LF-Tag policy `j=b`, `SELECT` | Nothing matches; the `j` key is absent. |
| `k=a` | `k=b` | Named table `SELECT` | All columns match; tags are not evaluated. |

## Permission Matrix

This matrix describes AWS Lake Formation permission shapes and how `lfguard`
models them.

| Resource shape | AWS permissions | `lfguard` support |
| --- | --- | --- |
| Catalog / Data Catalog | `CREATE_DATABASE`; catalog also has `ALL`, `ALTER`, `DESCRIBE`, `DROP` in the AWS reference. | `catalog` grants are supported. |
| Database | `ALL`, `ALTER`, `CREATE_TABLE`, `DESCRIBE`, `DROP`. | `database` grants and `lf_tag_policy` with `resource_type=DATABASE` are supported. |
| Table | `ALL`, `ALTER`, `DELETE`, `DESCRIBE`, `DROP`, `INSERT`, `SELECT`. | `table` grants and `lf_tag_policy` with `resource_type=TABLE` are supported. |
| Table columns | `SELECT` with included or excluded columns. | `table_with_columns` grants with included columns are supported. |
| Data location | `DATA_LOCATION_ACCESS`. | `data_location` grants are supported. |
| LF-Tag policy - database | Database permissions on databases matching an LF-Tag expression. | Supported as `lf_tag_policy` with `resource_type=DATABASE`. |
| LF-Tag policy - table | Table permissions on tables/views/columns matching an LF-Tag expression. | Supported as `lf_tag_policy` with `resource_type=TABLE`. |
| LF-Tag values | `ASSOCIATE`, `DESCRIBE`, and grant-with-LF-Tag-expression permissions. | Not modeled as desired grants. Use native Lake Formation administration for LF-Tag permission delegation. |
| LF-Tags themselves | `ALTER`, `DROP`. | `lfguard` can create/update LF-Tag definitions during apply, but does not model administrative LF-Tag delegation grants. |
| Data filters / cell filters | `SELECT`, `DESCRIBE`, `DROP` on filtered table resources. | `data_cells_filter` grants and `data_cells_filters` definitions are supported, including row filters and included or excluded columns. |
| Resource links | `DESCRIBE`, `DROP`. | Not modeled separately. |

## Permission Behavior Matrix

| Permission | Primary meaning | Main resource shapes | Guardrail note |
| --- | --- | --- | --- |
| `DESCRIBE` | Read metadata and make catalog objects visible. | Catalog, database, table, resource link, LF-Tag. | Often paired with `SELECT`; still requires IAM API permissions. |
| `SELECT` | Query table data and view selected column metadata. | Table, table with column filter, LF-Tag policy table, data filter. | The only table data permission that naturally supports column filtering. |
| `CREATE_DATABASE` | Create metadata databases or resource links in the catalog. | Data Catalog/catalog. | Keep out of routine read roles; AWS gives creators follow-on metadata authority on databases they create. |
| `CREATE_TABLE` | Create tables in a database. | Database or LF-Tag policy database. | Mutating permission; isolate to producer/steward workflows. |
| `ALTER` | Change metadata for databases, tables, or LF-Tags. | Database, table, LF-Tag. | Mutating permission; partial-column LF-TBAC matches do not grant table `ALTER`. |
| `INSERT` | Insert/update/read data at a table's registered S3 location. | Table or LF-Tag policy table. | Mutating permission; conflicts with column-filtered `SELECT`. |
| `DELETE` | Delete/update/read data at a table's registered S3 location. | Table or LF-Tag policy table. | Mutating permission; conflicts with column-filtered `SELECT`. |
| `DROP` | Drop a catalog object or LF-Tag. | Database, table, resource link, LF-Tag, data filter. | Destructive; dropping a database drops its tables. |
| `DATA_LOCATION_ACCESS` | Use a registered S3 location for table data. | Data location. | Required for some producer workflows; not a table read permission by itself. |
| `ASSOCIATE` | Assign an LF-Tag value to a Data Catalog resource. | LF-Tag value. | Implicitly includes `DESCRIBE`; useful for delegated tag stewards. |
| `GrantWithLFTagExpression` | Delegate grants using the permitted LF-Tag expression. | LF-Tag value. | Treat as stewardship delegation, not routine reader access. |
| `ALL` / `SUPER` | Broad supported operations on the resource. | Catalog, database, table, LF-Tag policy resources. | `lfguard` treats this as an error because it hides the intended permission shape. |
| `SUPER_USER` | Super user on catalogs within a catalog resource. | Catalog. | Outside normal `lfguard` desired policy; review natively. |

## Grant Option

`grantable_permissions` means the principal can delegate those Lake Formation
permissions to another principal. Keep it rare. In `lfguard`, declare it only
when delegation is the intent:

```json
{
  "principal": "arn:aws:iam::111122223333:role/DataSteward",
  "resource": {
    "kind": "lf_tag_policy",
    "resource_type": "TABLE",
    "expression": {"domain": ["sales"]}
  },
  "permissions": ["SELECT", "DESCRIBE"],
  "grantable_permissions": ["SELECT"]
}
```

Do not use grant option with column-filtered `SELECT`; AWS does not allow grant
option when column filtering is applied.

## Controlled-Lake Guardrails

`lfguard lint` is intentionally opinionated. It reports errors for policy that
does not behave cleanly in AWS, such as mixed-case LF-Tags, multiple values for
one key on a resource, broad `IAMAllowedPrincipals` or `ALLIAMPrincipals`
grants, `ALL`/`SUPER` permissions, and LF-Tag `TABLE` policies that combine
`SELECT` with `ALTER`, `DROP`, `DELETE`, or `INSERT`.

That last rule is deliberately preventive. If a table has
`sensitivity=internal` and one column such as `phonenumber` overrides the same
key to `sensitivity=confidential`, an `internal` LF-Tag grant with `SELECT` can
become partial-column `SELECT`. Combining that with table-level mutation
permissions for the same LF-Tag policy creates the partial-column `SELECT`
illegal permission combinations this project blocks before apply.

It reports errors for policy that can be valid but must be explicit: mutating
permissions, grant option, and named database/table grants. Use scoped
`exceptions` with reason, expiry, and owner or approver metadata when these are
intentional. Wildcard LF-Tag policy values remain warnings. In CI,
`lfguard check --fail-on-findings` blocks both errors and warnings by default,
which keeps the lake closer to a controlled database permission model.

## Review Checklist

- Does every LF-Tag key/value in assignments and expressions exist in
  `lf_tags`?
- Are tag keys and values lower-case?
- Does each resource assign at most one value per key?
- Are column overrides intentional, especially for sensitive columns?
- Does every LF-Tag expression use OR within values and AND across keys
  intentionally?
- Is `*` used only when all values for a key are truly intended?
- Are partial-column `SELECT` grants kept separate from table-level mutation
  permissions?
- Do LF-Tag `TABLE` policies that combine `SELECT` with `INSERT`, `DELETE`,
  `ALTER`, or `DROP` use only tag keys that cannot be assigned to columns?
- Are destructive operations and grant-option delegation reviewed separately?

## Source References

- [AWS Lake Formation permissions reference](https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-reference.html)
- [Creating a database](https://docs.aws.amazon.com/lake-formation/latest/dg/creating-database.html)
- [Lake Formation tag-based access control](https://docs.aws.amazon.com/lake-formation/latest/dg/tag-based-access-control.html)
- [LF-Tag best practices and considerations](https://docs.aws.amazon.com/lake-formation/latest/dg/lf-tag-considerations.html)
- [Assigning LF-Tags to Data Catalog resources](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-assigning-tags.html)
- [Viewing LF-Tags assigned to a resource](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-view-resource-tags.html)
- [Creating LF-Tag expressions](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-creating-tag-expressions.html)
- [Granting data lake permissions using LF-TBAC](https://docs.aws.amazon.com/lake-formation/latest/dg/granting-catalog-perms-TBAC.html)
- [Managing LF-Tag value permissions](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-granting-tags.html)
- [Updating LF-Tags](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-updating-tags.html)
- [Deleting LF-Tags](https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-deleting-tags.html)
