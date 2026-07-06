# AWS API Coverage

`lfguard` uses AWS APIs only when live inventory or import is requested.
Most commands are fully offline: `sample`, `bootstrap`, `init`, `schema`,
`doctor`, `permissions`, `completion`, `check`, `validate`, `lint`, and
`summary` never call AWS. The `audit`, `plan`, `review`, `explain`, and
`explain-batch` commands also stay
offline when `--current-snapshot` is provided.

The live adapter is intentionally small and uses only the Lake Formation client
from `boto3`.

## Live Inventory

These commands load live state when `--current-snapshot` is omitted:

- `lfguard audit`
- `lfguard plan`
- `lfguard review`
- `lfguard explain`
- `lfguard explain-batch`

`lfguard snapshot` and `lfguard import` load live state.

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

## Planned Change Evidence

`lfguard plan` and `lfguard review` may include `aws_api` metadata for planned
changes. That metadata is evidence for humans, services, CI, and tickets; it is
not an instruction that lfguard will execute. AWS write execution belongs to the
consuming service or operator workflow.

Library consumers that already own approval and AWS write execution can call
`lakeformation_guard.aws.boto3_kwargs_for(change)` to render one planned
`Change` into inert Lake Formation request evidence:

```python
from lakeformation_guard.aws import boto3_kwargs_for

request = boto3_kwargs_for(change)
# {"method": "...", "kwargs": {...}}
```

The helper is stateless: it creates no boto3 client, sends no request, reads no
credentials, and performs no retry or rollback. It is the request-shaped
counterpart to plan evidence, not an lfguard execution path.

## Catalog IDs

Pass `--catalog-id` to add a Glue Data Catalog ID to live inventory and import
requests. Resource-level `catalog_id` values in state files are also preserved
when rendering Lake Formation resource payloads. LF-Tag definitions can also
carry `catalog_id`; those scoped definitions override the adapter default for
`get_lf_tag` request shapes.
Data cells filter definitions use `catalog_id` as the AWS `TableCatalogId`.

## Error Handling

During inventory, missing LF-Tags or resources are treated as absent current
state when AWS returns a not-found style error. Other boto3 exceptions are
raised and the CLI exits with status `2`.

## Related Docs

- [`aws-permissions.md`](aws-permissions.md): starter IAM policies for read-only
  lfguard roles.
- [`safety-model.md`](safety-model.md): conservative defaults and destructive
  change handling.
- [`state-format.md`](state-format.md): resource shapes rendered into AWS Lake
  Formation resource payloads.
