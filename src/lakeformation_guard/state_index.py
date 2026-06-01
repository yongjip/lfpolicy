"""Shared indexes for normalized Lake Formation state objects."""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, Optional, Tuple

from .models import (
    Grant,
    LFTagDefinition,
    LFTagExpressionDefinition,
    ResourceRef,
    ResourceTagAssignment,
)

LFTagExpressionKey = Tuple[Optional[str], str]


def lf_tag_index(tags: Iterable[LFTagDefinition]) -> Dict[str, LFTagDefinition]:
    merged: Dict[str, set] = {}
    for tag in tags:
        merged.setdefault(tag.key, set()).update(tag.values)
    return {key: LFTagDefinition(key, tuple(values)) for key, values in merged.items()}


def lf_tag_expression_key(catalog_id: Optional[str], name: str) -> LFTagExpressionKey:
    return (catalog_id, name)


def lf_tag_expression_definition_key(expression: LFTagExpressionDefinition) -> LFTagExpressionKey:
    return lf_tag_expression_key(expression.catalog_id, expression.name)


def lf_tag_expression_index(
    expressions: Iterable[LFTagExpressionDefinition],
) -> Dict[LFTagExpressionKey, LFTagExpressionDefinition]:
    return {lf_tag_expression_definition_key(expression): expression for expression in expressions}


def lf_tag_expression_sort_key(key: LFTagExpressionKey) -> str:
    return "{}:{}".format(key[0] or "", key[1])


def resource_tag_index(assignments: Iterable[ResourceTagAssignment]) -> Dict[ResourceRef, Dict[str, FrozenSet[str]]]:
    merged: Dict[ResourceRef, Dict[str, set]] = {}
    for assignment in assignments:
        resource_tags = merged.setdefault(assignment.resource, {})
        for key, values in assignment.tags.items():
            resource_tags.setdefault(key, set()).update(values)
    return {
        resource: {key: frozenset(values) for key, values in tags.items()}
        for resource, tags in merged.items()
    }


def grant_index(grants: Iterable[Grant]) -> Dict[Tuple[str, ResourceRef], Grant]:
    merged: Dict[Tuple[str, ResourceRef], Dict[str, set]] = {}
    for grant in grants:
        entry = merged.setdefault(grant.identity, {"permissions": set(), "grantable_permissions": set()})
        entry["permissions"].update(grant.permissions)
        entry["grantable_permissions"].update(grant.grantable_permissions)
    return {
        identity: Grant(
            principal=identity[0],
            resource=identity[1],
            permissions=tuple(values["permissions"]),
            grantable_permissions=tuple(values["grantable_permissions"]),
        )
        for identity, values in merged.items()
    }


def grant_target(grant: Grant) -> str:
    return "{} -> {}".format(grant.principal, grant.resource.identity)
