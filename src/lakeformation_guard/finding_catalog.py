"""Stable metadata for public finding and plan codes."""

from __future__ import annotations

from typing import Any, Dict, Mapping

from .advisory import (
    ACTION_APPROVAL_REQUIRED,
    ACTION_BLOCK,
    ACTION_INFORM,
    ACTION_REVIEW_REQUIRED,
    is_hard_block,
)


DOCS_BASE_URL = "https://github.com/yongjip/aws-datalake-guard/blob/main/docs/finding-catalog.md"


def _entry(identifier: str, title: str, category: str, action: str, *, key: str = "code") -> Dict[str, Any]:
    docs_anchor = identifier.lower().replace("_", "-").replace(".", "-")
    return {
        key: identifier,
        "title": title,
        "category": category,
        "default_recommended_action": action,
        "hard_block": is_hard_block(action),
        "docs_anchor": docs_anchor,
        "docs_url": "{}#{}".format(DOCS_BASE_URL, docs_anchor),
    }


LINT_FINDINGS: Mapping[str, Mapping[str, Any]] = {
    "BROAD_PERMISSION_GRANT": _entry("BROAD_PERMISSION_GRANT", "Broad permission grant", "grant_governance", ACTION_APPROVAL_REQUIRED),
    "BROAD_PRINCIPAL_GRANT": _entry("BROAD_PRINCIPAL_GRANT", "Broad principal grant", "grant_governance", ACTION_APPROVAL_REQUIRED),
    "COLUMN_FILTER_MUTATING_PERMISSION_CONFLICT": _entry("COLUMN_FILTER_MUTATING_PERMISSION_CONFLICT", "Column filter mutation conflict", "grant_governance", ACTION_BLOCK),
    "DATA_CELLS_FILTER_DUPLICATE_IDENTITY": _entry("DATA_CELLS_FILTER_DUPLICATE_IDENTITY", "Duplicate data cells filter identity", "data_cells_filter", ACTION_BLOCK),
    "DESIRED_STATE_EMPTY": _entry("DESIRED_STATE_EMPTY", "Desired state is empty", "desired_state", ACTION_INFORM),
    "GRANTABLE_PERMISSION_REVIEW": _entry("GRANTABLE_PERMISSION_REVIEW", "Grantable permission requires review", "grant_governance", ACTION_APPROVAL_REQUIRED),
    "LF_TAG_CASE_NORMALIZATION": _entry("LF_TAG_CASE_NORMALIZATION", "LF-Tag case normalization", "lf_tag", ACTION_REVIEW_REQUIRED),
    "LF_TAG_DUPLICATE_IDENTITY": _entry("LF_TAG_DUPLICATE_IDENTITY", "Duplicate LF-Tag identity", "lf_tag", ACTION_BLOCK),
    "LF_TAG_EXPRESSION_DUPLICATE_IDENTITY": _entry("LF_TAG_EXPRESSION_DUPLICATE_IDENTITY", "Duplicate LF-Tag expression identity", "lf_tag_expression", ACTION_BLOCK),
    "LF_TAG_EXPRESSION_KEY_UNDEFINED": _entry("LF_TAG_EXPRESSION_KEY_UNDEFINED", "LF-Tag expression key is undefined", "lf_tag_expression", ACTION_BLOCK),
    "LF_TAG_EXPRESSION_TOO_LARGE": _entry("LF_TAG_EXPRESSION_TOO_LARGE", "LF-Tag expression too large", "lf_tag_expression", ACTION_BLOCK),
    "LF_TAG_EXPRESSION_VALUE_LIMIT_EXCEEDED": _entry("LF_TAG_EXPRESSION_VALUE_LIMIT_EXCEEDED", "LF-Tag expression value limit exceeded", "lf_tag_expression", ACTION_BLOCK),
    "LF_TAG_EXPRESSION_VALUE_UNDEFINED": _entry("LF_TAG_EXPRESSION_VALUE_UNDEFINED", "LF-Tag expression value is undefined", "lf_tag_expression", ACTION_BLOCK),
    "LF_TAG_EXPRESSION_WILDCARD_VALUE": _entry("LF_TAG_EXPRESSION_WILDCARD_VALUE", "LF-Tag expression wildcard value", "lf_tag_expression", ACTION_INFORM),
    "LF_TAG_KEY_METADATA_DUPLICATE_IDENTITY": _entry("LF_TAG_KEY_METADATA_DUPLICATE_IDENTITY", "Duplicate LF-Tag key metadata identity", "lf_tag", ACTION_BLOCK),
    "LF_TAG_POLICY_COMBINED_TABLE_SELECT_MUTATION_CONFLICT": _entry("LF_TAG_POLICY_COMBINED_TABLE_SELECT_MUTATION_CONFLICT", "Combined LF-Tag policy select and mutation conflict", "grant_governance", ACTION_BLOCK),
    "LF_TAG_POLICY_EXPRESSION_NAME_UNDEFINED": _entry("LF_TAG_POLICY_EXPRESSION_NAME_UNDEFINED", "LF-Tag policy expression name is undefined", "grant_governance", ACTION_BLOCK),
    "LF_TAG_POLICY_EXPRESSION_TOO_LARGE": _entry("LF_TAG_POLICY_EXPRESSION_TOO_LARGE", "LF-Tag policy expression too large", "grant_governance", ACTION_BLOCK),
    "LF_TAG_POLICY_KEY_UNDEFINED": _entry("LF_TAG_POLICY_KEY_UNDEFINED", "LF-Tag policy key is undefined", "grant_governance", ACTION_BLOCK),
    "LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT": _entry("LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT", "LF-Tag policy table select and mutation conflict", "grant_governance", ACTION_BLOCK),
    "LF_TAG_POLICY_VALUE_LIMIT_EXCEEDED": _entry("LF_TAG_POLICY_VALUE_LIMIT_EXCEEDED", "LF-Tag policy value limit exceeded", "grant_governance", ACTION_BLOCK),
    "LF_TAG_POLICY_VALUE_UNDEFINED": _entry("LF_TAG_POLICY_VALUE_UNDEFINED", "LF-Tag policy value is undefined", "grant_governance", ACTION_BLOCK),
    "LF_TAG_POLICY_WILDCARD_VALUE": _entry("LF_TAG_POLICY_WILDCARD_VALUE", "LF-Tag policy wildcard value", "grant_governance", ACTION_INFORM),
    "LF_TAG_VALUE_LIMIT_EXCEEDED": _entry("LF_TAG_VALUE_LIMIT_EXCEEDED", "LF-Tag value limit exceeded", "lf_tag", ACTION_BLOCK),
    "MUTATING_PERMISSION_REVIEW": _entry("MUTATING_PERMISSION_REVIEW", "Mutating permission requires review", "grant_governance", ACTION_APPROVAL_REQUIRED),
    "NAMED_RESOURCE_GRANT_REVIEW": _entry("NAMED_RESOURCE_GRANT_REVIEW", "Named resource grant requires review", "grant_governance", ACTION_APPROVAL_REQUIRED),
    "POLICY_EXCEPTION_APPROVER_IS_OWNER": _entry("POLICY_EXCEPTION_APPROVER_IS_OWNER", "Policy exception approver is owner", "exception_lifecycle", ACTION_INFORM),
    "POLICY_EXCEPTION_EXPIRED": _entry("POLICY_EXCEPTION_EXPIRED", "Policy exception expired", "exception_lifecycle", ACTION_BLOCK),
    "POLICY_EXCEPTION_EXPIRING_SOON": _entry("POLICY_EXCEPTION_EXPIRING_SOON", "Policy exception expiring soon", "exception_lifecycle", ACTION_INFORM),
    "RESOURCE_TAG_KEY_UNDEFINED": _entry("RESOURCE_TAG_KEY_UNDEFINED", "Resource tag key is undefined", "resource_tag", ACTION_BLOCK),
    "RESOURCE_TAG_KIND_UNSUPPORTED": _entry("RESOURCE_TAG_KIND_UNSUPPORTED", "Resource tag kind unsupported", "resource_tag", ACTION_BLOCK),
    "RESOURCE_TAG_LIMIT_EXCEEDED": _entry("RESOURCE_TAG_LIMIT_EXCEEDED", "Resource tag limit exceeded", "resource_tag", ACTION_BLOCK),
    "RESOURCE_TAG_MULTIPLE_VALUES": _entry("RESOURCE_TAG_MULTIPLE_VALUES", "Resource tag has multiple values", "resource_tag", ACTION_BLOCK),
    "RESOURCE_TAG_SCOPE_UNSUPPORTED": _entry("RESOURCE_TAG_SCOPE_UNSUPPORTED", "Resource tag scope unsupported", "resource_tag", ACTION_BLOCK),
    "RESOURCE_TAG_VALUE_UNDEFINED": _entry("RESOURCE_TAG_VALUE_UNDEFINED", "Resource tag value is undefined", "resource_tag", ACTION_BLOCK),
}

