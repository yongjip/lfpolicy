# Finding Catalog

This catalog documents stable public finding codes and plan actions emitted by
`lfguard` reports. Services, CI jobs, ticket workflows, and LLM agents should
map workflow behavior from `recommended_action`, `hard_block`, review `status`,
and explain-batch `decision`, not from `severity` alone.

`default_recommended_action` is the normal advisory action for the code or
action. Runtime configuration may still change lint severity, but it must not
turn `severity: "error"` into an automatic workflow block by itself.

JSON reports include `docs_anchor` and `docs_url` for catalog-backed findings
and plan changes. Use `code`, `action`, and `docs_anchor` as stable keys for
stored audit evidence and service UI mappings. `docs_url` points to live
documentation on the repository `main` branch and may show newer explanatory
text than the lfguard version that generated historical evidence.

## Compatibility

Minor releases may add optional fields, new finding codes, new plan actions, or
new catalog rows. Minor releases must not remove stable required JSON fields or
change the meaning of existing `recommended_action`, `hard_block`, `status`, or
`decision` fields without release-note documentation.

## Lint Findings

| Code | Title | Category | Default action | Hard block |
| --- | --- | --- | --- | --- |
| <a id="broad-permission-grant"></a>`BROAD_PERMISSION_GRANT` | Broad permission grant | grant_governance | `approval_required` | false |
| <a id="broad-principal-grant"></a>`BROAD_PRINCIPAL_GRANT` | Broad principal grant | grant_governance | `approval_required` | false |
| <a id="column-filter-mutating-permission-conflict"></a>`COLUMN_FILTER_MUTATING_PERMISSION_CONFLICT` | Column filter mutation conflict | grant_governance | `block` | true |
| <a id="data-cells-filter-duplicate-identity"></a>`DATA_CELLS_FILTER_DUPLICATE_IDENTITY` | Duplicate data cells filter identity | data_cells_filter | `block` | true |
| <a id="desired-state-empty"></a>`DESIRED_STATE_EMPTY` | Desired state is empty | desired_state | `inform` | false |
| <a id="grantable-permission-review"></a>`GRANTABLE_PERMISSION_REVIEW` | Grantable permission requires review | grant_governance | `approval_required` | false |
| <a id="lf-tag-case-normalization"></a>`LF_TAG_CASE_NORMALIZATION` | LF-Tag case normalization | lf_tag | `review_required` | false |
| <a id="lf-tag-duplicate-identity"></a>`LF_TAG_DUPLICATE_IDENTITY` | Duplicate LF-Tag identity | lf_tag | `block` | true |
| <a id="lf-tag-expression-duplicate-identity"></a>`LF_TAG_EXPRESSION_DUPLICATE_IDENTITY` | Duplicate LF-Tag expression identity | lf_tag_expression | `block` | true |
| <a id="lf-tag-expression-key-undefined"></a>`LF_TAG_EXPRESSION_KEY_UNDEFINED` | LF-Tag expression key is undefined | lf_tag_expression | `block` | true |
| <a id="lf-tag-expression-too-large"></a>`LF_TAG_EXPRESSION_TOO_LARGE` | LF-Tag expression too large | lf_tag_expression | `block` | true |
| <a id="lf-tag-expression-value-limit-exceeded"></a>`LF_TAG_EXPRESSION_VALUE_LIMIT_EXCEEDED` | LF-Tag expression value limit exceeded | lf_tag_expression | `block` | true |
| <a id="lf-tag-expression-value-undefined"></a>`LF_TAG_EXPRESSION_VALUE_UNDEFINED` | LF-Tag expression value is undefined | lf_tag_expression | `block` | true |
| <a id="lf-tag-expression-wildcard-value"></a>`LF_TAG_EXPRESSION_WILDCARD_VALUE` | LF-Tag expression wildcard value | lf_tag_expression | `inform` | false |
| <a id="lf-tag-key-metadata-duplicate-identity"></a>`LF_TAG_KEY_METADATA_DUPLICATE_IDENTITY` | Duplicate LF-Tag key metadata identity | lf_tag | `block` | true |
| <a id="lf-tag-policy-combined-table-select-mutation-conflict"></a>`LF_TAG_POLICY_COMBINED_TABLE_SELECT_MUTATION_CONFLICT` | Combined LF-Tag policy select and mutation conflict | grant_governance | `block` | true |
| <a id="lf-tag-policy-expression-name-undefined"></a>`LF_TAG_POLICY_EXPRESSION_NAME_UNDEFINED` | LF-Tag policy expression name is undefined | grant_governance | `block` | true |
| <a id="lf-tag-policy-expression-too-large"></a>`LF_TAG_POLICY_EXPRESSION_TOO_LARGE` | LF-Tag policy expression too large | grant_governance | `block` | true |
| <a id="lf-tag-policy-key-undefined"></a>`LF_TAG_POLICY_KEY_UNDEFINED` | LF-Tag policy key is undefined | grant_governance | `block` | true |
| <a id="lf-tag-policy-table-select-mutation-conflict"></a>`LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT` | LF-Tag policy table select and mutation conflict | grant_governance | `block` | true |
| <a id="lf-tag-policy-value-limit-exceeded"></a>`LF_TAG_POLICY_VALUE_LIMIT_EXCEEDED` | LF-Tag policy value limit exceeded | grant_governance | `block` | true |
| <a id="lf-tag-policy-value-undefined"></a>`LF_TAG_POLICY_VALUE_UNDEFINED` | LF-Tag policy value is undefined | grant_governance | `block` | true |
| <a id="lf-tag-policy-wildcard-value"></a>`LF_TAG_POLICY_WILDCARD_VALUE` | LF-Tag policy wildcard value | grant_governance | `inform` | false |
| <a id="lf-tag-value-limit-exceeded"></a>`LF_TAG_VALUE_LIMIT_EXCEEDED` | LF-Tag value limit exceeded | lf_tag | `block` | true |
| <a id="mutating-permission-review"></a>`MUTATING_PERMISSION_REVIEW` | Mutating permission requires review | grant_governance | `approval_required` | false |
| <a id="named-resource-grant-review"></a>`NAMED_RESOURCE_GRANT_REVIEW` | Named resource grant requires review | grant_governance | `approval_required` | false |
| <a id="policy-exception-approver-is-owner"></a>`POLICY_EXCEPTION_APPROVER_IS_OWNER` | Policy exception approver is owner | exception_lifecycle | `inform` | false |
| <a id="policy-exception-expired"></a>`POLICY_EXCEPTION_EXPIRED` | Policy exception expired | exception_lifecycle | `block` | true |
| <a id="policy-exception-expiring-soon"></a>`POLICY_EXCEPTION_EXPIRING_SOON` | Policy exception expiring soon | exception_lifecycle | `inform` | false |
| <a id="resource-tag-key-undefined"></a>`RESOURCE_TAG_KEY_UNDEFINED` | Resource tag key is undefined | resource_tag | `block` | true |
| <a id="resource-tag-kind-unsupported"></a>`RESOURCE_TAG_KIND_UNSUPPORTED` | Resource tag kind unsupported | resource_tag | `block` | true |
| <a id="resource-tag-limit-exceeded"></a>`RESOURCE_TAG_LIMIT_EXCEEDED` | Resource tag limit exceeded | resource_tag | `block` | true |
| <a id="resource-tag-multiple-values"></a>`RESOURCE_TAG_MULTIPLE_VALUES` | Resource tag has multiple values | resource_tag | `block` | true |
| <a id="resource-tag-scope-unsupported"></a>`RESOURCE_TAG_SCOPE_UNSUPPORTED` | Resource tag scope unsupported | resource_tag | `block` | true |
| <a id="resource-tag-value-undefined"></a>`RESOURCE_TAG_VALUE_UNDEFINED` | Resource tag value is undefined | resource_tag | `block` | true |

