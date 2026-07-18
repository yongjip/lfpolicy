"""Shared indexes for normalized Lake Formation state objects."""

from __future__ import annotations

from typing import Dict, FrozenSet, Iterable, Mapping, Optional, Set, Tuple

from .models import (
    DataCellsFilterDefinition,
    Grant,
    LFTagDefinition,
    LFTagExpressionDefinition,
    LFTagKeyMetadata,
    ResourceRef,
    ResourceTagAssignment,
)

LFTagExpressionKey = Tuple[Optional[str], str]
LFTagKey = Tuple[Optional[str], str]
DataCellsFilterKey = Tuple[Optional[str], str, str, str]


def lf_tag_key(catalog_id: Optional[str], key: str) -> LFTagKey:
    return (catalog_id, key)


def lf_tag_definition_key(tag: LFTagDefinition) -> LFTagKey:
    return lf_tag_key(tag.catalog_id, tag.key)


def lf_tag_key_identity(key: LFTagKey) -> str:
    if not key[0]:
        return "lf_tag:{}".format(key[1])
    parts = ["lf_tag"]
    parts.append("catalog={}".format(key[0]))
    parts.append("key={}".format(key[1]))
    return ":".join(parts)


def lf_tag_sort_key(key: LFTagKey) -> str:
    return "{}:{}".format(key[0] or "", key[1])


def duplicate_lf_tag_keys(
    tags: Iterable[LFTagDefinition],
) -> Tuple[LFTagKey, ...]:
    seen: Set[LFTagKey] = set()
    duplicates: Set[LFTagKey] = set()
    for tag in tags:
        key = lf_tag_definition_key(tag)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return tuple(sorted(duplicates, key=lf_tag_sort_key))


def lf_tag_index(
    tags: Iterable[LFTagDefinition],
    *,
    allow_duplicates: bool = False,
) -> Dict[LFTagKey, LFTagDefinition]:
    merged: Dict[LFTagKey, set] = {}
    for tag in tags:
        key = lf_tag_definition_key(tag)
        if key in merged and not allow_duplicates:
            raise ValueError(
                "Duplicate LF-Tag identity: {}".format(
                    lf_tag_key_identity(key)
                )
            )
        merged.setdefault(key, set()).update(tag.values)
    return {
        key: LFTagDefinition(key[1], tuple(values), catalog_id=key[0])
        for key, values in merged.items()
    }


def resolve_lf_tag_key(
    tag_index: Mapping[LFTagKey, object],
    catalog_id: Optional[str],
    key: str,
) -> Optional[LFTagKey]:
    if catalog_id:
        scoped_key = lf_tag_key(catalog_id, key)
        if scoped_key in tag_index:
            return scoped_key
        unscoped_key = lf_tag_key(None, key)
        return unscoped_key if unscoped_key in tag_index else None
    unscoped_key = lf_tag_key(None, key)
    if unscoped_key in tag_index:
        return unscoped_key
    scoped_matches = {
        candidate
        for candidate in tag_index
        if candidate[0] and candidate[1] == key
    }
    if len(scoped_matches) == 1:
        return next(iter(scoped_matches))
    return None


def lf_tag_key_metadata_key(metadata: LFTagKeyMetadata) -> LFTagKey:
    return lf_tag_key(metadata.catalog_id, metadata.key)


def lf_tag_key_metadata_identity(key: LFTagKey) -> str:
    if not key[0]:
        return "lf_tag_key_metadata:key={}".format(key[1])
    parts = ["lf_tag_key_metadata"]
    parts.append("catalog={}".format(key[0]))
    parts.append("key={}".format(key[1]))
    return ":".join(parts)


def duplicate_lf_tag_key_metadata_keys(
    metadata_items: Iterable[LFTagKeyMetadata],
) -> Tuple[LFTagKey, ...]:
    seen: Set[LFTagKey] = set()
    duplicates: Set[LFTagKey] = set()
    for metadata in metadata_items:
        key = lf_tag_key_metadata_key(metadata)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return tuple(sorted(duplicates, key=lf_tag_sort_key))


def lf_tag_expression_key(catalog_id: Optional[str], name: str) -> LFTagExpressionKey:
    return (catalog_id, name)


def lf_tag_expression_definition_key(expression: LFTagExpressionDefinition) -> LFTagExpressionKey:
    return lf_tag_expression_key(expression.catalog_id, expression.name)


