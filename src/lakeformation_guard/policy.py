"""Python-native policy authoring primitives for lfguard.

The policy layer keeps the public model small:

* users define permission group names;
* lfguard provides a few safe permission templates;
* database, table, and column LF-Tag assignments are explicit;
* LF-Tag assignment scope decides whether a tag may narrow columns.
"""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple, Type, TypeVar, Union

from .io import dumps_json, dumps_yaml
from .lint import lint_desired
from .models import (
    DesiredState,
    Grant,
    LFTagDefinition,
    LFTagKeyMetadata,
    ResourceRef,
    ResourceTagAssignment,
)


class TagAssignmentScope(str, Enum):
    """Catalog levels where an LF-Tag key may be assigned."""

    DATABASE = "database"
    TABLE = "table"
    COLUMN = "column"


TAG_ASSIGNMENT_SCOPE_ORDER = {
    TagAssignmentScope.DATABASE: 0,
    TagAssignmentScope.TABLE: 1,
    TagAssignmentScope.COLUMN: 2,
}


class PermissionTemplate(str, Enum):
    """Package-defined permission behavior used by policy groups."""

    READER = "reader"
    EDITOR = "editor"
    PRODUCER = "producer"
    TABLE_CREATOR = "table_creator"
    DATABASE_CREATOR = "database_creator"
    STEWARD = "steward"
    ADMIN = "admin"
    DATA_LOCATION_ACCESS = "data_location_access"


TagAssignmentScopeLike = Union[TagAssignmentScope, str]
TagAssignmentScopeInput = Union[TagAssignmentScopeLike, Iterable[TagAssignmentScopeLike]]

TEnum = TypeVar("TEnum", bound=Enum)

__all__ = [
    "LakePolicy",
    "PermissionGroup",
    "PermissionIntent",
    "PermissionTemplate",
    "RoleBinding",
    "TagAssignmentScope",
    "TagKey",
    "admin",
    "data_location_access",
    "database_creator",
    "editor",
    "load_policy",
    "producer",
    "reader",
    "steward",
    "table_creator",
]


@dataclass(frozen=True)
class TagKey:
    """Metadata for an LF-Tag key used by high-level policy authoring."""

    key: str
    values: Tuple[str, ...]
    assignable_to: Tuple[TagAssignmentScope, ...]
    catalog_id: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _clean_lower_token(self.key, field_name="tag key"))
        object.__setattr__(self, "catalog_id", _optional_str(self.catalog_id))
        object.__setattr__(
            self,
            "values",
            _string_tuple(self.values, field_name="tag values", allow_wildcard=False),
        )
        object.__setattr__(
            self,
            "assignable_to",
            _enum_tuple(self.assignable_to, TagAssignmentScope, field_name="assignable_to"),
        )

    @property
    def can_narrow_columns(self) -> bool:
        """Return whether this tag can make only some table columns visible."""

        return TagAssignmentScope.COLUMN in self.assignable_to

    @property
    def identity(self) -> str:
        if not self.catalog_id:
            return self.key
        return "{}:{}".format(self.catalog_id, self.key)


@dataclass(frozen=True)
class PermissionIntent:
    """A permission template plus its LF-Tag filter expression."""

    permission_template: PermissionTemplate
    filters: Mapping[str, Tuple[str, ...]]
    resource: Optional[ResourceRef] = None
    permissions: Tuple[str, ...] = field(default_factory=tuple)
    catalog_id: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "permission_template",
            _coerce_enum(
                self.permission_template,
                PermissionTemplate,
                field_name="permission_template",
            ),
        )
        normalized: Dict[str, Tuple[str, ...]] = {}
        for key, values in self.filters.items():
            normalized[_clean_lower_token(key, field_name="tag filter key")] = (
                _filter_values(values)
            )
        object.__setattr__(self, "filters", normalized)
        object.__setattr__(self, "permissions", _permission_tuple(self.permissions))
        object.__setattr__(self, "catalog_id", _optional_str(self.catalog_id))

    def where(
        self,
        filters: Optional[Mapping[str, Any]] = None,
        **tag_filters: Any,
    ) -> "PermissionIntent":
        """Return a copy with additional tag filters."""

        merged = dict(self.filters)
        for key, values in _merge_tag_mapping(filters, tag_filters, field_name="tag filter").items():
            merged[_clean_lower_token(key, field_name="tag filter key")] = _filter_values(values)
        return PermissionIntent(
            permission_template=self.permission_template,
            filters=merged,
            resource=self.resource,
            permissions=self.permissions,
            catalog_id=self.catalog_id,
        )

    def where_tags(self, filters: Mapping[str, Any]) -> "PermissionIntent":
        """Return a copy with tag filters from a mapping."""

        return self.where(filters)

    def in_catalog(self, catalog_id: str) -> "PermissionIntent":
        """Return a copy scoped to a Glue Data Catalog."""

        return PermissionIntent(
            permission_template=self.permission_template,
            filters=self.filters,
            resource=_resource_with_catalog(self.resource, catalog_id),
            permissions=self.permissions,
            catalog_id=catalog_id,
        )


