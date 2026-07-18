"""Permission set helpers for Lake Formation evidence and plans."""

from __future__ import annotations

from typing import Iterable, Set


BROAD_PERMISSION_COVERAGE = {"ALL", "SUPER", "SUPER_USER"}


def permission_set(permissions: Iterable[str]) -> Set[str]:
    """Return normalized Lake Formation permission names."""

    return {str(permission).strip().upper() for permission in permissions if str(permission).strip()}


def missing_permissions(desired: Iterable[str], current: Iterable[str]) -> Set[str]:
    """Return desired permissions not covered by the current permission set."""

    current_permissions = permission_set(current)
    if current_permissions & BROAD_PERMISSION_COVERAGE:
        return set()
    return permission_set(desired) - current_permissions
