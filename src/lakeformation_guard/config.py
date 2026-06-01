"""Guardrail configuration helpers."""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Iterable, Optional

from .models import GuardrailConfig, ResourcePattern, ResourceRef


def lint_severity(config: GuardrailConfig, code: str, default: str) -> Optional[str]:
    """Return configured lint severity, or None when the finding should be ignored."""

    severity = config.lint.get(code.upper(), default)
    if severity == "ignore":
        return None
    return severity


def unmanaged_severity(config: GuardrailConfig, principal: Optional[str], resource: ResourceRef) -> Optional[str]:
    """Return unmanaged-current-state severity inside the configured ownership boundary."""

    if ignored_principal(config, principal) or ignored_resource(config, resource):
        return None
    if not _owned_by_config(config, principal, resource):
        return None
    action = config.ownership.unmanaged_action
    if action == "ignore":
        return None
    if action == "error":
        return "error"
    return "warning"


def ignored_principal(config: GuardrailConfig, principal: Optional[str]) -> bool:
    if principal is None:
        return False
    return _matches_any(principal, config.ignore.principals)


def ignored_resource(config: GuardrailConfig, resource: ResourceRef) -> bool:
    return any(resource_pattern_matches(pattern, resource) for pattern in config.ignore.resources)


def resource_pattern_matches(pattern: ResourcePattern, resource: ResourceRef) -> bool:
    checks = (
        (pattern.kind, resource.kind),
        (pattern.database_name, resource.database_name),
        (pattern.table_name, resource.table_name),
        (pattern.location, resource.location),
        (pattern.expression_name, resource.expression_name),
    )
    for expected, actual in checks:
        if expected is None:
            continue
        if actual is None or not fnmatchcase(actual, expected):
            return False
    return True


def _owned_by_config(config: GuardrailConfig, principal: Optional[str], resource: ResourceRef) -> bool:
    principal_owned = not config.ownership.managed_principals or (
        principal is None or _matches_any(principal, config.ownership.managed_principals)
    )
    resource_owned = not config.ownership.managed_resources or any(
        resource_pattern_matches(pattern, resource) for pattern in config.ownership.managed_resources
    )
    return principal_owned and resource_owned


def _matches_any(value: str, patterns: Iterable[str]) -> bool:
    return any(fnmatchcase(value, pattern) for pattern in patterns)