@dataclass(frozen=True)
class PermissionGroup:
    """Named business access intent such as dataconsumer or dataengineer."""

    name: str
    intent: PermissionIntent

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean_name(self.name, field_name="permission group"))
        if not isinstance(self.intent, PermissionIntent):
            raise ValueError(
                "permission group intent must be created by reader(), editor(), "
                "producer(), table_creator(), database_creator(), steward(), "
                "admin(), or data_location_access()"
            )


@dataclass(frozen=True)
class RoleBinding:
    """Assignment from one IAM role principal to one or more permission groups."""

    principal: str
    groups: Tuple[str, ...]

    def __post_init__(self) -> None:
        principal = self.principal.strip()
        if not principal:
            raise ValueError("principal must not be empty")
        object.__setattr__(self, "principal", principal)
        object.__setattr__(
            self,
            "groups",
            _name_tuple(self.groups, field_name="role binding groups"),
        )


class LakePolicy:
    """Container for tag keys, permission groups, and role bindings."""

    def __init__(self) -> None:
        self._tag_keys: Dict[Tuple[Optional[str], str], TagKey] = {}
        self._groups: Dict[str, PermissionGroup] = {}
        self._bindings: list[RoleBinding] = []
        self._resource_tag_values: Dict[ResourceRef, Dict[str, str]] = {}
        self._resource_tag_scopes: Dict[ResourceRef, TagAssignmentScope] = {}

    @property
    def tag_keys(self) -> Tuple[TagKey, ...]:
        return tuple(self._tag_keys[key] for key in sorted(self._tag_keys, key=_tag_key_sort_key))

    @property
    def groups(self) -> Tuple[PermissionGroup, ...]:
        return tuple(self._groups[name] for name in sorted(self._groups))

    @property
    def bindings(self) -> Tuple[RoleBinding, ...]:
        return tuple(self._bindings)

    @property
    def resource_tags(self) -> Tuple[ResourceTagAssignment, ...]:
        return tuple(
            ResourceTagAssignment(
                resource=resource,
                tags={key: frozenset((value,)) for key, value in sorted(tags.items())},
            )
            for resource, tags in sorted(
                self._resource_tag_values.items(),
                key=lambda item: item[0].identity,
            )
        )

    def tag_key(
        self,
        key: str,
        *,
        values: Union[str, Iterable[str]],
        assignable_to: TagAssignmentScopeInput,
        catalog_id: Optional[str] = None,
    ) -> TagKey:
        """Define an LF-Tag key and where it may be assigned."""

        tag_key = TagKey(
            key=key,
            values=_string_tuple(values, field_name="tag values", allow_wildcard=False),
            assignable_to=_enum_tuple(
                assignable_to,
                TagAssignmentScope,
                field_name="assignable_to",
            ),
            catalog_id=catalog_id,
        )
        identity = _tag_key_identity(tag_key.catalog_id, tag_key.key)
        if identity in self._tag_keys:
            raise ValueError("tag key {!r} is already defined".format(tag_key.identity))
        self._tag_keys[identity] = tag_key
        return tag_key

    def group(self, name: str, intent: PermissionIntent) -> PermissionGroup:
        """Define a permission group from a safe permission template."""

        group = PermissionGroup(name=name, intent=intent)
        if group.name in self._groups:
            raise ValueError("permission group {!r} is already defined".format(group.name))
        self._groups[group.name] = group
        return group

    permission_group = group

    def tag_database(
        self,
        database: str,
        *,
        catalog_id: Optional[str] = None,
        tags: Optional[Mapping[str, str]] = None,
        **tag_kwargs: str,
    ) -> ResourceTagAssignment:
        """Assign LF-Tags to a database."""

        return self._tag_resource(
            ResourceRef(kind="database", database_name=database, catalog_id=catalog_id),
            TagAssignmentScope.DATABASE,
            _merge_tag_mapping(tags, tag_kwargs, field_name="resource tag assignment"),
        )

    def tag_table(
        self,
        database: str,
        table: str,
        *,
        catalog_id: Optional[str] = None,
        tags: Optional[Mapping[str, str]] = None,
        **tag_kwargs: str,
    ) -> ResourceTagAssignment:
        """Assign LF-Tags to a table."""

        return self._tag_resource(
            ResourceRef(kind="table", database_name=database, table_name=table, catalog_id=catalog_id),
            TagAssignmentScope.TABLE,
            _merge_tag_mapping(tags, tag_kwargs, field_name="resource tag assignment"),
        )

    def tag_columns(
        self,
        database: str,
        table: str,
        columns: Union[str, Iterable[str]],
        *,
        catalog_id: Optional[str] = None,
        tags: Optional[Mapping[str, str]] = None,
        **tag_kwargs: str,
    ) -> ResourceTagAssignment:
        """Assign LF-Tags to one or more columns in a table."""

        column_names = (columns,) if isinstance(columns, str) else tuple(columns)
        return self._tag_resource(
            ResourceRef(
                kind="table_with_columns",
                database_name=database,
                table_name=table,
                columns=tuple(column_names),
                catalog_id=catalog_id,
            ),
            TagAssignmentScope.COLUMN,
            _merge_tag_mapping(tags, tag_kwargs, field_name="resource tag assignment"),
        )

    def bind_role(self, principal: str, groups: Union[str, Iterable[str]]) -> RoleBinding:
        """Bind an IAM role principal to one or more permission groups."""

        group_names = (groups,) if isinstance(groups, str) else tuple(groups)
        binding = RoleBinding(principal=principal, groups=group_names)
        self._bindings.append(binding)
        return binding

    def validate(self) -> None:
        """Validate references, tag values, and column-narrowing safety rules."""

        for group in self.groups:
            self._validate_group(group)

        for resource, tags in sorted(
            self._resource_tag_values.items(),
            key=lambda item: item[0].identity,
        ):
            self._validate_resource_tags(resource, tags)

        for binding in self.bindings:
            for group_name in binding.groups:
                if group_name not in self._groups:
                    raise ValueError(
                        "role binding for {!r} references undefined permission group {!r}".format(
                            binding.principal,
                            group_name,
                        )
                    )

    def to_desired_state(self) -> DesiredState:
        """Compile the high-level policy into normal lfguard desired state."""

        self.validate()
        grants = []
        for binding in self.bindings:
            for group_name in binding.groups:
                group = self._groups[group_name]
                grants.extend(self._grants_for_group(binding.principal, group))

        desired = DesiredState(
            lf_tags=tuple(LFTagDefinition(tag.key, tag.values, catalog_id=tag.catalog_id) for tag in self.tag_keys),
            lf_tag_key_metadata=tuple(
                LFTagKeyMetadata(tag.key, tuple(scope.value for scope in tag.assignable_to), catalog_id=tag.catalog_id)
                for tag in self.tag_keys
            ),
            resource_tags=self.resource_tags,
            grants=tuple(sorted(set(grants))),
        )
        error_findings = [
            finding for finding in lint_desired(desired) if finding.severity == "error"
        ]
        if error_findings:
            rendered = "; ".join(
                "{}: {}".format(finding.code, finding.message)
                for finding in error_findings
            )
            raise ValueError("generated desired state failed lint: {}".format(rendered))
        return desired

    def write_desired(self, path: Union[str, Path]) -> None:
        """Write compiled desired state as JSON or YAML based on file extension."""

        output_path = Path(path)
        data = self.to_desired_state().to_dict()
        if output_path.suffix.lower() in {".yaml", ".yml"}:
            text = "# Generated by policy.py. Do not edit directly.\n" + dumps_yaml(data)
        else:
            text = dumps_json(data)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")

    def _tag_resource(
        self,
        resource: ResourceRef,
        assignment_scope: TagAssignmentScope,
        tags: Mapping[str, Any],
    ) -> ResourceTagAssignment:
        if not tags:
            raise ValueError(
                "resource tag assignment for {} must include at least one tag".format(
                    resource.identity
                )
            )

        normalized = {
            _clean_lower_token(key, field_name="resource tag key"): _single_tag_value(value)
            for key, value in tags.items()
        }
        existing = self._resource_tag_values.setdefault(resource, {})
        self._resource_tag_scopes[resource] = assignment_scope
        for key, value in normalized.items():
            if key in existing and existing[key] != value:
                raise ValueError(
                    "resource {} already has LF-Tag {}={!r}; cannot also assign {!r}".format(
                        resource.identity,
                        key,
                        existing[key],
                        value,
                    )
                )
            existing[key] = value
        return ResourceTagAssignment(
            resource=resource,
            tags={key: frozenset((value,)) for key, value in sorted(existing.items())},
        )

    def _validate_resource_tags(self, resource: ResourceRef, tags: Mapping[str, str]) -> None:
        assignment_scope = self._resource_tag_scopes[resource]
        for tag_key, value in tags.items():
            definition = self._tag_key_definition(tag_key, resource.catalog_id)
            if definition is None:
                raise ValueError(
                    "resource {} references undefined tag key {!r}".format(
                        resource.identity,
                        tag_key,
                    )
                )
            if assignment_scope not in definition.assignable_to:
                raise ValueError(
                    (
                        "resource {} assigns tag key {!r} at {} scope, but that "
                        "tag is assignable only to {}"
                    ).format(
                        resource.identity,
                        tag_key,
                        assignment_scope.value,
                        ", ".join(scope.value for scope in definition.assignable_to),
                    )
                )
            if value not in definition.values:
                raise ValueError(
                    "resource {} assigns undefined value {!r} for tag key {!r}".format(
                        resource.identity,
                        value,
                        tag_key,
                    )
                )

    def _validate_group(self, group: PermissionGroup) -> None:
        if group.intent.permission_template == PermissionTemplate.DATABASE_CREATOR:
            if group.intent.filters:
                raise ValueError(
                    "database_creator permission group {!r} cannot use LF-Tag filters".format(
                        group.name
                    )
                )
            return
        if group.intent.permission_template in {
            PermissionTemplate.STEWARD,
            PermissionTemplate.ADMIN,
            PermissionTemplate.DATA_LOCATION_ACCESS,
        }:
            if group.intent.filters:
                raise ValueError(
                    "{} permission group {!r} cannot use LF-Tag filters".format(
                        group.intent.permission_template.value,
                        group.name,
                    )
                )
            if group.intent.resource is None:
                raise ValueError(
                    "{} permission group {!r} requires a direct resource".format(
                        group.intent.permission_template.value,
                        group.name,
                    )
                )
            if not group.intent.permissions:
                raise ValueError(
                    "{} permission group {!r} requires permissions".format(
                        group.intent.permission_template.value,
                        group.name,
                    )
                )
            return

        if not group.intent.filters:
            raise ValueError(
                "permission group {!r} must define at least one tag filter".format(
                    group.name
                )
            )

        for tag_key, values in group.intent.filters.items():
            definition = self._tag_key_definition(tag_key, group.intent.catalog_id)
            if definition is None:
                raise ValueError(
                    "permission group {!r} references undefined tag key {!r}".format(
                        group.name,
                        tag_key,
                    )
                )
            if group.intent.permission_template in {
                PermissionTemplate.EDITOR,
                PermissionTemplate.PRODUCER,
                PermissionTemplate.TABLE_CREATOR,
            }:
                if definition.can_narrow_columns:
                    raise ValueError(
                        (
                            "{} permission group {!r} uses tag key {!r}, but that "
                            "tag can be assigned to columns; {} filters must not "
                            "be able to narrow columns"
                        ).format(
                            group.intent.permission_template.value,
                            group.name,
                            tag_key,
                            group.intent.permission_template.value,
                        )
                    )
            undefined = sorted(
                value for value in values if value != "*" and value not in definition.values
            )
            if undefined:
                raise ValueError(
                    "permission group {!r} uses undefined values for tag key {!r}: {}".format(
                        group.name,
                        tag_key,
                        ", ".join(undefined),
                    )
                )

        if not self._database_filter_items(group):
            raise ValueError(
                "permission group {!r} needs at least one tag filter that can "
                "be assigned to databases so lfguard can grant database "
                "DESCRIBE safely".format(group.name)
            )

    def _grants_for_group(self, principal: str, group: PermissionGroup) -> Tuple[Grant, ...]:
        template = group.intent.permission_template
        if template == PermissionTemplate.DATABASE_CREATOR:
            return (
                Grant(
                    principal=principal,
                    resource=ResourceRef(kind="catalog", catalog_id=group.intent.catalog_id),
                    permissions=("CREATE_DATABASE",),
                ),
            )
        if template in {
            PermissionTemplate.STEWARD,
            PermissionTemplate.ADMIN,
            PermissionTemplate.DATA_LOCATION_ACCESS,
        }:
            return (
                Grant(
                    principal=principal,
                    resource=group.intent.resource,
                    permissions=group.intent.permissions,
                ),
            )

        database_permissions = ("DESCRIBE",)
        if template in {PermissionTemplate.PRODUCER, PermissionTemplate.TABLE_CREATOR}:
            database_permissions = ("CREATE_TABLE", "DESCRIBE")

        table_permissions = {
            PermissionTemplate.READER: ("DESCRIBE", "SELECT"),
            PermissionTemplate.EDITOR: ("DELETE", "DESCRIBE", "INSERT", "SELECT"),
            PermissionTemplate.PRODUCER: ("DELETE", "DESCRIBE", "INSERT", "SELECT"),
            PermissionTemplate.TABLE_CREATOR: ("DELETE", "DESCRIBE", "INSERT", "SELECT"),
        }[template]

        return (
            Grant(
                principal=principal,
                resource=ResourceRef(
                    kind="lf_tag_policy",
                    resource_type="DATABASE",
                    expression=self._database_filter_items(group),
                    catalog_id=group.intent.catalog_id,
                ),
                permissions=database_permissions,
            ),
            Grant(
                principal=principal,
                resource=ResourceRef(
                    kind="lf_tag_policy",
                    resource_type="TABLE",
                    expression=_expression_items(group.intent.filters),
                    catalog_id=group.intent.catalog_id,
                ),
                permissions=table_permissions,
            ),
        )

    def _database_filter_items(self, group: PermissionGroup) -> Tuple[Any, ...]:
        return _expression_items(
            {
                key: values
                for key, values in group.intent.filters.items()
                if TagAssignmentScope.DATABASE in self._tag_key_definition(key, group.intent.catalog_id).assignable_to
            }
        )

    def _tag_key_definition(self, key: str, catalog_id: Optional[str]) -> Optional[TagKey]:
        key = _clean_lower_token(key, field_name="tag key")
        if catalog_id:
            scoped = self._tag_keys.get(_tag_key_identity(catalog_id, key))
            if scoped:
                return scoped
            return self._tag_keys.get(_tag_key_identity(None, key))
        unscoped = self._tag_keys.get(_tag_key_identity(None, key))
        if unscoped:
            return unscoped
        scoped_matches = [
            tag_key
            for tag_identity, tag_key in self._tag_keys.items()
            if tag_identity[0] and tag_identity[1] == key
        ]
        if len(scoped_matches) == 1:
            return scoped_matches[0]
        return None