def lf_tag_expression_key_identity(key: LFTagExpressionKey) -> str:
    parts = ["lf_tag_expression"]
    if key[0]:
        parts.append("catalog={}".format(key[0]))
    parts.append("name={}".format(key[1]))
    return ":".join(parts)


def duplicate_lf_tag_expression_keys(
    expressions: Iterable[LFTagExpressionDefinition],
) -> Tuple[LFTagExpressionKey, ...]:
    seen: Set[LFTagExpressionKey] = set()
    duplicates: Set[LFTagExpressionKey] = set()
    for expression in expressions:
        key = lf_tag_expression_definition_key(expression)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return tuple(sorted(duplicates, key=lf_tag_expression_sort_key))


def lf_tag_expression_index(
    expressions: Iterable[LFTagExpressionDefinition],
    *,
    allow_duplicates: bool = False,
) -> Dict[LFTagExpressionKey, LFTagExpressionDefinition]:
    result: Dict[LFTagExpressionKey, LFTagExpressionDefinition] = {}
    for expression in expressions:
        key = lf_tag_expression_definition_key(expression)
        if key in result and not allow_duplicates:
            raise ValueError(
                "Duplicate LF-Tag expression identity: {}".format(
                    lf_tag_expression_key_identity(key)
                )
            )
        result[key] = expression
    return result


def lf_tag_expression_sort_key(key: LFTagExpressionKey) -> str:
    return "{}:{}".format(key[0] or "", key[1])


def resolve_lf_tag_expression_key(
    expression_index: Mapping[LFTagExpressionKey, object],
    catalog_id: Optional[str],
    name: str,
) -> Optional[LFTagExpressionKey]:
    if catalog_id:
        key = lf_tag_expression_key(catalog_id, name)
        return key if key in expression_index else None
    unscoped_key = lf_tag_expression_key(None, name)
    if unscoped_key in expression_index:
        return unscoped_key
    scoped_matches = {
        key
        for key in expression_index
        if key[0] and key[1] == name
    }
    if len(scoped_matches) == 1:
        return next(iter(scoped_matches))
    return None


def data_cells_filter_key(
    catalog_id: Optional[str],
    database_name: str,
    table_name: str,
    name: str,
) -> DataCellsFilterKey:
    return (catalog_id, database_name, table_name, name)


def data_cells_filter_definition_key(definition: DataCellsFilterDefinition) -> DataCellsFilterKey:
    return data_cells_filter_key(
        definition.catalog_id,
        definition.database_name,
        definition.table_name,
        definition.name,
    )


def data_cells_filter_resource_key(resource: ResourceRef) -> DataCellsFilterKey:
    return data_cells_filter_key(
        resource.catalog_id,
        resource.database_name or "",
        resource.table_name or "",
        resource.filter_name or "",
    )


def data_cells_filter_sort_key(key: DataCellsFilterKey) -> str:
    return "{}:{}:{}:{}".format(key[0] or "", key[1], key[2], key[3])


def duplicate_data_cells_filter_keys(
    definitions: Iterable[DataCellsFilterDefinition],
) -> Tuple[DataCellsFilterKey, ...]:
    seen: Set[DataCellsFilterKey] = set()
    duplicates: Set[DataCellsFilterKey] = set()
    for definition in definitions:
        key = data_cells_filter_definition_key(definition)
        if key in seen:
            duplicates.add(key)
        seen.add(key)
    return tuple(sorted(duplicates, key=data_cells_filter_sort_key))


def data_cells_filter_key_identity(key: DataCellsFilterKey) -> str:
    parts = ["data_cells_filter"]
    if key[0]:
        parts.append("catalog={}".format(key[0]))
    parts.append("database={}".format(key[1]))
    parts.append("table={}".format(key[2]))
    parts.append("name={}".format(key[3]))
    return ":".join(parts)


def data_cells_filter_index(
    definitions: Iterable[DataCellsFilterDefinition],
    *,
    allow_duplicates: bool = False,
) -> Dict[DataCellsFilterKey, DataCellsFilterDefinition]:
    result: Dict[DataCellsFilterKey, DataCellsFilterDefinition] = {}
    for definition in definitions:
        key = data_cells_filter_definition_key(definition)
        if key in result and not allow_duplicates:
            raise ValueError(
                "Duplicate data cells filter identity: {}".format(
                    data_cells_filter_key_identity(key)
                )
            )
        result[key] = definition
    return result


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
