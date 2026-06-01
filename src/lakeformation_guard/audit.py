"""Audit findings for desired and current Lake Formation state."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Tuple

from .config import unmanaged_severity
from .models import CurrentState, DesiredState, Grant, ResourceRef
from .planner import _grant_index, _grant_target, _lf_tag_expression_index, _lf_tag_index, _resource_tag_index


@dataclass(frozen=True)
class AuditFinding:
    """A drift or policy finding detected during guardrail audit."""

    code: str
    severity: str
    target: str
    message: str
    details: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "target": self.target,
            "message": self.message,
            "details": dict(self.details),
        }


def audit(desired: DesiredState, current: CurrentState) -> Tuple[AuditFinding, ...]:
    """Return drift findings without making any changes."""

    findings: List[AuditFinding] = []
    findings.extend(_audit_lf_tags(desired, current))
    findings.extend(_audit_lf_tag_expressions(desired, current))
    findings.extend(_audit_resource_tags(desired, current))
    findings.extend(_audit_grants(desired, current))
    return tuple(findings)


def _audit_lf_tags(desired: DesiredState, current: CurrentState) -> List[AuditFinding]:
    findings: List[AuditFinding] = []
    desired_tags = _lf_tag_index(desired.lf_tags)
    current_tags = _lf_tag_index(current.lf_tags)
    for key, desired_tag in sorted(desired_tags.items()):
        current_tag = current_tags.get(key)
        if current_tag is None:
            findings.append(
                AuditFinding(
                    code="LF_TAG_MISSING",
                    severity="error",
                    target="lf_tag:{}".format(key),
                    message="Desired LF-Tag is missing",
                    details={"tag_key": key, "desired_values": list(desired_tag.values)},
                )
            )
            continue
        missing = sorted(set(desired_tag.values) - set(current_tag.values))
        if missing:
            findings.append(
                AuditFinding(
                    code="LF_TAG_VALUES_MISSING",
                    severity="error",
                    target="lf_tag:{}".format(key),
                    message="Desired LF-Tag values are missing",
                    details={"tag_key": key, "missing_values": missing},
                )
            )
        extra = sorted(set(current_tag.values) - set(desired_tag.values))
        if extra:
            severity = unmanaged_severity(desired.config, None, ResourceRef(kind="catalog"))
            if severity:
                findings.append(
                    AuditFinding(
                        code="LF_TAG_VALUES_UNMANAGED",
                        severity=severity,
                        target="lf_tag:{}".format(key),
                        message="Current LF-Tag has values not present in desired state",
                        details={"tag_key": key, "unmanaged_values": extra},
                    )
                )
    return findings


def _audit_lf_tag_expressions(desired: DesiredState, current: CurrentState) -> List[AuditFinding]:
    findings: List[AuditFinding] = []
    desired_expressions = _lf_tag_expression_index(desired.lf_tag_expressions)
    current_expressions = _lf_tag_expression_index(current.lf_tag_expressions)
    for key, desired_expression in sorted(desired_expressions.items(), key=lambda item: _expression_sort_key(item[0])):
        current_expression = current_expressions.get(key)
        if current_expression is None:
            findings.append(
                AuditFinding(
                    code="LF_TAG_EXPRESSION_MISSING",
                    severity="error",
                    target=desired_expression.identity,
                    message="Desired LF-Tag expression is missing",
                    details=_expression_details(desired_expression, "desired_expression"),
                )
            )
            continue
        if (
            current_expression.expression != desired_expression.expression
            or current_expression.description != desired_expression.description
        ):
            findings.append(
                AuditFinding(
                    code="LF_TAG_EXPRESSION_BODY_DRIFT",
                    severity="error",
                    target=desired_expression.identity,
                    message="Current LF-Tag expression body differs from desired state",
                    details={
                        "name": desired_expression.name,
                        "catalog_id": desired_expression.catalog_id,
                        "desired": desired_expression.to_dict(),
                        "current": current_expression.to_dict(),
                    },
                )
            )
    for key, current_expression in sorted(current_expressions.items(), key=lambda item: _expression_sort_key(item[0])):
        if key in desired_expressions:
            continue
        resource = ResourceRef(
            kind="lf_tag_expression",
            expression_name=current_expression.name,
            catalog_id=current_expression.catalog_id,
        )
        severity = unmanaged_severity(desired.config, None, resource)
        if severity:
            findings.append(
                AuditFinding(
                    code="LF_TAG_EXPRESSION_UNMANAGED",
                    severity=severity,
                    target=current_expression.identity,
                    message="Current LF-Tag expression is not present in desired state",
                    details=_expression_details(current_expression, "current"),
                )
            )
    return findings


def _expression_sort_key(key: Tuple[Any, str]) -> str:
    return "{}:{}".format(key[0] or "", key[1])


def _expression_details(expression: Any, field_name: str) -> Dict[str, Any]:
    return {
        "name": expression.name,
        "catalog_id": expression.catalog_id,
        field_name: expression.to_dict(),
    }


def _audit_resource_tags(desired: DesiredState, current: CurrentState) -> List[AuditFinding]:
    findings: List[AuditFinding] = []
    desired_by_resource = _resource_tag_index(desired.resource_tags)
    current_by_resource = _resource_tag_index(current.resource_tags)

    for resource, desired_tags in sorted(desired_by_resource.items(), key=lambda item: item[0].identity):
        current_tags = current_by_resource.get(resource, {})
        for key, desired_values in sorted(desired_tags.items()):
            current_values = current_tags.get(key, frozenset())
            missing = sorted(desired_values - current_values)
            if missing:
                findings.append(
                    AuditFinding(
                        code="RESOURCE_TAG_VALUES_MISSING",
                        severity="error",
                        target=resource.identity,
                        message="Resource is missing desired LF-Tag values",
                        details={"resource": resource.to_dict(), "tag_key": key, "missing_values": missing},
                    )
                )
            extra = sorted(current_values - desired_values)
            if extra:
                severity = unmanaged_severity(desired.config, None, resource)
                if severity:
                    findings.append(
                        AuditFinding(
                            code="RESOURCE_TAG_VALUES_UNMANAGED",
                            severity=severity,
                            target=resource.identity,
                            message="Resource has LF-Tag values not present in desired state",
                            details={"resource": resource.to_dict(), "tag_key": key, "unmanaged_values": extra},
                        )
                    )
        unmanaged_keys = sorted(set(current_tags) - set(desired_tags))
        for key in unmanaged_keys:
            severity = unmanaged_severity(desired.config, None, resource)
            if severity:
                findings.append(
                    AuditFinding(
                        code="RESOURCE_TAG_KEY_UNMANAGED",
                        severity=severity,
                        target=resource.identity,
                        message="Resource has LF-Tag key not present in desired state",
                        details={"resource": resource.to_dict(), "tag_key": key, "unmanaged_values": sorted(current_tags[key])},
                    )
                )
    return findings


def _audit_grants(desired: DesiredState, current: CurrentState) -> List[AuditFinding]:
    findings: List[AuditFinding] = []
    desired_grants = _grant_index(desired.grants)
    current_grants = _grant_index(current.grants)

    for identity, desired_grant in sorted(desired_grants.items(), key=lambda item: _grant_sort_key(item[0])):
        current_grant = current_grants.get(identity)
        if current_grant is None:
            findings.append(_grant_finding("GRANT_MISSING", "error", desired_grant, "Principal grant is missing", {
                "missing_permissions": list(desired_grant.permissions),
                "missing_grantable_permissions": list(desired_grant.grantable_permissions),
            }))
            continue
        missing_permissions = sorted(set(desired_grant.permissions) - set(current_grant.permissions))
        missing_grantables = sorted(set(desired_grant.grantable_permissions) - set(current_grant.grantable_permissions))
        if missing_permissions or missing_grantables:
            findings.append(_grant_finding("GRANT_PERMISSIONS_MISSING", "error", desired_grant, "Principal is missing desired permissions", {
                "missing_permissions": missing_permissions,
                "missing_grantable_permissions": missing_grantables,
            }))
        extra_permissions = sorted(set(current_grant.permissions) - set(desired_grant.permissions))
        extra_grantables = sorted(set(current_grant.grantable_permissions) - set(desired_grant.grantable_permissions))
        if extra_permissions or extra_grantables:
            severity = unmanaged_severity(desired.config, current_grant.principal, current_grant.resource)
            if severity:
                findings.append(_grant_finding("GRANT_PERMISSIONS_UNMANAGED", severity, current_grant, "Principal has permissions not present in desired state", {
                    "unmanaged_permissions": extra_permissions,
                    "unmanaged_grantable_permissions": extra_grantables,
                }))

    for identity, current_grant in sorted(current_grants.items(), key=lambda item: _grant_sort_key(item[0])):
        if identity not in desired_grants:
            severity = unmanaged_severity(desired.config, current_grant.principal, current_grant.resource)
            if severity:
                findings.append(_grant_finding("GRANT_UNMANAGED", severity, current_grant, "Principal grant is not present in desired state", {
                    "permissions": list(current_grant.permissions),
                    "grantable_permissions": list(current_grant.grantable_permissions),
                }))
    return findings


def _grant_finding(code: str, severity: str, grant: Grant, message: str, details: Mapping[str, Any]) -> AuditFinding:
    enriched = dict(details)
    enriched["principal"] = grant.principal
    enriched["resource"] = grant.resource.to_dict()
    return AuditFinding(
        code=code,
        severity=severity,
        target=_grant_target(grant),
        message=message,
        details=enriched,
    )


def _grant_sort_key(identity: Tuple[str, ResourceRef]) -> str:
    return "{}:{}".format(identity[0], identity[1].identity)