def reader(*, catalog_id: Optional[str] = None) -> PermissionIntent:
    """Read approved existing tables."""

    return PermissionIntent(permission_template=PermissionTemplate.READER, filters={}, catalog_id=catalog_id)


def editor(*, catalog_id: Optional[str] = None) -> PermissionIntent:
    """Read and mutate approved existing tables without creating tables."""

    return PermissionIntent(permission_template=PermissionTemplate.EDITOR, filters={}, catalog_id=catalog_id)


def producer(*, catalog_id: Optional[str] = None) -> PermissionIntent:
    """Create tables in approved databases, and read/mutate approved tables."""

    return PermissionIntent(permission_template=PermissionTemplate.PRODUCER, filters={}, catalog_id=catalog_id)


def table_creator(*, catalog_id: Optional[str] = None) -> PermissionIntent:
    """Create tables in approved databases, and read/mutate approved tables."""

    return PermissionIntent(permission_template=PermissionTemplate.TABLE_CREATOR, filters={}, catalog_id=catalog_id)


def database_creator(*, catalog_id: Optional[str] = None) -> PermissionIntent:
    """Create new databases in the catalog."""

    return PermissionIntent(permission_template=PermissionTemplate.DATABASE_CREATOR, filters={}, catalog_id=catalog_id)