AUDIT_FINDINGS: Mapping[str, Mapping[str, Any]] = {
    "DATA_CELLS_FILTER_DRIFT": _entry("DATA_CELLS_FILTER_DRIFT", "Data cells filter drift", "data_cells_filter", ACTION_REVIEW_REQUIRED),
    "DATA_CELLS_FILTER_MISSING": _entry("DATA_CELLS_FILTER_MISSING", "Data cells filter missing", "data_cells_filter", ACTION_REVIEW_REQUIRED),
    "DATA_CELLS_FILTER_UNMANAGED": _entry("DATA_CELLS_FILTER_UNMANAGED", "Data cells filter unmanaged", "data_cells_filter", ACTION_REVIEW_REQUIRED),
    "GRANT_MISSING": _entry("GRANT_MISSING", "Grant missing", "grant", ACTION_REVIEW_REQUIRED),
    "GRANT_PERMISSIONS_MISSING": _entry("GRANT_PERMISSIONS_MISSING", "Grant permissions missing", "grant", ACTION_REVIEW_REQUIRED),
    "GRANT_PERMISSIONS_UNMANAGED": _entry("GRANT_PERMISSIONS_UNMANAGED", "Grant permissions unmanaged", "grant", ACTION_REVIEW_REQUIRED),
    "GRANT_UNMANAGED": _entry("GRANT_UNMANAGED", "Grant unmanaged", "grant", ACTION_REVIEW_REQUIRED),
    "LF_TAG_EXPRESSION_BODY_DRIFT": _entry("LF_TAG_EXPRESSION_BODY_DRIFT", "LF-Tag expression body drift", "lf_tag_expression", ACTION_REVIEW_REQUIRED),
    "LF_TAG_EXPRESSION_MISSING": _entry("LF_TAG_EXPRESSION_MISSING", "LF-Tag expression missing", "lf_tag_expression", ACTION_REVIEW_REQUIRED),
    "LF_TAG_EXPRESSION_UNMANAGED": _entry("LF_TAG_EXPRESSION_UNMANAGED", "LF-Tag expression unmanaged", "lf_tag_expression", ACTION_REVIEW_REQUIRED),
    "LF_TAG_MISSING": _entry("LF_TAG_MISSING", "LF-Tag missing", "lf_tag", ACTION_REVIEW_REQUIRED),
    "LF_TAG_UNMANAGED": _entry("LF_TAG_UNMANAGED", "LF-Tag unmanaged", "lf_tag", ACTION_REVIEW_REQUIRED),
    "LF_TAG_VALUES_MISSING": _entry("LF_TAG_VALUES_MISSING", "LF-Tag values missing", "lf_tag", ACTION_REVIEW_REQUIRED),
    "LF_TAG_VALUES_UNMANAGED": _entry("LF_TAG_VALUES_UNMANAGED", "LF-Tag values unmanaged", "lf_tag", ACTION_REVIEW_REQUIRED),
    "RESOURCE_TAG_KEY_UNMANAGED": _entry("RESOURCE_TAG_KEY_UNMANAGED", "Resource tag key unmanaged", "resource_tag", ACTION_REVIEW_REQUIRED),
    "RESOURCE_TAG_UNMANAGED": _entry("RESOURCE_TAG_UNMANAGED", "Resource tag unmanaged", "resource_tag", ACTION_REVIEW_REQUIRED),
    "RESOURCE_TAG_VALUES_MISSING": _entry("RESOURCE_TAG_VALUES_MISSING", "Resource tag values missing", "resource_tag", ACTION_REVIEW_REQUIRED),
    "RESOURCE_TAG_VALUES_UNMANAGED": _entry("RESOURCE_TAG_VALUES_UNMANAGED", "Resource tag values unmanaged", "resource_tag", ACTION_REVIEW_REQUIRED),
}

