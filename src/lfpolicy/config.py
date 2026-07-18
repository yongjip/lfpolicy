"""Guardrail configuration helpers."""

from __future__ import annotations

from dataclasses import replace
from fnmatch import fnmatchcase
from typing import Iterable, Optional

from .models import GuardrailConfig, ResourcePattern, ResourceRef
from .permissions import is_iam_allowed_principal


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
    if _matches_any(principal, config.ignore.principals):
        return True
    if is_iam_allowed_principal(principal):
        return any(
            is_iam_allowed_principal(pattern)
            for pattern in config.ignore.principals
        )
    return False


def ignored_resource(config: GuardrailConfig, resource: ResourceRef) -> bool:
    return any(resource_pattern_matches(pattern, resource) for pattern in config.ignore.resources)


def lint_exception_applies(
    config: GuardrailConfig,
    rule: str,
    principal: str,
    resource: ResourceRef,
    permissions: Iterable[str] = (),
) -> bool:
    """Return whether a non-expired policy exception covers a lint rule."""

    requested_permissions = {str(permission).strip().upper() for permission in permissions if str(permission).strip()}
    for exception in config.exceptions:
        if exception.is_expired():
            continue
        if rule not in exception.rules:
            continue
        if not fnmatchcase(principal, exception.principal):
            continue
        if exception.resource and not resource_pattern_matches(exception.resource, resource):
            continue
        if exception.permissions and not requested_permissions.issubset(set(exception.permissions)):
            continue
        return True
    return False


def resource_pattern_matches(pattern: ResourcePattern, resource: ResourceRef) -> bool:
    checks = (
        (pattern.kind, resource.kind),
        (pattern.catalog_id, resource.catalog_id),
        (pattern.database_name, resource.database_name),
        (pattern.table_name, resource.table_name),
        (pattern.location, resource.location),
        (pattern.expression_name, resource.expression_name),
        (pattern.filter_name, resource.filter_name),
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
        _ownership_resource_matches(pattern, resource) for pattern in config.ownership.managed_resources
    )
    return principal_owned and resource_owned


def _ownership_resource_matches(pattern: ResourcePattern, resource: ResourceRef) -> bool:
    if resource_pattern_matches(pattern, resource):
        return True
    if pattern.catalog_id and resource.catalog_id is None:
        return resource_pattern_matches(pattern, replace(resource, catalog_id=pattern.catalog_id))
    return False


def _matches_any(value: str, patterns: Iterable[str]) -> bool:
    return any(fnmatchcase(value, pattern) for pattern in patterns)