def steward(expression_name: str, *, catalog_id: Optional[str] = None) -> PermissionIntent:
    """Use a named LF-Tag expression when granting access."""

    return PermissionIntent(
        permission_template=PermissionTemplate.STEWARD,
        filters={},
        resource=ResourceRef(kind="lf_tag_expression", expression_name=expression_name, catalog_id=catalog_id),
        permissions=("DESCRIBE", "GRANT_WITH_LF_TAG_EXPRESSION"),
        catalog_id=catalog_id,
    )


def admin(*, catalog_id: Optional[str] = None) -> PermissionIntent:
    """Create databases, LF-Tags, and named LF-Tag expressions in a catalog."""

    return PermissionIntent(
        permission_template=PermissionTemplate.ADMIN,
        filters={},
        resource=ResourceRef(kind="catalog", catalog_id=catalog_id),
        permissions=("CREATE_DATABASE", "CREATE_LF_TAG", "CREATE_LF_TAG_EXPRESSION", "DESCRIBE"),
        catalog_id=catalog_id,
    )


def data_location_access(location: str, *, catalog_id: Optional[str] = None) -> PermissionIntent:
    """Use a registered data location for approved producer workflows."""

    return PermissionIntent(
        permission_template=PermissionTemplate.DATA_LOCATION_ACCESS,
        filters={},
        resource=ResourceRef(kind="data_location", location=location, catalog_id=catalog_id),
        permissions=("DATA_LOCATION_ACCESS",),
        catalog_id=catalog_id,
    )


