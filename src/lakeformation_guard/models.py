"""Domain models for Lake Formation guardrail desired and current state."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, Tuple, Type, TypeVar


RESOURCE_KINDS = {
    "catalog",
    "database",
    "table",
    "table_with_columns",
    "data_location",
    "lf_tag_policy",
    "lf_tag_expression",
}

TAG_ASSIGNMENT_SCOPES = {"database", "table", "column"}
TAG_ASSIGNMENT_SCOPE_ORDER = {"database": 0, "table": 1, "column": 2}
LINT_SEVERITIES = {"error", "warning", "ignore"}
UNMANAGED_ACTIONS = {"warn", "warning", "error", "ignore"}


def _normalize_kind(value: str) -> str:
    kind = value.strip().lower().replace("-", "_")
    if kind not in RESOURCE_KINDS:
        raise ValueError(
            "Unsupported resource kind {!r}. Expected one of: {}".format(
                value, ", ".join(sorted(RESOURCE_KINDS))
            )
        )
    return kind


def _string_tuple(values: Iterable[str], *, field_name: str) -> Tuple[str, ...]:
    normalized = tuple(sorted({str(value).strip() for value in values if str(value).strip()}))
    if not normalized:
        raise ValueError("{} must contain at least one value".format(field_name))
    return normalized


def _tag_assignment_scope_tuple(values: Iterable[str], *, field_name: str) -> Tuple[str, ...]:
    raw_values = _string_tuple(values, field_name=field_name)
    unsupported = sorted(set(raw_values) - TAG_ASSIGNMENT_SCOPES)
    if unsupported:
        raise ValueError(
            "{} contains unsupported scopes {}. Expected one of: {}".format(
                field_name,
                ", ".join(unsupported),
                ", ".join(sorted(TAG_ASSIGNMENT_SCOPES)),
            )
        )
    return tuple(sorted(set(raw_values), key=lambda value: TAG_ASSIGNMENT_SCOPE_ORDER[value]))


def _values_from_raw(raw: Any, *, field_name: str) -> Tuple[str, ...]:
    if isinstance(raw, str):
        return _string_tuple([raw], field_name=field_name)
    if isinstance(raw, Iterable):
        return _string_tuple([str(value) for value in raw], field_name=field_name)
    raise ValueError("{} must be a string or a list of strings".format(field_name))


def _optional_str(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _resource_name(raw: Mapping[str, Any], *names: str) -> Optional[str]:
    for name in names:
        if name in raw:
            return _optional_str(raw[name])
    return None


@dataclass(frozen=True, order=True)
class LFTagValue:
    """An LF-Tag expression item: one tag key matched to one or more values."""

    key: str
    values: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", self.key.strip())
        object.__setattr__(self, "values", _string_tuple(self.values, field_name="LF-Tag values"))
        if not self.key:
            raise ValueError("LF-Tag key must not be empty")

    @classmethod
    def from_raw(cls, key: str, values: Any) -> "LFTagValue":
        return cls(key=str(key), values=_values_from_raw(values, field_name="LF-Tag values"))

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "values": list(self.values)}


@dataclass(frozen=True, order=True)
class ResourceRef:
    """Canonical reference to a Lake Formation Data Catalog resource."""

    kind: str
    database_name: Optional[str] = None
    table_name: Optional[str] = None
    columns: Tuple[str, ...] = field(default_factory=tuple)
    location: Optional[str] = None
    resource_type: Optional[str] = None
    expression: Tuple[LFTagValue, ...] = field(default_factory=tuple)
    expression_name: Optional[str] = None
    catalog_id: Optional[str] = None

    def __post_init__(self) -> None:
        kind = _normalize_kind(self.kind)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "database_name", _optional_str(self.database_name))
        object.__setattr__(self, "table_name", _optional_str(self.table_name))
        object.__setattr__(self, "location", _optional_str(self.location))
        object.__setattr__(self, "catalog_id", _optional_str(self.catalog_id))
        object.__setattr__(self, "expression_name", _optional_str(self.expression_name))
        if self.resource_type is not None:
            object.__setattr__(self, "resource_type", self.resource_type.strip().upper())
        object.__setattr__(self, "columns", tuple(sorted({column.strip() for column in self.columns if column.strip()})))
        object.__setattr__(self, "expression", tuple(sorted(self.expression)))
        self._validate()

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ResourceRef":
        kind = _normalize_kind(str(raw.get("kind", "")))
        expression = cls._expression_from_raw(raw.get("expression", ()))
        columns = raw.get("columns", ())
        if isinstance(columns, str):
            columns = [columns]
        database_name = _resource_name(raw, "database", "database_name")
        expression_name = _resource_name(raw, "expression_name", "ExpressionName")
        if kind == "database":
            database_name = database_name or _resource_name(raw, "name")
        if kind == "lf_tag_expression":
            expression_name = expression_name or _resource_name(raw, "name", "Name")
        return cls(
            kind=kind,
            database_name=database_name,
            table_name=_resource_name(raw, "table", "table_name"),
            columns=tuple(str(column) for column in columns),
            location=_resource_name(raw, "location", "resource_arn", "arn"),
            resource_type=_resource_name(raw, "resource_type"),
            expression=expression,
            expression_name=expression_name,
            catalog_id=_resource_name(raw, "catalog_id", "catalog"),
        )

    @staticmethod
    def _expression_from_raw(raw: Any) -> Tuple[LFTagValue, ...]:
        if raw in (None, "", (), [], {}):
            return ()
        if isinstance(raw, Mapping):
            return tuple(LFTagValue.from_raw(str(key), values) for key, values in raw.items())
        if isinstance(raw, Iterable):
            expression = []
            for item in raw:
                if not isinstance(item, Mapping):
                    raise ValueError("LF-Tag policy expression items must be mappings")
                key = item.get("key") or item.get("tag_key") or item.get("TagKey")
                values = item.get("values") or item.get("tag_values") or item.get("TagValues")
                if not key:
                    raise ValueError("LF-Tag policy expression item is missing a key")
                expression.append(LFTagValue.from_raw(str(key), values))
            return tuple(expression)
        raise ValueError("LF-Tag policy expression must be a mapping or list")

    def _validate(self) -> None:
        if self.kind == "database" and not self.database_name:
            raise ValueError("database resources require database")
        if self.kind == "table" and (not self.database_name or not self.table_name):
            raise ValueError("table resources require database and table")
        if self.kind == "table_with_columns":
            if not self.database_name or not self.table_name:
                raise ValueError("table_with_columns resources require database and table")
            if not self.columns:
                raise ValueError("table_with_columns resources require columns")
        if self.kind == "data_location" and not self.location:
            raise ValueError("data_location resources require location")
        if self.kind == "lf_tag_policy":
            if self.resource_type not in {"DATABASE", "TABLE"}:
                raise ValueError("lf_tag_policy resources require resource_type DATABASE or TABLE")
            if bool(self.expression) == bool(self.expression_name):
                raise ValueError("lf_tag_policy resources require exactly one of expression or expression_name")
        if self.kind == "lf_tag_expression" and not self.expression_name:
            raise ValueError("lf_tag_expression resources require expression_name or name")

    @property
    def identity(self) -> str:
        parts = [self.kind]
        if self.catalog_id:
            parts.append("catalog={}".format(self.catalog_id))
        if self.database_name:
            parts.append("database={}".format(self.database_name))
        if self.table_name:
            parts.append("table={}".format(self.table_name))
        if self.columns:
            parts.append("columns={}".format(",".join(self.columns)))
        if self.location:
            parts.append("location={}".format(self.location))
        if self.resource_type:
            parts.append("resource_type={}".format(self.resource_type))
        if self.expression_name:
            parts.append("expression_name={}".format(self.expression_name))
        if self.expression:
            rendered = ",".join(
                "{}={}".format(item.key, "|".join(item.values)) for item in self.expression
            )
            parts.append("expression={}".format(rendered))
        return ":".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {"kind": self.kind}
        if self.catalog_id:
            data["catalog_id"] = self.catalog_id
        if self.database_name:
            data["database"] = self.database_name
        if self.table_name:
            data["table"] = self.table_name
        if self.columns:
            data["columns"] = list(self.columns)
        if self.location:
            data["location"] = self.location
        if self.resource_type:
            data["resource_type"] = self.resource_type
        if self.expression_name:
            data["expression_name"] = self.expression_name
        if self.expression:
            data["expression"] = {item.key: list(item.values) for item in self.expression}
        return data


@dataclass(frozen=True, order=True)
class LFTagDefinition:
    """Allowed values for a Lake Formation LF-Tag key."""

    key: str
    values: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", self.key.strip())
        object.__setattr__(self, "values", _string_tuple(self.values, field_name="LF-Tag values"))
        if not self.key:
            raise ValueError("LF-Tag key must not be empty")

    @classmethod
    def from_raw(cls, key: str, values: Any) -> "LFTagDefinition":
        return cls(key=str(key), values=_values_from_raw(values, field_name="LF-Tag values"))

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "values": list(self.values)}


@dataclass(frozen=True, order=True)
class LFTagExpressionDefinition:
    """Named LF-Tag expression managed by Lake Formation."""

    name: str
    expression: Tuple[LFTagValue, ...]
    description: Optional[str] = None
    catalog_id: Optional[str] = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "description", _optional_str(self.description))
        object.__setattr__(self, "catalog_id", _optional_str(self.catalog_id))
        object.__setattr__(self, "expression", tuple(sorted(self.expression)))
        if not self.name:
            raise ValueError("LF-Tag expression name must not be empty")
        if not self.expression:
            raise ValueError("LF-Tag expression requires expression")

    @classmethod
    def from_raw(cls, name: str, raw: Any) -> "LFTagExpressionDefinition":
        if isinstance(raw, Mapping):
            expression = ResourceRef._expression_from_raw(raw.get("expression", ()))
            description = _optional_str(raw.get("description"))
            catalog_id = _resource_name(raw, "catalog_id", "catalog")
        else:
            expression = ResourceRef._expression_from_raw(raw)
            description = None
            catalog_id = None
        return cls(name=str(name), expression=expression, description=description, catalog_id=catalog_id)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "LFTagExpressionDefinition":
        return cls.from_raw(str(raw.get("name", "")), raw)

    @property
    def identity(self) -> str:
        parts = ["lf_tag_expression"]
        if self.catalog_id:
            parts.append("catalog={}".format(self.catalog_id))
        parts.append("name={}".format(self.name))
        return ":".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "name": self.name,
            "expression": {item.key: list(item.values) for item in self.expression},
        }
        if self.description is not None:
            data["description"] = self.description
        if self.catalog_id:
            data["catalog_id"] = self.catalog_id
        return data


@dataclass(frozen=True, order=True)
class LFTagKeyMetadata:
    """Authoring metadata for an LF-Tag key.

    This metadata is optional and not read from AWS. It lets lfguard distinguish
    table-wide LF-Tag policy grants from grants that may narrow access to
    matching columns.
    """

    key: str
    assignable_to: Tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", self.key.strip())
        object.__setattr__(
            self,
            "assignable_to",
            _tag_assignment_scope_tuple(self.assignable_to, field_name="LF-Tag assignable_to"),
        )
        if not self.key:
            raise ValueError("LF-Tag key must not be empty")

    @classmethod
    def from_raw(cls, key: str, raw: Any) -> "LFTagKeyMetadata":
        if isinstance(raw, Mapping):
            assignable_to = raw.get("assignable_to", ())
        else:
            assignable_to = raw
        return cls(
            key=str(key),
            assignable_to=_values_from_raw(assignable_to, field_name="LF-Tag assignable_to"),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {"key": self.key, "assignable_to": list(self.assignable_to)}


@dataclass(frozen=True)
class ResourceTagAssignment:
    """Desired or current LF-Tag assignment for a resource."""

    resource: ResourceRef
    tags: Mapping[str, FrozenSet[str]]

    def __post_init__(self) -> None:
        normalized: Dict[str, FrozenSet[str]] = {}
        for key, values in self.tags.items():
            tag_key = str(key).strip()
            if not tag_key:
                raise ValueError("Resource tag keys must not be empty")
            normalized[tag_key] = frozenset(_values_from_raw(values, field_name="Resource tag values"))
        object.__setattr__(self, "tags", normalized)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ResourceTagAssignment":
        resource = ResourceRef.from_dict(_require_mapping(raw.get("resource"), "resource_tags[].resource"))
        tags = _require_mapping(raw.get("tags"), "resource_tags[].tags")
        return cls(resource=resource, tags={str(key): frozenset(_values_from_raw(values, field_name="Resource tag values")) for key, values in tags.items()})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource": self.resource.to_dict(),
            "tags": {key: sorted(values) for key, values in sorted(self.tags.items())},
        }


@dataclass(frozen=True, order=True)
class Grant:
    """Lake Formation grant for a principal and resource."""

    principal: str
    resource: ResourceRef
    permissions: Tuple[str, ...]
    grantable_permissions: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        principal = self.principal.strip()
        if not principal:
            raise ValueError("Grant principal must not be empty")
        object.__setattr__(self, "principal", principal)
        grantable_permissions = tuple(
            sorted({permission.upper().strip() for permission in self.grantable_permissions if permission.strip()})
        )
        permissions = tuple(
            sorted(
                {permission.upper().strip() for permission in self.permissions if permission.strip()}
                | set(grantable_permissions)
            )
        )
        object.__setattr__(self, "permissions", _string_tuple(permissions, field_name="permissions"))
        object.__setattr__(
            self,
            "grantable_permissions",
            grantable_permissions,
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Grant":
        return cls(
            principal=str(raw.get("principal", "")),
            resource=ResourceRef.from_dict(_require_mapping(raw.get("resource"), "grants[].resource")),
            permissions=_values_from_raw(raw.get("permissions", ()), field_name="permissions"),
            grantable_permissions=_values_from_raw(raw.get("grantable_permissions", ()), field_name="grantable_permissions")
            if raw.get("grantable_permissions") not in (None, "")
            else (),
        )

    @property
    def identity(self) -> Tuple[str, ResourceRef]:
        return (self.principal, self.resource)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "principal": self.principal,
            "resource": self.resource.to_dict(),
            "permissions": list(self.permissions),
        }
        if self.grantable_permissions:
            data["grantable_permissions"] = list(self.grantable_permissions)
        return data


@dataclass(frozen=True, order=True)
class ResourcePattern:
    """Pattern used by ownership and ignore rules."""

    kind: Optional[str] = None
    database_name: Optional[str] = None
    table_name: Optional[str] = None
    location: Optional[str] = None
    expression_name: Optional[str] = None

    def __post_init__(self) -> None:
        kind = _optional_str(self.kind)
        if kind is not None:
            kind = _normalize_kind(kind)
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "database_name", _optional_str(self.database_name))
        object.__setattr__(self, "table_name", _optional_str(self.table_name))
        object.__setattr__(self, "location", _optional_str(self.location))
        object.__setattr__(self, "expression_name", _optional_str(self.expression_name))
        if not any((self.kind, self.database_name, self.table_name, self.location, self.expression_name)):
            raise ValueError("Resource ignore/ownership pattern must not be empty")

    @classmethod
    def from_raw(cls, raw: Any) -> "ResourcePattern":
        if isinstance(raw, str):
            return cls(kind=raw)
        raw_mapping = _require_mapping(raw, "resource pattern")
        if len(raw_mapping) == 1:
            key, value = next(iter(raw_mapping.items()))
            key_text = str(key)
            if key_text in {"database", "database_name"}:
                return cls(database_name=str(value))
            if key_text in {"table", "table_name"}:
                return cls(table_name=str(value))
            if key_text in {"data_location", "location"}:
                return cls(location=str(value))
            if key_text in {"lf_tag_expression", "expression_name"}:
                return cls(expression_name=str(value))
        return cls(
            kind=_resource_name(raw_mapping, "kind"),
            database_name=_resource_name(raw_mapping, "database", "database_name"),
            table_name=_resource_name(raw_mapping, "table", "table_name"),
            location=_resource_name(raw_mapping, "location", "resource_arn", "arn"),
            expression_name=_resource_name(raw_mapping, "expression_name", "name"),
        )

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.kind:
            data["kind"] = self.kind
        if self.database_name:
            data["database"] = self.database_name
        if self.table_name:
            data["table"] = self.table_name
        if self.location:
            data["location"] = self.location
        if self.expression_name:
            data["expression_name"] = self.expression_name
        return data


@dataclass(frozen=True)
class OwnershipConfig:
    """Ownership boundary for unmanaged current-state drift."""

    managed_principals: Tuple[str, ...] = field(default_factory=tuple)
    managed_resources: Tuple[ResourcePattern, ...] = field(default_factory=tuple)
    unmanaged_action: str = "warn"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "managed_principals",
            tuple(sorted({str(value).strip() for value in self.managed_principals if str(value).strip()})),
        )
        object.__setattr__(self, "managed_resources", tuple(sorted(self.managed_resources)))
        action = self.unmanaged_action.strip().lower()
        if action == "warning":
            action = "warn"
        if action not in UNMANAGED_ACTIONS:
            raise ValueError("ownership.unmanaged_action must be one of error, warn, or ignore")
        object.__setattr__(self, "unmanaged_action", action)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OwnershipConfig":
        resources = tuple(ResourcePattern.from_raw(item) for item in raw.get("managed_resources", ()))
        principals = _optional_string_tuple(raw.get("managed_principals", ()), "ownership.managed_principals")
        return cls(
            managed_principals=principals,
            managed_resources=resources,
            unmanaged_action=str(raw.get("unmanaged_action", "warn")),
        )

    def is_default(self) -> bool:
        return not self.managed_principals and not self.managed_resources and self.unmanaged_action == "warn"

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.managed_principals:
            data["managed_principals"] = list(self.managed_principals)
        if self.managed_resources:
            data["managed_resources"] = [pattern.to_dict() for pattern in self.managed_resources]
        if self.unmanaged_action != "warn":
            data["unmanaged_action"] = self.unmanaged_action
        return data


@dataclass(frozen=True)
class IgnoreConfig:
    """Explicit audit ignore rules."""

    principals: Tuple[str, ...] = field(default_factory=tuple)
    resources: Tuple[ResourcePattern, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "principals",
            tuple(sorted({str(value).strip() for value in self.principals if str(value).strip()})),
        )
        object.__setattr__(self, "resources", tuple(sorted(self.resources)))

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "IgnoreConfig":
        return cls(
            principals=_optional_string_tuple(raw.get("principals", ()), "ignore.principals"),
            resources=tuple(ResourcePattern.from_raw(item) for item in raw.get("resources", ())),
        )

    def is_default(self) -> bool:
        return not self.principals and not self.resources

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.principals:
            data["principals"] = list(self.principals)
        if self.resources:
            data["resources"] = [pattern.to_dict() for pattern in self.resources]
        return data


@dataclass(frozen=True)
class GuardrailConfig:
    """Optional guardrail behavior configuration embedded in desired state."""

    lint: Mapping[str, str] = field(default_factory=dict)
    ownership: OwnershipConfig = field(default_factory=OwnershipConfig)
    ignore: IgnoreConfig = field(default_factory=IgnoreConfig)

    def __post_init__(self) -> None:
        normalized: Dict[str, str] = {}
        for key, severity in self.lint.items():
            code = str(key).strip().upper()
            value = str(severity).strip().lower()
            if value not in LINT_SEVERITIES:
                raise ValueError("lint.{} must be one of error, warning, or ignore".format(key))
            if code:
                normalized[code] = value
        object.__setattr__(self, "lint", normalized)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "GuardrailConfig":
        lint = _require_mapping(raw.get("lint", {}), "lint") if raw.get("lint") is not None else {}
        ownership = (
            OwnershipConfig.from_dict(_require_mapping(raw["ownership"], "ownership"))
            if raw.get("ownership") is not None
            else OwnershipConfig()
        )
        ignore = (
            IgnoreConfig.from_dict(_require_mapping(raw["ignore"], "ignore"))
            if raw.get("ignore") is not None
            else IgnoreConfig()
        )
        return cls(lint={str(key): str(value) for key, value in lint.items()}, ownership=ownership, ignore=ignore)

    def is_default(self) -> bool:
        return not self.lint and self.ownership.is_default() and self.ignore.is_default()

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {}
        if self.lint:
            data["lint"] = {key.lower(): value for key, value in sorted(self.lint.items())}
        if not self.ownership.is_default():
            data["ownership"] = self.ownership.to_dict()
        if not self.ignore.is_default():
            data["ignore"] = self.ignore.to_dict()
        return data


TState = TypeVar("TState", bound="GuardrailState")


@dataclass(frozen=True)
class GuardrailState:
    """Serializable Lake Formation state used for desired policy and snapshots."""

    lf_tags: Tuple[LFTagDefinition, ...] = field(default_factory=tuple)
    lf_tag_expressions: Tuple[LFTagExpressionDefinition, ...] = field(default_factory=tuple)
    lf_tag_key_metadata: Tuple[LFTagKeyMetadata, ...] = field(default_factory=tuple)
    resource_tags: Tuple[ResourceTagAssignment, ...] = field(default_factory=tuple)
    grants: Tuple[Grant, ...] = field(default_factory=tuple)
    config: GuardrailConfig = field(default_factory=GuardrailConfig)

    @classmethod
    def empty(cls: Type[TState]) -> TState:
        return cls()

    @classmethod
    def from_dict(cls: Type[TState], raw: Mapping[str, Any]) -> TState:
        lf_tags_raw = raw.get("lf_tags", {})
        if isinstance(lf_tags_raw, Mapping):
            lf_tags = tuple(LFTagDefinition.from_raw(str(key), values) for key, values in lf_tags_raw.items())
        elif isinstance(lf_tags_raw, Iterable):
            lf_tags = tuple(
                LFTagDefinition.from_raw(
                    str(_require_mapping(item, "lf_tags[]").get("key", "")),
                    _require_mapping(item, "lf_tags[]").get("values", ()),
                )
                for item in lf_tags_raw
            )
        else:
            raise ValueError("lf_tags must be a mapping or list")

        expressions_raw = raw.get("lf_tag_expressions", {})
        if isinstance(expressions_raw, Mapping):
            lf_tag_expressions = tuple(
                LFTagExpressionDefinition.from_raw(str(name), value)
                for name, value in expressions_raw.items()
            )
        elif isinstance(expressions_raw, Iterable):
            lf_tag_expressions = tuple(
                LFTagExpressionDefinition.from_dict(_require_mapping(item, "lf_tag_expressions[]"))
                for item in expressions_raw
            )
        else:
            raise ValueError("lf_tag_expressions must be a mapping or list")

        metadata_raw = raw.get("lf_tag_key_metadata", {})
        if isinstance(metadata_raw, Mapping):
            lf_tag_key_metadata = tuple(
                LFTagKeyMetadata.from_raw(str(key), value)
                for key, value in metadata_raw.items()
            )
        elif isinstance(metadata_raw, Iterable):
            metadata_items = []
            for item in metadata_raw:
                item_mapping = _require_mapping(item, "lf_tag_key_metadata[]")
                metadata_items.append(
                    LFTagKeyMetadata.from_raw(
                        str(item_mapping.get("key", "")),
                        item_mapping,
                    )
                )
            lf_tag_key_metadata = tuple(metadata_items)
        else:
            raise ValueError("lf_tag_key_metadata must be a mapping or list")

        resource_tags = tuple(
            ResourceTagAssignment.from_dict(_require_mapping(item, "resource_tags[]"))
            for item in raw.get("resource_tags", ())
        )
        grants = tuple(Grant.from_dict(_require_mapping(item, "grants[]")) for item in raw.get("grants", ()))
        config = GuardrailConfig.from_dict(raw)
        return cls(
            lf_tags=tuple(sorted(lf_tags)),
            lf_tag_expressions=tuple(sorted(lf_tag_expressions)),
            lf_tag_key_metadata=tuple(sorted(lf_tag_key_metadata)),
            resource_tags=resource_tags,
            grants=tuple(sorted(grants)),
            config=config,
        )

    @classmethod
    def from_file(cls: Type[TState], path: str) -> TState:
        from .io import load_state

        return load_state(Path(path), cls)

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "lf_tags": {tag.key: list(tag.values) for tag in self.lf_tags},
        }
        if self.lf_tag_expressions:
            expression_names = [expression.name for expression in self.lf_tag_expressions]
            if len(expression_names) != len(set(expression_names)):
                data["lf_tag_expressions"] = [
                    expression.to_dict() for expression in self.lf_tag_expressions
                ]
            else:
                data["lf_tag_expressions"] = {
                    expression.name: {
                        key: value
                        for key, value in expression.to_dict().items()
                        if key != "name"
                    }
                    for expression in self.lf_tag_expressions
                }
        if self.lf_tag_key_metadata:
            data["lf_tag_key_metadata"] = {
                metadata.key: {"assignable_to": list(metadata.assignable_to)}
                for metadata in self.lf_tag_key_metadata
            }
        data["resource_tags"] = [assignment.to_dict() for assignment in self.resource_tags]
        data["grants"] = [grant.to_dict() for grant in self.grants]
        if not self.config.is_default():
            data.update(self.config.to_dict())
        return data


class DesiredState(GuardrailState):
    """Desired Lake Formation policy state."""


class CurrentState(GuardrailState):
    """Observed Lake Formation policy state."""


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("{} must be a mapping".format(field_name))
    return value


def _optional_string_tuple(raw: Any, field_name: str) -> Tuple[str, ...]:
    if raw in (None, "", (), []):
        return ()
    return _values_from_raw(raw, field_name=field_name)
