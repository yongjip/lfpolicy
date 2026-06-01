"""Conservative diff engine for Lake Formation guardrails."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from .models import (
    CurrentState,
    DesiredState,
    LFTagExpressionDefinition,
    ResourceRef,
)
from .permissions import BROAD_PERMISSION_COVERAGE, missing_permissions
from .state_index import (
    grant_index,
    grant_target,
    lf_tag_expression_index,
    lf_tag_index,
    lf_tag_sort_key,
    resource_tag_index,
)


PLAN_SCHEMA_VERSION = "lfguard.plan.v1"
_UNSET = object()

_ACTION_AWS_API = {
    "lf_tag.create": "create_lf_tag",
    "lf_tag.add_values": "update_lf_tag",
    "lf_tag.remove_values": "update_lf_tag",
    "lf_tag_expression.create": "create_lf_tag_expression",
    "lf_tag_expression.update": "update_lf_tag_expression",
    "lf_tag_expression.delete": "delete_lf_tag_expression",
    "resource_tag.add_values": "add_lf_tags_to_resource",
    "resource_tag.remove_values": "remove_lf_tags_from_resource",
    "grant.add_permissions": "grant_permissions",
    "grant.revoke_permissions": "revoke_permissions",
}

_ACTION_REQUIRED_FLAG = {
    "lf_tag.remove_values": "--allow-lf-tag-value-removals",
    "lf_tag_expression.update": "--allow-lf-tag-expression-updates",
    "lf_tag_expression.delete": "--allow-lf-tag-expression-deletes",
    "resource_tag.remove_values": "--allow-resource-tag-removals",
    "grant.revoke_permissions": "--allow-permission-revokes",
}


@dataclass(frozen=True)
class PlanOptions:
    """Controls whether destructive drift remediation is included in a plan."""

    allow_lf_tag_value_removals: bool = False
    allow_lf_tag_expression_updates: bool = False
    allow_lf_tag_expression_deletes: bool = False
    allow_resource_tag_removals: bool = False
    allow_permission_revokes: bool = False


@dataclass(frozen=True)
class Change:
    """Single executable or reviewable Lake Formation change."""

    action: str
    target: str
    reason: str
    payload: Mapping[str, Any]
    destructive: bool = False
    id: Optional[str] = None
    before: Any = _UNSET
    after: Any = _UNSET

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Change":
        payload = raw.get("payload", {})
        if not isinstance(payload, Mapping):
            raise ValueError("plan changes[].payload must be a mapping")
        return cls(
            action=str(raw.get("action", "")).strip(),
            target=str(raw.get("target", "")).strip(),
            reason=str(raw.get("reason", "")).strip(),
            payload=dict(payload),
            destructive=bool(raw.get("destructive", False)),
            id=str(raw["id"]).strip() if raw.get("id") else None,
            before=raw["before"] if "before" in raw else _UNSET,
            after=raw["after"] if "after" in raw else _UNSET,
        )

    @property
    def risk(self) -> str:
        return "destructive" if self.destructive else "safe"

    @property
    def principal(self) -> Optional[str]:
        principal = self.payload.get("principal")
        return str(principal) if principal not in (None, "") else None

    @property
    def resource(self) -> Any:
        return self.payload.get("resource")

    @property
    def requires_flag(self) -> Optional[str]:
        return _ACTION_REQUIRED_FLAG.get(self.action)

    @property
    def aws_api(self) -> Optional[str]:
        return _ACTION_AWS_API.get(self.action)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action,
            "target": self.target,
            "reason": self.reason,
            "destructive": self.destructive,
            "risk": self.risk,
            "principal": self.principal,
            "resource": _json_ready(self.resource),
            "before": _json_ready(None if self.before is _UNSET else self.before),
            "after": _json_ready(None if self.after is _UNSET else self.after),
            "requires_flag": self.requires_flag,
            "aws_api": self.aws_api,
            "payload": _json_ready(self.payload),
        }


@dataclass(frozen=True)
class Plan:
    """Ordered collection of changes required to converge current to desired state."""

    changes: Tuple[Change, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "changes",
            tuple(_change_with_id(change, index) for index, change in enumerate(self.changes, start=1)),
        )

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "Plan":
        changes = raw.get("changes")
        if not isinstance(changes, Iterable) or isinstance(changes, (str, bytes, Mapping)):
            raise ValueError("plan JSON must contain top-level changes list")
        return cls(tuple(Change.from_dict(_require_mapping(item, "changes[]")) for item in changes))

    @property
    def destructive_changes(self) -> Tuple[Change, ...]:
        return tuple(change for change in self.changes if change.destructive)

    @property
    def safe_changes(self) -> Tuple[Change, ...]:
        return tuple(change for change in self.changes if not change.destructive)

    def executable_changes(self, *, allow_destructive: bool = False) -> Tuple[Change, ...]:
        if allow_destructive:
            return self.changes
        return self.safe_changes

    def summary(self) -> Dict[str, int]:
        return {
            "total": len(self.changes),
            "safe": len(self.safe_changes),
            "destructive": len(self.destructive_changes),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": PLAN_SCHEMA_VERSION,
            "summary": self.summary(),
            "changes": [change.to_dict() for change in self.changes],
        }


def plan(desired: DesiredState, current: CurrentState, options: PlanOptions = PlanOptions()) -> Plan:
    """Create a conservative plan to move current state toward desired state."""

    changes: List[Change] = []
    changes.extend(_plan_lf_tags(desired, current, options))
    changes.extend(_plan_lf_tag_expressions(desired, current, options))
    changes.extend(_plan_resource_tags(desired, current, options))
    changes.extend(_plan_grants(desired, current, options))
    return Plan(tuple(changes))


def _plan_lf_tags(desired: DesiredState, current: CurrentState, options: PlanOptions) -> Iterable[Change]:
    desired_tags = lf_tag_index(desired.lf_tags)
    current_tags = lf_tag_index(current.lf_tags)
    for key, desired_tag in sorted(desired_tags.items(), key=lambda item: lf_tag_sort_key(item[0])):
        current_tag = current_tags.get(key)
        if current_tag is None:
            yield Change(
                action="lf_tag.create",
                target=desired_tag.identity,
                reason="LF-Tag is missing",
                payload=_lf_tag_payload(desired_tag.key, desired_tag.values, desired_tag.catalog_id),
                before=None,
                after=_lf_tag_payload(desired_tag.key, desired_tag.values, desired_tag.catalog_id),
            )
            continue

        desired_values = set(desired_tag.values)
        current_values = set(current_tag.values)
        missing_values = sorted(desired_values - current_values)
        if missing_values:
            yield Change(
                action="lf_tag.add_values",
                target=desired_tag.identity,
                reason="LF-Tag is missing allowed values",
                payload=_lf_tag_payload(desired_tag.key, missing_values, desired_tag.catalog_id),
                before=_lf_tag_payload(desired_tag.key, sorted(current_values), desired_tag.catalog_id),
                after=_lf_tag_payload(desired_tag.key, sorted(current_values | set(missing_values)), desired_tag.catalog_id),
            )
        extra_values = sorted(current_values - desired_values)
        if extra_values and options.allow_lf_tag_value_removals:
            yield Change(
                action="lf_tag.remove_values",
                target=desired_tag.identity,
                reason="LF-Tag has values not present in desired state",
                payload=_lf_tag_payload(desired_tag.key, extra_values, desired_tag.catalog_id),
                destructive=True,
                before=_lf_tag_payload(desired_tag.key, sorted(current_values), desired_tag.catalog_id),
                after=_lf_tag_payload(desired_tag.key, sorted(current_values - set(extra_values)), desired_tag.catalog_id),
            )


def _plan_lf_tag_expressions(desired: DesiredState, current: CurrentState, options: PlanOptions) -> Iterable[Change]:
    current_expressions = lf_tag_expression_index(current.lf_tag_expressions)
    desired_expressions = lf_tag_expression_index(desired.lf_tag_expressions)
    for name, desired_expression in desired_expressions.items():
        current_expression = current_expressions.get(name)
        if current_expression is None:
            yield Change(
                action="lf_tag_expression.create",
                target=desired_expression.identity,
                reason="LF-Tag expression is missing",
                payload=_lf_tag_expression_payload(desired_expression),
                before=None,
                after=desired_expression.to_dict(),
            )
            continue
        if (
            current_expression.expression != desired_expression.expression
            or current_expression.description != desired_expression.description
        ) and options.allow_lf_tag_expression_updates:
            yield Change(
                action="lf_tag_expression.update",
                target=desired_expression.identity,
                reason="LF-Tag expression body differs from desired state",
                payload=_lf_tag_expression_payload(desired_expression),
                destructive=True,
                before=current_expression.to_dict(),
                after=desired_expression.to_dict(),
            )
    if options.allow_lf_tag_expression_deletes:
        for name, current_expression in current_expressions.items():
            if name in desired_expressions:
                continue
            yield Change(
                action="lf_tag_expression.delete",
                target=current_expression.identity,
                reason="LF-Tag expression is not present in desired state",
                payload={"name": current_expression.name, "catalog_id": current_expression.catalog_id},
                destructive=True,
                before=current_expression.to_dict(),
                after=None,
            )


def _plan_resource_tags(desired: DesiredState, current: CurrentState, options: PlanOptions) -> Iterable[Change]:
    current_by_resource = resource_tag_index(current.resource_tags)
    desired_by_resource = resource_tag_index(desired.resource_tags)
    for resource, desired_tags in sorted(
        desired_by_resource.items(),
        key=lambda item: item[0].identity,
    ):
        current_tags = current_by_resource.get(resource, {})
        tags_to_add: Dict[str, List[str]] = {}
        tags_to_remove: Dict[str, List[str]] = {}
        for key, desired_values in sorted(desired_tags.items()):
            current_values = current_tags.get(key, frozenset())
            missing_values = sorted(desired_values - current_values)
            if missing_values:
                tags_to_add[key] = missing_values
            extra_values = sorted(current_values - desired_values)
            if extra_values and options.allow_resource_tag_removals:
                tags_to_remove[key] = extra_values
        if options.allow_resource_tag_removals:
            for key, current_values in sorted(current_tags.items()):
                if key in desired_tags:
                    continue
                values_to_remove = sorted(current_values)
                if values_to_remove:
                    tags_to_remove[key] = values_to_remove

        if tags_to_add:
            yield Change(
                action="resource_tag.add_values",
                target=resource.identity,
                reason="Resource is missing desired LF-Tag assignments",
                payload={"resource": resource.to_dict(), "tags": tags_to_add},
                before={"resource": resource.to_dict(), "tags": _tag_values_dict(current_tags)},
                after={"resource": resource.to_dict(), "tags": _add_tag_values(current_tags, tags_to_add)},
            )
        if tags_to_remove:
            yield Change(
                action="resource_tag.remove_values",
                target=resource.identity,
                reason="Resource has LF-Tag assignments not present in desired state",
                payload={"resource": resource.to_dict(), "tags": tags_to_remove},
                destructive=True,
                before={"resource": resource.to_dict(), "tags": _tag_values_dict(current_tags)},
                after={"resource": resource.to_dict(), "tags": _remove_tag_values(current_tags, tags_to_remove)},
            )
    if options.allow_resource_tag_removals:
        for resource, current_tags in sorted(
            current_by_resource.items(),
            key=lambda item: item[0].identity,
        ):
            if resource in desired_by_resource:
                continue
            tags_to_remove = _tag_values_dict(current_tags)
            if not tags_to_remove:
                continue
            yield Change(
                action="resource_tag.remove_values",
                target=resource.identity,
                reason="Resource has LF-Tag assignments not present in desired state",
                payload={"resource": resource.to_dict(), "tags": tags_to_remove},
                destructive=True,
                before={"resource": resource.to_dict(), "tags": tags_to_remove},
                after={"resource": resource.to_dict(), "tags": {}},
            )


def _plan_grants(desired: DesiredState, current: CurrentState, options: PlanOptions) -> Iterable[Change]:
    desired_grants = grant_index(desired.grants)
    current_grants = grant_index(current.grants)

    for identity, desired_grant in desired_grants.items():
        current_grant = current_grants.get(identity)
        current_permissions = set(current_grant.permissions) if current_grant else set()
        current_grantables = set(current_grant.grantable_permissions) if current_grant else set()
        desired_permissions = set(desired_grant.permissions)
        desired_grantables = set(desired_grant.grantable_permissions)

        missing_permission_names = missing_permissions(desired_permissions, current_permissions)
        missing_grantables = missing_permissions(desired_grantables, current_grantables)
        if options.allow_permission_revokes:
            if current_permissions & BROAD_PERMISSION_COVERAGE and not desired_permissions & BROAD_PERMISSION_COVERAGE:
                missing_permission_names.update(desired_permissions - current_permissions)
            if current_grantables & BROAD_PERMISSION_COVERAGE and not desired_grantables & BROAD_PERMISSION_COVERAGE:
                missing_grantables.update(desired_grantables - current_grantables)
        missing_permission_names = sorted(missing_permission_names)
        missing_grantables = sorted(missing_grantables)
        if missing_permission_names or missing_grantables:
            permissions_to_grant = sorted(set(missing_permission_names) | set(missing_grantables))
            yield Change(
                action="grant.add_permissions",
                target=grant_target(desired_grant),
                reason="Principal is missing desired Lake Formation permissions",
                payload={
                    "principal": desired_grant.principal,
                    "resource": desired_grant.resource.to_dict(),
                    "permissions": permissions_to_grant,
                    "grantable_permissions": missing_grantables,
                },
                before=_grant_snapshot(desired_grant.principal, desired_grant.resource, current_permissions, current_grantables)
                if current_grant
                else None,
                after=_grant_snapshot(
                    desired_grant.principal,
                    desired_grant.resource,
                    current_permissions | set(permissions_to_grant),
                    current_grantables | set(missing_grantables),
                ),
            )

        extra_permissions = sorted(current_permissions - desired_permissions)
        extra_grantables = sorted(current_grantables - desired_grantables)
        if (extra_permissions or extra_grantables) and options.allow_permission_revokes:
            yield Change(
                action="grant.revoke_permissions",
                target=grant_target(desired_grant),
                reason="Principal has Lake Formation permissions not present in desired state",
                payload={
                    "principal": desired_grant.principal,
                    "resource": desired_grant.resource.to_dict(),
                    "permissions": extra_permissions,
                    "grantable_permissions": extra_grantables,
                },
                destructive=True,
                before=_grant_snapshot(desired_grant.principal, desired_grant.resource, current_permissions, current_grantables),
                after=_grant_snapshot(
                    desired_grant.principal,
                    desired_grant.resource,
                    current_permissions - set(extra_permissions),
                    current_grantables - set(extra_grantables),
                ),
            )

    if options.allow_permission_revokes:
        for identity, current_grant in current_grants.items():
            if identity in desired_grants:
                continue
            yield Change(
                action="grant.revoke_permissions",
                target=grant_target(current_grant),
                reason="Principal grant is not present in desired state",
                payload={
                    "principal": current_grant.principal,
                    "resource": current_grant.resource.to_dict(),
                    "permissions": list(current_grant.permissions),
                    "grantable_permissions": list(current_grant.grantable_permissions),
                },
                destructive=True,
                before=current_grant.to_dict(),
                after=None,
            )


def _lf_tag_expression_payload(expression: LFTagExpressionDefinition) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": expression.name,
        "expression": [item.to_dict() for item in expression.expression],
    }
    if expression.description is not None:
        payload["description"] = expression.description
    if expression.catalog_id:
        payload["catalog_id"] = expression.catalog_id
    return payload


def _lf_tag_payload(key: str, values: Iterable[str], catalog_id: Optional[str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"tag_key": key, "tag_values": list(values)}
    if catalog_id:
        payload["catalog_id"] = catalog_id
    return payload


def _change_id(index: int) -> str:
    return "change_{:03d}".format(index)


def _change_with_id(change: Change, index: int) -> Change:
    if change.id:
        return change
    return Change(
        action=change.action,
        target=change.target,
        reason=change.reason,
        payload=change.payload,
        destructive=change.destructive,
        id=_change_id(index),
        before=change.before,
        after=change.after,
    )


def _require_mapping(value: Any, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("{} must be a mapping".format(field_name))
    return value


def _tag_values_dict(tags: Mapping[str, Iterable[str]]) -> Dict[str, List[str]]:
    return {key: sorted(values) for key, values in sorted(tags.items()) if values}


def _add_tag_values(current: Mapping[str, Iterable[str]], additions: Mapping[str, Iterable[str]]) -> Dict[str, List[str]]:
    merged = {key: set(values) for key, values in current.items()}
    for key, values in additions.items():
        merged.setdefault(key, set()).update(values)
    return _tag_values_dict(merged)


def _remove_tag_values(current: Mapping[str, Iterable[str]], removals: Mapping[str, Iterable[str]]) -> Dict[str, List[str]]:
    merged = {key: set(values) for key, values in current.items()}
    for key, values in removals.items():
        if key not in merged:
            continue
        merged[key].difference_update(values)
    return _tag_values_dict(merged)


def _grant_snapshot(
    principal: str,
    resource: ResourceRef,
    permissions: Iterable[str],
    grantable_permissions: Iterable[str],
) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "principal": principal,
        "resource": resource.to_dict(),
        "permissions": sorted(permissions),
    }
    grantables = sorted(grantable_permissions)
    if grantables:
        data["grantable_permissions"] = grantables
    return data


def _json_ready(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _json_ready(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_ready(item) for item in value]
    return value