def load_policy(path: Union[str, Path], *, object_name: str = "policy") -> LakePolicy:
    """Load a LakePolicy object or factory from a Python policy file."""

    policy_path = Path(path)
    if not policy_path.exists():
        raise ValueError("policy file does not exist: {}".format(policy_path))
    spec = importlib.util.spec_from_file_location("_lfguard_user_policy", policy_path)
    if spec is None or spec.loader is None:
        raise ValueError("could not load policy file: {}".format(policy_path))

    module = importlib.util.module_from_spec(spec)
    original_path = list(sys.path)
    sys.path.insert(0, str(policy_path.parent))
    try:
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise RuntimeError(
                "could not execute policy file {}: {}".format(policy_path, exc)
            ) from exc
    finally:
        sys.path = original_path

    if not hasattr(module, object_name):
        raise ValueError(
            "policy file {} must define a LakePolicy named {!r}".format(
                policy_path,
                object_name,
            )
        )

    value = getattr(module, object_name)
    if callable(value):
        try:
            value = value()
        except Exception as exc:
            raise RuntimeError(
                "policy file {} object {!r} failed: {}".format(
                    policy_path,
                    object_name,
                    exc,
                )
            ) from exc
    if not isinstance(value, LakePolicy):
        raise ValueError(
            "policy file {} object {!r} must be a LakePolicy or a function returning one".format(
                policy_path,
                object_name,
            )
        )
    return value


