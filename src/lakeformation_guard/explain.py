"""Explain effective Lake Formation access from current and desired state."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from .models import CurrentState, DesiredState, Grant, LFTagValue, ResourceRef
from .state_index import (
    LFTagExpressionKey,
    lf_tag_expression_index,
    resolve_lf_tag_expression_key,
)


EXPLAIN_SCHEMA_VERSION = "lfguard.explain.v1"


@dataclass(frozen=True)
class ExplainFinding:
    """One explanation item for a current or desired grant."""

    source: str
    status: str
    message: str
    permissions: Tuple[str, ...] = field(default_factory=tuple)
    grantable_permissions: Tuple[str, ...] = field(default_factory=tuple)
    resource: Optional[ResourceRef] = None
    details: Mapping[str, Any] = field(default_factory=dict)
    id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", self.source.strip())
        object.__setattr__(self, "status", self.status.strip())
        object.__setattr__(self, "message", self.message.strip())
        object.__setattr__(
            self,
            "permissions",
            tuple(sorted({permission.upper().strip() for permission in self.permissions if permission.strip()})),
        )
        object.__setattr__(
            self,
            "grantable_permissions",
            tuple(
                sorted(
                    {
                        permission.upper().strip()
                        for permission in self.grantable_permissions
                        if permission.strip()
                    }
                )
            ),
        )
        object.__setattr__(self, "details", dict(self.details))

    def to_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "id": self.id,
            "source": self.source,
            "status": self.status,
            "message": self.message,
            "permissions": list(self.permissions),
            "grantable_permissions": list(self.grantable_permissions),
            "details": _json_ready(self.details),
        }
        if self.resource is not None:
            data["resource"] = self.resource.to_dict()
        return data

    def with_id(self, finding_id: str) -> "ExplainFinding":
        return ExplainFinding(
            source=self.source,
            status=self.status,
            message=self.message,
            permissions=self.permissions,
            grantable_permissions=self.grantable_permissions,
            resource=self.resource,
            details=self.details,
            id=finding_id,
        )


@dataclass(frozen=True)
class ExplainReport:
    """Structured explanation for a principal and target resource."""

    principal: str
    resource: ResourceRef
    requested_permissions: Tuple[str, ...]
    effective_lf_tags: Mapping[str, Tuple[str, ...]]
    findings: Tuple[ExplainFinding, ...]
    notes: Tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> Dict[str, int]:
        return {
            "matched": sum(1 for finding in self.findings if finding.status == "matched"),
            "not_matched": sum(1 for finding in self.findings if finding.status == "not_matched"),
            "missing": sum(1 for finding in self.findings if finding.status == "missing"),
            "context": sum(1 for finding in self.findings if finding.status == "context"),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": EXPLAIN_SCHEMA_VERSION,
            "principal": self.principal,
            "resource": self.resource.to_dict(),
            "requested_permissions": list(self.requested_permissions),
            "effective_lf_tags": {
                key: list(values) for key, values in sorted(self.effective_lf_tags.items())
            },
            "summary": self.summary(),
            "findings": [finding.to_dict() for finding in self.findings],
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class _GrantRelevance:
    status: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


def explain(
    desired: DesiredState,
    current: CurrentState,
    *,
    principal: str,
    resource: ResourceRef,
    permissions: Iterable[str] = (),
) -> ExplainReport:
    """Explain current access and desired-state gaps for one principal/resource."""

    principal = principal.strip()
    if not principal:
        raise ValueError("principal must not be empty")
    requested_permissions = _normalize_permissions(permissions)
    effective_lf_tags = _effective_lf_tags(current, resource)
    expression_index = _expression_index(current)
    desired_expression_index = _expression_index(desired)
    findings: List[ExplainFinding] = []
    notes: List[str] = []

    for grant in current.grants:
        if grant.principal != principal:
            continue
        relevance = _grant_relevance(grant.resource, resource, effective_lf_tags, expression_index)
        if relevance is None:
            continue
        findings.append(_finding_for_current_grant(grant, relevance, requested_permissions))

    for grant in desired.grants:
        if grant.principal != principal:
            continue
        if requested_permissions and not set(requested_permissions).issubset(set(grant.permissions)):
            continue
        relevance = _grant_relevance(
            grant.resource,
            resource,
            effective_lf_tags,
            desired_expression_index,
        )
        if relevance is None or relevance.status != "matched":
            continue
        if not _current_covers_desired_grant(grant, current.grants):
            findings.append(
                ExplainFinding(
                    source="desired_grant",
                    status="missing",
                    message="Desired grant is not present in current state.",
                    permissions=grant.permissions,
                    grantable_permissions=grant.grantable_permissions,
                    resource=grant.resource,
                    details={"desired_resource": grant.resource.to_dict(), **dict(relevance.details)},
                )
            )

    if resource.kind == "table_with_columns":
        notes.append(
            "Column LF-Tags are evaluated from matching column assignments in the current snapshot."
        )
    if not findings:
        notes.append("No current or desired grants matched this principal/resource scope.")

    return ExplainReport(
        principal=principal,
        resource=resource,
        requested_permissions=requested_permissions,
        effective_lf_tags=effective_lf_tags,
        findings=_assign_finding_ids(findings),
        notes=tuple(notes),
    )


def _assign_finding_ids(findings: Iterable[ExplainFinding]) -> Tuple[ExplainFinding, ...]:
    return tuple(
        finding.with_id("finding_{:03d}".format(index))
        for index, finding in enumerate(findings, start=1)
    )


def _finding_for_current_grant(
    grant: Grant,
    relevance: _GrantRelevance,
    requested_permissions: Tuple[str, ...],
) -> ExplainFinding:
    status = relevance.status
    message = relevance.message
    details = dict(relevance.details)
    if status == "matched" and requested_permissions:
        missing_permissions = sorted(set(requested_permissions) - set(grant.permissions))
        if missing_permissions:
            status = "not_matched"
            message = "{} Missing requested permission(s): {}.".format(
                message,
                ", ".join(missing_permissions),
            )
            details["missing_permissions"] = missing_permissions
    details["requested_permissions"] = list(requested_permissions)
    return ExplainFinding(
        source=_grant_source(grant.resource),
        status=status,
        message=message,
        permissions=grant.permissions,
        grantable_permissions=grant.grantable_permissions,
        resource=grant.resource,
        details=details,
    )


def _grant_relevance(
    grant_resource: ResourceRef,
    target: ResourceRef,
    effective_lf_tags: Mapping[str, Tuple[str, ...]],
    expression_index: Mapping[LFTagExpressionKey, Tuple[LFTagValue, ...]],
) -> Optional[_GrantRelevance]:
    if grant_resource.kind == "lf_tag_policy":
        return _lf_tag_policy_relevance(grant_resource, target, effective_lf_tags, expression_index)
    return _direct_resource_relevance(grant_resource, target)


def _direct_resource_relevance(grant_resource: ResourceRef, target: ResourceRef) -> Optional[_GrantRelevance]:
    if grant_resource == target:
        return _GrantRelevance("matched", "Direct grant resource exactly matches the target.")
    if grant_resource.kind == "catalog":
        return _GrantRelevance("context", "Catalog-level grant is present for this principal.")
    if grant_resource.kind == "database" and target.kind in {"database", "table", "table_with_columns"}:
        if _same_database(grant_resource, target):
            return _GrantRelevance("matched", "Database-level grant is on the target database.")
    if grant_resource.kind == "table" and target.kind in {"table", "table_with_columns"}:
        if _same_table(grant_resource, target):
            return _GrantRelevance("matched", "Table-level grant covers the target table.")
    if grant_resource.kind == "table_with_columns" and target.kind == "table_with_columns":
        if _same_table(grant_resource, target):
            granted = set(grant_resource.columns)
            requested = set(target.columns)
            missing = sorted(requested - granted)
            if not missing:
                return _GrantRelevance(
                    "matched",
                    "Column-level grant covers all requested columns.",
                    {"covered_columns": sorted(requested)},
                )
            if granted & requested:
                return _GrantRelevance(
                    "not_matched",
                    "Column-level grant covers only some requested columns.",
                    {"covered_columns": sorted(granted & requested), "missing_columns": missing},
                )
    if grant_resource.kind == "data_location":
        if target.kind == "data_location" and grant_resource.location == target.location:
            return _GrantRelevance("matched", "Data-location grant resource exactly matches the target.")
        return _GrantRelevance(
            "context",
            "Data-location grant is present, but table storage locations are not modeled in lfguard state.",
        )
    return None


def _lf_tag_policy_relevance(
    grant_resource: ResourceRef,
    target: ResourceRef,
    effective_lf_tags: Mapping[str, Tuple[str, ...]],
    expression_index: Mapping[LFTagExpressionKey, Tuple[LFTagValue, ...]],
) -> Optional[_GrantRelevance]:
    target_type = _target_lf_tag_policy_type(target)
    if target_type is None or grant_resource.resource_type != target_type:
        return None
    expression = grant_resource.expression
    details: Dict[str, Any] = {"resource_type": grant_resource.resource_type}
    if grant_resource.expression_name:
        details["expression_name"] = grant_resource.expression_name
        expression = _find_lf_tag_expression(
            expression_index,
            grant_resource.catalog_id,
            grant_resource.expression_name,
        )
        if not expression:
            return _GrantRelevance(
                "not_matched",
                "Named LF-Tag expression definition is missing from current state.",
                details,
            )
    details["expression"] = _expression_to_dict(expression)
    details["effective_lf_tags"] = {
        key: list(values) for key, values in sorted(effective_lf_tags.items())
    }
    match = _match_lf_tag_expression(expression, effective_lf_tags)
    details.update(match)
    if match["matched"]:
        if grant_resource.expression_name:
            message = "Named LF-Tag expression '{}' matches the target's effective LF-Tags.".format(
                grant_resource.expression_name
            )
        else:
            message = "Inline LF-Tag policy expression matches the target's effective LF-Tags."
        return _GrantRelevance("matched", message, details)
    if grant_resource.expression_name:
        message = "Named LF-Tag expression '{}' does not match the target's effective LF-Tags.".format(
            grant_resource.expression_name
        )
    else:
        message = "Inline LF-Tag policy expression does not match the target's effective LF-Tags."
    return _GrantRelevance("not_matched", message, details)


def _match_lf_tag_expression(
    expression: Iterable[LFTagValue],
    effective_lf_tags: Mapping[str, Tuple[str, ...]],
) -> Dict[str, Any]:
    missing_keys = []
    mismatched_values = []
    for item in expression:
        actual_values = set(effective_lf_tags.get(item.key, ()))
        if not actual_values:
            missing_keys.append({"key": item.key, "expected": list(item.values)})
            continue
        if "*" not in item.values and not (actual_values & set(item.values)):
            mismatched_values.append(
                {
                    "key": item.key,
                    "expected": list(item.values),
                    "actual": sorted(actual_values),
                }
            )
    return {
        "matched": not missing_keys and not mismatched_values,
        "missing_keys": missing_keys,
        "mismatched_values": mismatched_values,
    }


def _effective_lf_tags(current: CurrentState, target: ResourceRef) -> Dict[str, Tuple[str, ...]]:
    tags: Dict[str, Tuple[str, ...]] = {}
    for scope in ("database", "table", "column"):
        for assignment in current.resource_tags:
            if _tag_assignment_applies(assignment.resource, target, scope):
                for key, values in assignment.tags.items():
                    if scope == "column" and key in tags:
                        tags[key] = tuple(sorted(set(tags[key]) | set(values)))
                    else:
                        tags[key] = tuple(sorted(values))
    return tags


def _tag_assignment_applies(assignment_resource: ResourceRef, target: ResourceRef, scope: str) -> bool:
    if scope == "database":
        return assignment_resource.kind == "database" and _same_database(assignment_resource, target)
    if scope == "table":
        return assignment_resource.kind == "table" and target.kind in {"table", "table_with_columns"} and _same_table(
            assignment_resource,
            target,
        )
    if scope == "column":
        if assignment_resource.kind != "table_with_columns" or target.kind != "table_with_columns":
            return False
        return _same_table(assignment_resource, target) and bool(set(assignment_resource.columns) & set(target.columns))
    return False


def _current_covers_desired_grant(desired_grant: Grant, current_grants: Iterable[Grant]) -> bool:
    desired_permissions = set(desired_grant.permissions)
    desired_grantables = set(desired_grant.grantable_permissions)
    for current_grant in current_grants:
        if current_grant.principal != desired_grant.principal:
            continue
        if current_grant.resource != desired_grant.resource:
            continue
        if desired_permissions.issubset(set(current_grant.permissions)) and desired_grantables.issubset(
            set(current_grant.grantable_permissions)
        ):
            return True
    return False


def _grant_source(resource: ResourceRef) -> str:
    if resource.kind == "lf_tag_policy" and resource.expression_name:
        return "named_lf_tag_policy"
    if resource.kind == "lf_tag_policy":
        return "lf_tag_policy"
    if resource.kind == "data_location":
        return "data_location_grant"
    return "direct_grant"


def _target_lf_tag_policy_type(target: ResourceRef) -> Optional[str]:
    if target.kind == "database":
        return "DATABASE"
    if target.kind in {"table", "table_with_columns"}:
        return "TABLE"
    return None


def _same_database(left: ResourceRef, right: ResourceRef) -> bool:
    return (
        left.database_name == right.database_name
        and bool(left.database_name)
        and _catalog_compatible(left.catalog_id, right.catalog_id)
    )


def _same_table(left: ResourceRef, right: ResourceRef) -> bool:
    return (
        left.database_name == right.database_name
        and left.table_name == right.table_name
        and bool(left.database_name)
        and bool(left.table_name)
        and _catalog_compatible(left.catalog_id, right.catalog_id)
    )


def _catalog_compatible(left: Optional[str], right: Optional[str]) -> bool:
    return not left or not right or left == right


def _expression_index(state: Union[DesiredState, CurrentState]) -> Dict[LFTagExpressionKey, Tuple[LFTagValue, ...]]:
    return {
        key: expression.expression
        for key, expression in lf_tag_expression_index(state.lf_tag_expressions).items()
    }


def _find_lf_tag_expression(
    expression_index: Mapping[LFTagExpressionKey, Tuple[LFTagValue, ...]],
    catalog_id: Optional[str],
    name: str,
) -> Tuple[LFTagValue, ...]:
    key = resolve_lf_tag_expression_key(expression_index, catalog_id, name)
    if key is None:
        return ()
    return expression_index.get(key, ())


def _normalize_permissions(permissions: Iterable[str]) -> Tuple[str, ...]:
    return tuple(sorted({permission.upper().strip() for permission in permissions if permission.strip()}))


def _expression_to_dict(expression: Iterable[LFTagValue]) -> Dict[str, Any]:
    return {item.key: list(item.values) for item in expression}


def _json_ready(value: Any) -> Any:
    if isinstance(value, ResourceRef):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    if isinstance(value, set):
        return sorted(_json_ready(item) for item in value)
    return value
