# AWS API Coverage

`lfguard` uses AWS APIs only when live inventory or execution is requested.
Most commands are fully offline: `sample`, `bootstrap`, `init`, `schema`,
`doctor`, `permissions`, `completion`, `check`, `validate`, `lint`, and
`summary` never call AWS. The `audit`, `plan`, and `apply` commands also stay
offline when `--current-snapshot` is provided.

The live adapter is intentionally small and uses only the Lake Formation client
from `boto3`.

## Live Inventory

These commands load live state when `--current-snapshot` is omitted:

- `lfguard audit`
- `lfguard plan`
- `lfguard apply`

`lfguard snapshot` always loads live state.

Live inventory is scoped by the desired-state file. `lfguard` asks AWS only for
the LF-Tags, resources, principals, and grants referenced by the desired state.
It does not perform full account-wide catalog discovery.

| Purpose | boto3 Lake Formation method | IAM action |
| --- | --- | --- |
| Read LF-Tag definitions named in desired state | `get_lf_tag` | `lakeformation:GetLFTag` |
| Read named LF-Tag expressions named in desired state or grants | `get_lf_tag_expression` | `lakeformation:GetLFTagExpression` |
| Read data cells filters named in desired state or grants | `get_data_cells_filter` | `lakeformation:GetDataCellsFilter` |
| Read LF-Tag assignments for desired resources and grant resources | `get_resource_lf_tags` | `lakeformation:GetResourceLFTags` |
| Read permissions for desired principal/resource pairs | `list_permissions` | `lakeformation:ListPermissions` |

`list_permissions` uses a paginator when the installed boto3 client exposes one
and falls back to manual `NextToken` paging otherwise.

## Live Import

`lfguard import` performs starter desired-state scaffolding from live AWS state.
It is intentionally named import, not sync, because the generated file still
needs human review before becoming owned desired state.

| Imported section | boto3 Lake Formation method | IAM action |
| --- | --- | --- |
| `lf-tags` | `list_lf_tags` | `lakeformation:ListLFTags` |
| `lf-tag-expressions` | `list_lf_tag_expressions` | `lakeformation:ListLFTagExpressions` |
| `data-cells-filters` | `list_data_cells_filter` for tables discovered from imported grants | `lakeformation:ListDataCellsFilter` |
| `grants` | `list_permissions` | `lakeformation:ListPermissions` |
| `resource-tags` | `get_resource_lf_tags` for resources discovered from imported grants | `lakeformation:GetResourceLFTags` |

`list_lf_tags`, `list_lf_tag_expressions`, `list_data_cells_filter`, and
`list_permissions` use paginators when available and fall back to manual
`NextToken` paging otherwise. Import does not crawl Glue databases and tables
directly.

## Apply

`lfguard apply` is a dry run unless `--execute` is provided. With `--execute`,
the adapter calls AWS for the changes present in the computed plan, or for the
selected changes in a saved JSON plan passed with `--plan`.

| Plan action | boto3 Lake Formation method | IAM action |
| --- | --- | --- |
| `lf_tag.create` | `create_lf_tag` | `lakeformation:CreateLFTag` |
| `lf_tag.add_values` | `update_lf_tag` with `TagValuesToAdd` | `lakeformation:UpdateLFTag` |
| `lf_tag.remove_values` | `update_lf_tag` with `TagValuesToDelete` | `lakeformation:UpdateLFTag` |
| `lf_tag_expression.create` | `create_lf_tag_expression` | `lakeformation:CreateLFTagExpression` |
| `lf_tag_expression.update` | `update_lf_tag_expression` | `lakeformation:UpdateLFTagExpression` |
| `lf_tag_expression.delete` | `delete_lf_tag_expression` | `lakeformation:DeleteLFTagExpression` |
| `data_cells_filter.create` | `create_data_cells_filter` | `lakeformation:CreateDataCellsFilter` |
| `data_cells_filter.update` | `update_data_cells_filter` | `lakeformation:UpdateDataCellsFilter` |
| `data_cells_filter.delete` | `delete_data_cells_filter` | `lakeformation:DeleteDataCellsFilter` |
| `resource_tag.add_values` | `add_lf_tags_to_resource` | `lakeformation:AddLFTagsToResource` |
| `resource_tag.remove_values` | `remove_lf_tags_from_resource` | `lakeformation:RemoveLFTagsFromResource` |
| `grant.add_permissions` | `grant_permissions` | `lakeformation:GrantPermissions` |
| `grant.revoke_permissions` | `revoke_permissions` | `lakeformation:RevokePermissions` |

Destructive actions are not planned or applied unless the matching `--allow-*`
flag is supplied:

- `lf_tag.remove_values` requires `--allow-lf-tag-value-removals`;
- `lf_tag_expression.update` requires `--allow-lf-tag-expression-updates`;
- `lf_tag_expression.delete` requires `--allow-lf-tag-expression-deletes`;
- `data_cells_filter.update` requires `--allow-data-cells-filter-updates`;
- `data_cells_filter.delete` requires `--allow-data-cells-filter-deletes`;
- `resource_tag.remove_values` requires `--allow-resource-tag-removals`;
- `grant.revoke_permissions` requires `--allow-permission-revokes`.

## Catalog IDs

Pass `--catalog-id` to add a Glue Data Catalog ID to live inventory and apply
requests. Resource-level `catalog_id` values in state files are also preserved
when rendering Lake Formation resource payloads. LF-Tag definitions can also
carry `catalog_id`; those scoped definitions override the adapter default for
`get_lf_tag`, `create_lf_tag`, and `update_lf_tag` request shapes.
Data cells filter definitions use `catalog_id` as the AWS `TableCatalogId`.

## Error Handling

During inventory, missing LF-Tags or resources are treated as absent current
state when AWS returns a not-found style error. Other boto3 exceptions are
raised and the CLI exits with status `2`.

During apply, AWS responses are returned in JSON output under each result's
`response` field. Failed AWS calls are not swallowed; the command exits with an
error so automation can stop immediately.

## Related Docs

- [`aws-permissions.md`](aws-permissions.md): starter IAM policies for read-only
  and apply roles.
- [`safety-model.md`](safety-model.md): conservative defaults and destructive
  change handling.
- [`state-format.md`](state-format.md): resource shapes rendered into AWS Lake
  Formation resource payloads.