def _expression_items(filters: Mapping[str, Tuple[str, ...]]) -> Tuple[Any, ...]:
    from .models import LFTagValue

    return tuple(LFTagValue(key, values) for key, values in sorted(filters.items()))


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _tag_key_identity(catalog_id: Optional[str], key: str) -> Tuple[Optional[str], str]:
    return (_optional_str(catalog_id), key)


def _tag_key_sort_key(identity: Tuple[Optional[str], str]) -> str:
    return "{}:{}".format(identity[0] or "", identity[1])


def _resource_with_catalog(resource: Optional[ResourceRef], catalog_id: Optional[str]) -> Optional[ResourceRef]:
    if resource is None:
        return None
    return ResourceRef(
        kind=resource.kind,
        database_name=resource.database_name,
        table_name=resource.table_name,
        columns=resource.columns,
        location=resource.location,
        resource_type=resource.resource_type,
        expression=resource.expression,
        expression_name=resource.expression_name,
        filter_name=resource.filter_name,
        catalog_id=catalog_id,
    )


def _coerce_enum(value: Union[TEnum, str], enum_type: Type[TEnum], *, field_name: str) -> TEnum:
    if isinstance(value, enum_type):
        return value
    normalized = str(value).strip().lower().replace("-", "_")
    try:
        return enum_type(normalized)
    except ValueError as exc:
        expected = ", ".join(item.value for item in enum_type)
        raise ValueError("{} must be one of: {}".format(field_name, expected)) from exc


