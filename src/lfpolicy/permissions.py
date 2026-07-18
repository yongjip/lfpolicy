"""Permission set helpers for Lake Formation evidence and plans."""

from __future__ import annotations

from typing import FrozenSet, Iterable, Set


BROAD_PERMISSION_COVERAGE = {"ALL", "SUPER", "SUPER_USER"}
IAM_ALLOWED_PRINCIPAL = "IAM_Allowed_Principals"
IAM_ALLOWED_PRINCIPAL_ALIASES: FrozenSet[str] = frozenset(
    {"iamallowedprincipals", "iam_allowed_principals"}
)


def normalize_principal_identifier(principal: str) -> str:
    """Normalize known Lake Formation special-principal spellings."""

    return str(principal).strip().lower().replace(" ", "").replace("-", "_")


def is_iam_allowed_principal(principal: str) -> bool:
    """Return whether a principal names AWS IAM compatibility coverage."""

    return normalize_principal_identifier(principal) in IAM_ALLOWED_PRINCIPAL_ALIASES


def permission_set(permissions: Iterable[str]) -> Set[str]:
    """Return normalized Lake Formation permission names."""

    return {str(permission).strip().upper() for permission in permissions if str(permission).strip()}


def missing_permissions(desired: Iterable[str], current: Iterable[str]) -> Set[str]:
    """Return desired permissions not covered by the current permission set."""

    current_permissions = permission_set(current)
    if current_permissions & BROAD_PERMISSION_COVERAGE:
        return set()
    return permission_set(desired) - current_permissions
