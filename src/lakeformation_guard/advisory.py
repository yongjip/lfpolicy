"""Recommended actions for advisory review outputs."""

from __future__ import annotations

from typing import Iterable, Mapping


ACTION_INFORM = "inform"
ACTION_REVIEW_REQUIRED = "review_required"
ACTION_APPROVAL_REQUIRED = "approval_required"
ACTION_BLOCK = "block"
ACTION_ORDER = {
    ACTION_INFORM: 0,
    ACTION_REVIEW_REQUIRED: 1,
    ACTION_APPROVAL_REQUIRED: 2,
    ACTION_BLOCK: 3,
}

_APPROVAL_REQUIRED_LINT_CODES = {
    "BROAD_PRINCIPAL_GRANT",
    "BROAD_PERMISSION_GRANT",
    "MUTATING_PERMISSION_REVIEW",
    "GRANTABLE_PERMISSION_REVIEW",
    "NAMED_RESOURCE_GRANT_REVIEW",
}

_BLOCK_LINT_CODES = {
    "DATA_CELLS_FILTER_MISSING_CATALOG_ID",
    "POLICY_EXCEPTION_EXPIRED",
    "RESOURCE_TAG_KIND_UNSUPPORTED",
    "RESOURCE_TAG_SCOPE_UNSUPPORTED",
    "RESOURCE_TAG_MULTIPLE_VALUES",
    "LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT",
    "COLUMN_FILTER_MUTATING_PERMISSION_CONFLICT",
    "LF_TAG_POLICY_COMBINED_TABLE_SELECT_MUTATION_CONFLICT",
}

_BLOCK_LINT_SUFFIXES = (
    "_DUPLICATE_IDENTITY",
    "_LIMIT_EXCEEDED",
    "_TOO_LARGE",
    "_UNDEFINED",
)


def lint_recommended_action(code: str, severity: str) -> str:
    """Return the advisory action for a lint finding."""

    if code in _BLOCK_LINT_CODES or code.endswith(_BLOCK_LINT_SUFFIXES):
        return ACTION_BLOCK
    if code in _APPROVAL_REQUIRED_LINT_CODES:
        return ACTION_APPROVAL_REQUIRED
    if severity == "error":
        return ACTION_REVIEW_REQUIRED
    return ACTION_INFORM


def audit_recommended_action(code: str, severity: str) -> str:
    """Return the advisory action for an audit finding."""

    return ACTION_REVIEW_REQUIRED


def plan_recommended_action(action: str, *, destructive: bool) -> str:
    """Return the advisory action for a planned change."""

    if destructive:
        return ACTION_BLOCK
    return ACTION_REVIEW_REQUIRED


def is_hard_block(action: str) -> bool:
    """Return whether a recommended action should hard-block the review."""

    return action == ACTION_BLOCK


def strongest_action(actions: Iterable[str]) -> str:
    """Return the strongest action in an iterable of advisory actions."""

    result = ACTION_INFORM
    for action in actions:
        if ACTION_ORDER.get(action, 0) > ACTION_ORDER[result]:
            result = action
    return result


def action_summary(actions: Iterable[str]) -> Mapping[str, int]:
    """Count advisory actions using stable keys."""

    counts = {action: 0 for action in ACTION_ORDER}
    for action in actions:
        counts[action if action in counts else ACTION_INFORM] += 1
    return counts