def _enum_tuple(values: Any, enum_type: Type[TEnum], *, field_name: str) -> Tuple[TEnum, ...]:
    if isinstance(values, (str, Enum)):
        raw_values = (values,)
    else:
        raw_values = tuple(values)
    normalized = tuple(
        sorted(
            {_coerce_enum(value, enum_type, field_name=field_name) for value in raw_values},
            key=lambda item: (
                TAG_ASSIGNMENT_SCOPE_ORDER[item]
                if isinstance(item, TagAssignmentScope)
                else item.value
            ),
        )
    )
    if not normalized:
        raise ValueError("{} must contain at least one value".format(field_name))
    return normalized


def _filter_values(values: Any) -> Tuple[str, ...]:
    if isinstance(values, str):
        return _string_tuple([values], field_name="tag filter values", allow_wildcard=True)
    if isinstance(values, Iterable):
        return _string_tuple(values, field_name="tag filter values", allow_wildcard=True)
    raise ValueError("tag filter values must be a string or iterable of strings")


def _permission_tuple(values: Iterable[str]) -> Tuple[str, ...]:
    normalized = tuple(sorted({str(value).strip().upper() for value in values if str(value).strip()}))
    return normalized


def _merge_tag_mapping(
    explicit: Optional[Mapping[str, Any]],
    keyword_values: Mapping[str, Any],
    *,
    field_name: str,
) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    if explicit is not None:
        if not isinstance(explicit, Mapping):
            raise ValueError("{} must be a mapping".format(field_name))
        merged.update({str(key): value for key, value in explicit.items()})
    for key, value in keyword_values.items():
        if key in merged and merged[key] != value:
            raise ValueError("{} has conflicting values for tag key {!r}".format(field_name, key))
        merged[key] = value
    return merged


def _single_tag_value(value: Any) -> str:
    if isinstance(value, str):
        return _clean_lower_token(value, field_name="resource tag value")
    raise ValueError("resource tag value must be a string")


def _string_tuple(values: Any, *, field_name: str, allow_wildcard: bool) -> Tuple[str, ...]:
    raw_values = (values,) if isinstance(values, str) else tuple(values)
    normalized = tuple(
        sorted(
            _clean_lower_token(str(value), field_name=field_name, allow_wildcard=allow_wildcard)
            for value in raw_values
        )
    )
    if not normalized:
        raise ValueError("{} must contain at least one value".format(field_name))
    return normalized


def _name_tuple(values: Iterable[str], *, field_name: str) -> Tuple[str, ...]:
    normalized = tuple(sorted({_clean_name(value, field_name=field_name) for value in values}))
    if not normalized:
        raise ValueError("{} must contain at least one value".format(field_name))
    return normalized


def _clean_lower_token(value: str, *, field_name: str, allow_wildcard: bool = False) -> str:
    token = value.strip()
    if not token:
        raise ValueError("{} must not be empty".format(field_name))
    if allow_wildcard and token == "*":
        return token
    if token != token.lower():
        raise ValueError("{} must be lower-case: {!r}".format(field_name, value))
    return token


def _clean_name(value: str, *, field_name: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("{} must not be empty".format(field_name))
    return name