## Audit Findings

| Code | Title | Category | Default action | Hard block |
| --- | --- | --- | --- | --- |
| <a id="data-cells-filter-drift"></a>`DATA_CELLS_FILTER_DRIFT` | Data cells filter drift | data_cells_filter | `review_required` | false |
| <a id="data-cells-filter-missing"></a>`DATA_CELLS_FILTER_MISSING` | Data cells filter missing | data_cells_filter | `review_required` | false |
| <a id="data-cells-filter-unmanaged"></a>`DATA_CELLS_FILTER_UNMANAGED` | Data cells filter unmanaged | data_cells_filter | `review_required` | false |
| <a id="grant-missing"></a>`GRANT_MISSING` | Grant missing | grant | `review_required` | false |
| <a id="grant-permissions-missing"></a>`GRANT_PERMISSIONS_MISSING` | Grant permissions missing | grant | `review_required` | false |
| <a id="grant-permissions-unmanaged"></a>`GRANT_PERMISSIONS_UNMANAGED` | Grant permissions unmanaged | grant | `review_required` | false |
| <a id="grant-unmanaged"></a>`GRANT_UNMANAGED` | Grant unmanaged | grant | `review_required` | false |
| <a id="lf-tag-expression-body-drift"></a>`LF_TAG_EXPRESSION_BODY_DRIFT` | LF-Tag expression body drift | lf_tag_expression | `review_required` | false |
| <a id="lf-tag-expression-missing"></a>`LF_TAG_EXPRESSION_MISSING` | LF-Tag expression missing | lf_tag_expression | `review_required` | false |
| <a id="lf-tag-expression-unmanaged"></a>`LF_TAG_EXPRESSION_UNMANAGED` | LF-Tag expression unmanaged | lf_tag_expression | `review_required` | false |
| <a id="lf-tag-missing"></a>`LF_TAG_MISSING` | LF-Tag missing | lf_tag | `review_required` | false |
| <a id="lf-tag-unmanaged"></a>`LF_TAG_UNMANAGED` | LF-Tag unmanaged | lf_tag | `review_required` | false |
| <a id="lf-tag-values-missing"></a>`LF_TAG_VALUES_MISSING` | LF-Tag values missing | lf_tag | `review_required` | false |
| <a id="lf-tag-values-unmanaged"></a>`LF_TAG_VALUES_UNMANAGED` | LF-Tag values unmanaged | lf_tag | `review_required` | false |
| <a id="resource-tag-key-unmanaged"></a>`RESOURCE_TAG_KEY_UNMANAGED` | Resource tag key unmanaged | resource_tag | `review_required` | false |
| <a id="resource-tag-unmanaged"></a>`RESOURCE_TAG_UNMANAGED` | Resource tag unmanaged | resource_tag | `review_required` | false |
| <a id="resource-tag-values-missing"></a>`RESOURCE_TAG_VALUES_MISSING` | Resource tag values missing | resource_tag | `review_required` | false |
| <a id="resource-tag-values-unmanaged"></a>`RESOURCE_TAG_VALUES_UNMANAGED` | Resource tag values unmanaged | resource_tag | `review_required` | false |

