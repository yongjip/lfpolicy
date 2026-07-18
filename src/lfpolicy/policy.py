"""Python-native policy authoring primitives for lfpolicy.

The policy layer keeps the public model small:

* users define permission group names;
* lfpolicy provides a few safe permission templates;
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
    LFTagExpressionDefinition,
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
    "NamedLFTagExpression",
    "PermissionGroup",
    "PermissionIntent",
    "PermissionTemplate",
    "PolicyValidationError",
    "PolicyValidationFinding",
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
class PolicyValidationFinding:
    """Actionable validation finding for Python-native policy authoring."""

    code: str
    path: str
    message: str
    suggestion: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "code": self.code,
            "path": self.path,
            "message": self.message,
        }
        if self.suggestion:
            payload["suggestion"] = self.suggestion
        return payload


class PolicyValidationError(ValueError):
    """Raised when a LakePolicy contains one or more validation findings."""

    def __init__(self, findings: Iterable[PolicyValidationFinding]) -> None:
        self.findings = tuple(findings)
        super().__init__(_render_policy_validation_error(self.findings))


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
class NamedLFTagExpression:
    """Configuration for compiling a group filter into a reusable named expression."""

    name: str
    description: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "name",
            _clean_name(self.name, field_name="named LF-Tag expression"),
        )
        object.__setattr__(self, "description", _optional_str(self.description))


@dataclass(frozen=True)
class PermissionIntent:
    """A permission template plus its LF-Tag filter expression."""

    permission_template: PermissionTemplate
    filters: Mapping[str, Tuple[str, ...]]
    resource: Optional[ResourceRef] = None
    permissions: Tuple[str, ...] = field(default_factory=tuple)
    catalog_id: Optional[str] = None
    named_expression: Optional[NamedLFTagExpression] = None

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
        if self.named_expression is not None and not isinstance(
            self.named_expression,
            NamedLFTagExpression,
        ):
            raise ValueError("named_expression must be created by as_named_expression()")

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
            named_expression=self.named_expression,
        )

    def where_tags(self, filters: Mapping[str, Any]) -> "PermissionIntent":
        """Return a copy with tag filters from a mapping."""

        return self.where(filters)

    def as_named_expression(
        self,
        name: str,
        *,
        description: Optional[str] = None,
    ) -> "PermissionIntent":
        """Return a copy that compiles the LF-Tag filter as a named expression."""

        return PermissionIntent(
            permission_template=self.permission_template,
            filters=self.filters,
            resource=self.resource,
            permissions=self.permissions,
            catalog_id=self.catalog_id,
            named_expression=NamedLFTagExpression(name=name, description=description),
        )

    def in_catalog(self, catalog_id: str) -> "PermissionIntent":
        """Return a copy scoped to a Glue Data Catalog."""

        return PermissionIntent(
            permission_template=self.permission_template,
            filters=self.filters,
            resource=_resource_with_catalog(self.resource, catalog_id),
            permissions=self.permissions,
            catalog_id=catalog_id,
            named_expression=self.named_expression,
        )


@dataclass(frozen=True)
class PermissionGroup:
    """Named business access intent such as dataconsumer or dataengineer."""

    name: str
    intent: PermissionIntent
    _owner: Optional["LakePolicy"] = field(default=None, compare=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _clean_name(self.name, field_name="permission group"))
        if not isinstance(self.intent, PermissionIntent):
            raise ValueError(
                "permission group intent must be created by reader(), editor(), "
                "producer(), table_creator(), database_creator(), steward(), "
                "admin(), or data_location_access()"
            )

    def as_named_expression(
        self,
        name: str,
        *,
        description: Optional[str] = None,
    ) -> "PermissionGroup":
        """Compile this group's LF-Tag filter into a reusable named expression."""

        group = PermissionGroup(
            name=self.name,
            intent=self.intent.as_named_expression(name, description=description),
            _owner=self._owner,
        )
        if self._owner is not None:
            self._owner._groups[self.name] = group
        return group


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

        group = PermissionGroup(name=name, intent=intent, _owner=self)
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

        findings = self.validate_findings()
        if findings:
            raise PolicyValidationError(findings)

    def validate_findings(self) -> Tuple[PolicyValidationFinding, ...]:
        """Return structured policy authoring findings without raising."""

        findings = []
        for group in self.groups:
            findings.extend(self._group_validation_findings(group))
        findings.extend(self._named_expression_validation_findings())

        for resource, tags in sorted(
            self._resource_tag_values.items(),
            key=lambda item: item[0].identity,
        ):
            findings.extend(self._resource_tag_validation_findings(resource, tags))

        for binding_index, binding in enumerate(self.bindings, start=1):
            for group_name in binding.groups:
                if group_name not in self._groups:
                    findings.append(
                        PolicyValidationFinding(
                            code="POLICY_UNDEFINED_PERMISSION_GROUP",
                            path="bindings[{}].groups.{}".format(binding_index, group_name),
                            message=(
                                "role binding for {!r} references undefined permission group {!r}".format(
                                    binding.principal,
                                    group_name,
                                )
                            ),
                            suggestion=(
                                "Define policy.group({!r}, ...) before bind_role(), "
                                "or remove {!r} from this binding."
                            ).format(group_name, group_name),
                        )
                    )
        return tuple(findings)

    def _named_expression_validation_findings(self) -> Tuple[PolicyValidationFinding, ...]:
        findings = []
        seen: Dict[Tuple[Optional[str], str], Tuple[str, Tuple[Any, ...], Optional[str]]] = {}
        for group in self.groups:
            named_expression = group.intent.named_expression
            if named_expression is None:
                continue
            path_prefix = "groups.{}.named_expression".format(group.name)
            if group.intent.permission_template in {
                PermissionTemplate.DATABASE_CREATOR,
                PermissionTemplate.STEWARD,
                PermissionTemplate.ADMIN,
                PermissionTemplate.DATA_LOCATION_ACCESS,
            }:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_NAMED_EXPRESSION_UNSUPPORTED",
                        path=path_prefix,
                        message=(
                            "{} permission group {!r} cannot compile a filter into a named LF-Tag expression"
                        ).format(group.intent.permission_template.value, group.name),
                        suggestion=(
                            "Use as_named_expression(...) only on filtered bundles "
                            "such as reader(), producer(), editor(), or table_creator()."
                        ),
                    )
                )
                continue
            expression = _expression_items(group.intent.filters)
            conflict_key = (group.intent.catalog_id, named_expression.name)
            current = (group.name, expression, named_expression.description)
            previous = seen.get(conflict_key)
            if previous is not None and previous[1:] != current[1:]:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_NAMED_EXPRESSION_CONFLICT",
                        path=path_prefix,
                        message=(
                            "permission group {!r} defines named LF-Tag expression {!r} differently from group {!r}"
                        ).format(group.name, named_expression.name, previous[0]),
                        suggestion="Use a unique expression name or make every group with the same name compile to the same LF-Tag expression body.",
                    )
                )
            else:
                seen[conflict_key] = current
            for tag_key in group.intent.filters:
                definition = self._tag_key_definition(tag_key, group.intent.catalog_id)
                if definition is None:
                    continue
                if TagAssignmentScope.DATABASE not in definition.assignable_to:
                    findings.append(
                        PolicyValidationFinding(
                            code="POLICY_NAMED_EXPRESSION_DATABASE_SCOPE_UNSUPPORTED",
                            path="{}.filters.{}".format(path_prefix, tag_key),
                            message=(
                                "named LF-Tag expression group {!r} uses tag key {!r}, but that key cannot be assigned to databases"
                            ).format(group.name, tag_key),
                            suggestion=(
                                "Either make the tag key database-assignable or leave "
                                "this group inline so lfpolicy can keep the database "
                                "grant narrowed to database-compatible filters."
                            ),
                        )
                    )
        return tuple(findings)

    def to_desired_state(self) -> DesiredState:
        """Compile the high-level policy into normal lfpolicy desired state."""

        self.validate()
        lf_tag_expressions = []
        grants = []
        for group in self.groups:
            named_expression = group.intent.named_expression
            if named_expression is not None:
                lf_tag_expressions.append(
                    LFTagExpressionDefinition(
                        name=named_expression.name,
                        expression=_expression_items(group.intent.filters),
                        description=named_expression.description,
                        catalog_id=group.intent.catalog_id,
                    )
                )
        for binding in self.bindings:
            for group_name in binding.groups:
                group = self._groups[group_name]
                grants.extend(self._grants_for_group(binding.principal, group))

        desired = DesiredState(
            lf_tags=tuple(LFTagDefinition(tag.key, tag.values, catalog_id=tag.catalog_id) for tag in self.tag_keys),
            lf_tag_expressions=tuple(sorted(set(lf_tag_expressions))),
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
            raise PolicyValidationError(
                PolicyValidationFinding(
                    code="POLICY_GENERATED_DESIRED_LINT_ERROR",
                    path="generated_desired.{}".format(finding.id),
                    message="{}: {}".format(finding.code, finding.message),
                    suggestion="Fix the Python policy so generated desired state passes lfpolicy lint.",
                )
                for finding in error_findings
            )
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

    def _resource_tag_validation_findings(
        self,
        resource: ResourceRef,
        tags: Mapping[str, str],
    ) -> Tuple[PolicyValidationFinding, ...]:
        findings = []
        assignment_scope = self._resource_tag_scopes[resource]
        for tag_key, value in tags.items():
            definition = self._tag_key_definition(tag_key, resource.catalog_id)
            if definition is None:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_RESOURCE_UNDEFINED_TAG_KEY",
                        path="resource_tags.{}.{}".format(resource.identity, tag_key),
                        message="resource {} references undefined tag key {!r}".format(
                            resource.identity,
                            tag_key,
                        ),
                        suggestion="Define policy.tag_key({!r}, ...) before tagging this resource.".format(tag_key),
                    )
                )
                continue
            if assignment_scope not in definition.assignable_to:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_RESOURCE_TAG_SCOPE_UNSUPPORTED",
                        path="resource_tags.{}.{}".format(resource.identity, tag_key),
                        message=(
                            "resource {} assigns tag key {!r} at {} scope, but that "
                            "tag is assignable only to {}"
                        ).format(
                            resource.identity,
                            tag_key,
                            assignment_scope.value,
                            ", ".join(scope.value for scope in definition.assignable_to),
                        ),
                        suggestion="Add TagAssignmentScope.{} to the tag_key(..., assignable_to=...) declaration or move the tag assignment to a supported resource level.".format(
                            assignment_scope.name
                        ),
                    )
                )
            if value not in definition.values:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_RESOURCE_UNDEFINED_TAG_VALUE",
                        path="resource_tags.{}.{}".format(resource.identity, tag_key),
                        message="resource {} assigns undefined value {!r} for tag key {!r}".format(
                            resource.identity,
                            value,
                            tag_key,
                        ),
                        suggestion="Add {!r} to policy.tag_key({!r}, values=[...]) or correct the resource tag value.".format(
                            value,
                            tag_key,
                        ),
                    )
                )
        return tuple(findings)

    def _group_validation_findings(self, group: PermissionGroup) -> Tuple[PolicyValidationFinding, ...]:
        findings = []
        path_prefix = "groups.{}".format(group.name)
        if group.intent.permission_template == PermissionTemplate.DATABASE_CREATOR:
            if group.intent.filters:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_DIRECT_GROUP_FILTERS_UNSUPPORTED",
                        path="{}.filters".format(path_prefix),
                        message="database_creator permission group {!r} cannot use LF-Tag filters".format(
                            group.name
                        ),
                        suggestion="Remove .where(...) from database_creator(), or use reader()/producer() for LF-Tag filtered access.",
                    )
                )
            return tuple(findings)
        if group.intent.permission_template in {
            PermissionTemplate.STEWARD,
            PermissionTemplate.ADMIN,
            PermissionTemplate.DATA_LOCATION_ACCESS,
        }:
            if group.intent.filters:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_DIRECT_GROUP_FILTERS_UNSUPPORTED",
                        path="{}.filters".format(path_prefix),
                        message="{} permission group {!r} cannot use LF-Tag filters".format(
                            group.intent.permission_template.value,
                            group.name,
                        ),
                        suggestion="Remove .where(...) from this direct bundle; direct bundles are scoped by their resource argument.",
                    )
                )
            if group.intent.resource is None:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_DIRECT_GROUP_RESOURCE_REQUIRED",
                        path="{}.resource".format(path_prefix),
                        message="{} permission group {!r} requires a direct resource".format(
                            group.intent.permission_template.value,
                            group.name,
                        ),
                        suggestion="Use steward(name), admin(), or data_location_access(location) so the bundle supplies a resource.",
                    )
                )
            if not group.intent.permissions:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_DIRECT_GROUP_PERMISSIONS_REQUIRED",
                        path="{}.permissions".format(path_prefix),
                        message="{} permission group {!r} requires permissions".format(
                            group.intent.permission_template.value,
                            group.name,
                        ),
                        suggestion="Use the package-provided direct bundle helper instead of constructing PermissionIntent manually.",
                    )
                )
            return tuple(findings)

        if not group.intent.filters:
            findings.append(
                PolicyValidationFinding(
                    code="POLICY_GROUP_FILTER_REQUIRED",
                    path="{}.filters".format(path_prefix),
                    message="permission group {!r} must define at least one tag filter".format(
                        group.name
                    ),
                    suggestion="Add .where(tag_key='value') to the template, or use a direct bundle such as data_location_access().",
                )
            )
            return tuple(findings)

        for tag_key, values in group.intent.filters.items():
            definition = self._tag_key_definition(tag_key, group.intent.catalog_id)
            if definition is None:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_GROUP_UNDEFINED_TAG_KEY",
                        path="{}.filters.{}".format(path_prefix, tag_key),
                        message="permission group {!r} references undefined tag key {!r}".format(
                            group.name,
                            tag_key,
                        ),
                        suggestion="Define policy.tag_key({!r}, ...) before using it in this group filter.".format(tag_key),
                    )
                )
                continue
            if group.intent.permission_template in {
                PermissionTemplate.EDITOR,
                PermissionTemplate.PRODUCER,
                PermissionTemplate.TABLE_CREATOR,
            }:
                if definition.can_narrow_columns:
                    findings.append(
                        PolicyValidationFinding(
                            code="POLICY_MUTATING_GROUP_COLUMN_NARROWING_TAG",
                            path="{}.filters.{}".format(path_prefix, tag_key),
                            message=(
                                "{} permission group {!r} uses tag key {!r}, but that "
                                "tag can be assigned to columns; {} filters must not "
                                "be able to narrow columns"
                            ).format(
                                group.intent.permission_template.value,
                                group.name,
                                tag_key,
                                group.intent.permission_template.value,
                            ),
                            suggestion="Use reader() for column-filtered access, or remove TagAssignmentScope.COLUMN from this tag key.",
                        )
                    )
            undefined = sorted(
                value for value in values if value != "*" and value not in definition.values
            )
            if undefined:
                findings.append(
                    PolicyValidationFinding(
                        code="POLICY_GROUP_UNDEFINED_TAG_VALUE",
                        path="{}.filters.{}".format(path_prefix, tag_key),
                        message="permission group {!r} uses undefined values for tag key {!r}: {}".format(
                            group.name,
                            tag_key,
                            ", ".join(undefined),
                        ),
                        suggestion="Add the value(s) to policy.tag_key({!r}, values=[...]) or correct this group filter.".format(tag_key),
                    )
                )

        if not findings and not self._database_filter_items(group):
            findings.append(
                PolicyValidationFinding(
                    code="POLICY_DATABASE_FILTER_REQUIRED",
                    path="{}.filters".format(path_prefix),
                    message=(
                        "permission group {!r} needs at least one tag filter that can "
                        "be assigned to databases so lfpolicy can grant database "
                        "DESCRIBE safely"
                    ).format(group.name),
                    suggestion="Add a database-assignable tag key such as domain to the group filter.",
                )
            )
        return tuple(findings)

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
        expression_name = (
            group.intent.named_expression.name
            if group.intent.named_expression is not None
            else None
        )
        database_resource = ResourceRef(
            kind="lf_tag_policy",
            resource_type="DATABASE",
            expression_name=expression_name,
            expression=() if expression_name else self._database_filter_items(group),
            catalog_id=group.intent.catalog_id,
        )
        table_resource = ResourceRef(
            kind="lf_tag_policy",
            resource_type="TABLE",
            expression_name=expression_name,
            expression=() if expression_name else _expression_items(group.intent.filters),
            catalog_id=group.intent.catalog_id,
        )

        return (
            Grant(
                principal=principal,
                resource=database_resource,
                permissions=database_permissions,
            ),
            Grant(
                principal=principal,
                resource=table_resource,
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
    spec = importlib.util.spec_from_file_location("_lfpolicy_user_policy", policy_path)
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


def _render_policy_validation_error(findings: Tuple[PolicyValidationFinding, ...]) -> str:
    if not findings:
        return "policy validation failed"
    lines = ["policy validation failed with {} finding(s):".format(len(findings))]
    for finding in findings:
        lines.append("- {} at {}: {}".format(finding.code, finding.path, finding.message))
        if finding.suggestion:
            lines.append("  suggestion: {}".format(finding.suggestion))
    return "\n".join(lines)


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