PLAN_ACTIONS: Mapping[str, Mapping[str, Any]] = {
    "data_cells_filter.create": _entry("data_cells_filter.create", "Create data cells filter", "data_cells_filter", ACTION_REVIEW_REQUIRED, key="action"),
    "data_cells_filter.delete": _entry("data_cells_filter.delete", "Delete data cells filter", "data_cells_filter", ACTION_BLOCK, key="action"),
    "data_cells_filter.update": _entry("data_cells_filter.update", "Update data cells filter", "data_cells_filter", ACTION_BLOCK, key="action"),
    "grant.add_permissions": _entry("grant.add_permissions", "Grant permissions", "grant", ACTION_REVIEW_REQUIRED, key="action"),
    "grant.revoke_permissions": _entry("grant.revoke_permissions", "Revoke permissions", "grant", ACTION_BLOCK, key="action"),
    "lf_tag.add_values": _entry("lf_tag.add_values", "Add LF-Tag values", "lf_tag", ACTION_REVIEW_REQUIRED, key="action"),
    "lf_tag.create": _entry("lf_tag.create", "Create LF-Tag", "lf_tag", ACTION_REVIEW_REQUIRED, key="action"),
    "lf_tag.delete": _entry("lf_tag.delete", "Delete LF-Tag", "lf_tag", ACTION_BLOCK, key="action"),
    "lf_tag.remove_values": _entry("lf_tag.remove_values", "Remove LF-Tag values", "lf_tag", ACTION_BLOCK, key="action"),
    "lf_tag_expression.create": _entry("lf_tag_expression.create", "Create LF-Tag expression", "lf_tag_expression", ACTION_REVIEW_REQUIRED, key="action"),
    "lf_tag_expression.delete": _entry("lf_tag_expression.delete", "Delete LF-Tag expression", "lf_tag_expression", ACTION_BLOCK, key="action"),
    "lf_tag_expression.update": _entry("lf_tag_expression.update", "Update LF-Tag expression", "lf_tag_expression", ACTION_BLOCK, key="action"),
    "resource_tag.add_values": _entry("resource_tag.add_values", "Add resource LF-Tags", "resource_tag", ACTION_REVIEW_REQUIRED, key="action"),
    "resource_tag.remove_values": _entry("resource_tag.remove_values", "Remove resource LF-Tags", "resource_tag", ACTION_BLOCK, key="action"),
}


def lint_metadata(code: str) -> Mapping[str, Any]:
    return LINT_FINDINGS.get(code, _entry(code, code.replace("_", " ").title(), "lint", ACTION_REVIEW_REQUIRED))


def audit_metadata(code: str) -> Mapping[str, Any]:
    return AUDIT_FINDINGS.get(code, _entry(code, code.replace("_", " ").title(), "audit", ACTION_REVIEW_REQUIRED))


def plan_metadata(action: str) -> Mapping[str, Any]:
    return PLAN_ACTIONS.get(action, _entry(action, action.replace(".", " ").replace("_", " ").title(), "plan", ACTION_REVIEW_REQUIRED, key="action"))