## Plan Actions

| Action | Title | Category | Default action | Hard block |
| --- | --- | --- | --- | --- |
| <a id="data-cells-filter-create"></a>`data_cells_filter.create` | Create data cells filter | data_cells_filter | `review_required` | false |
| <a id="data-cells-filter-delete"></a>`data_cells_filter.delete` | Delete data cells filter | data_cells_filter | `block` | true |
| <a id="data-cells-filter-update"></a>`data_cells_filter.update` | Update data cells filter | data_cells_filter | `block` | true |
| <a id="grant-add-permissions"></a>`grant.add_permissions` | Grant permissions | grant | `review_required` | false |
| <a id="grant-revoke-permissions"></a>`grant.revoke_permissions` | Revoke permissions | grant | `block` | true |
| <a id="lf-tag-add-values"></a>`lf_tag.add_values` | Add LF-Tag values | lf_tag | `review_required` | false |
| <a id="lf-tag-create"></a>`lf_tag.create` | Create LF-Tag | lf_tag | `review_required` | false |
| <a id="lf-tag-delete"></a>`lf_tag.delete` | Delete LF-Tag | lf_tag | `block` | true |
| <a id="lf-tag-remove-values"></a>`lf_tag.remove_values` | Remove LF-Tag values | lf_tag | `block` | true |
| <a id="lf-tag-expression-create"></a>`lf_tag_expression.create` | Create LF-Tag expression | lf_tag_expression | `review_required` | false |
| <a id="lf-tag-expression-delete"></a>`lf_tag_expression.delete` | Delete LF-Tag expression | lf_tag_expression | `block` | true |
| <a id="lf-tag-expression-update"></a>`lf_tag_expression.update` | Update LF-Tag expression | lf_tag_expression | `block` | true |
| <a id="resource-tag-add-values"></a>`resource_tag.add_values` | Add resource LF-Tags | resource_tag | `review_required` | false |
| <a id="resource-tag-remove-values"></a>`resource_tag.remove_values` | Remove resource LF-Tags | resource_tag | `block` | true |
