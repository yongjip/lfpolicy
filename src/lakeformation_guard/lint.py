"""Semantic lint checks for desired Lake Formation guardrail policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple

from .config import lint_severity
from .models import DesiredState, Grant, ResourceTagAssignment
from .state_index import (
    LFTagExpressionKey,
    duplicate_lf_tag_expression_keys,
    lf_tag_expression_index,
    lf_tag_expression_key_identity,
    resolve_lf_tag_expression_key,
)


BROAD_PRINCIPALS = {"alliamprincipals", "iamallowedprincipals", "iam_allowed_principals"}
BROAD_PERMISSIONS = {"ALL", "SUPER"}
MUTATING_PERMISSIONS = {"ALTER", "CREATE_TABLE", "DELETE", "DROP", "INSERT"}
TABLE_MUTATING_PERMISSIONS = {"ALTER", "DELETE", "DROP", "INSERT"}
NAMED_GRANT_RESOURCE_KINDS = {"database", "table", "table_with_columns"}


@dataclass(frozen=True)
class LintFinding:
    """A desired-policy issue that can be detected without AWS access."""

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

    def with_severity(self, severity: str) -> "LintFinding":
        return LintFinding(
            code=self.code,
            severity=severity,
            target=self.target,
            message=self.message,
            details=self.details,
        )


def lint_desired(desired: DesiredState) -> Tuple[LintFinding, ...]:
    """Return semantic desired-policy findings without making AWS calls."""

    findings: List[LintFinding] = []
    if not desired.lf_tags and not desired.lf_tag_expressions and not desired.resource_tags and not desired.grants:
        findings.append(
            LintFinding(
                code="DESIRED_STATE_EMPTY",
                severity="warning",
                target="desired_state",
                message="Desired state does not define any LF-Tags, LF-Tag expressions, resource tag assignments, or grants",
                details={},
            )
        )

    tag_values = {tag.key: set(tag.values) for tag in desired.lf_tags}
    tag_assignment_scopes = {
        metadata.key: set(metadata.assignable_to)
        for metadata in desired.lf_tag_key_metadata
    }
    duplicate_expression_keys = duplicate_lf_tag_expression_keys(desired.lf_tag_expressions)
    expression_index = lf_tag_expression_index(
        desired.lf_tag_expressions,
        allow_duplicates=bool(duplicate_expression_keys),
    )
    findings.extend(_lint_lf_tag_definitions(tag_values))
    findings.extend(_lint_duplicate_lf_tag_expression_keys(duplicate_expression_keys))
    for expression in desired.lf_tag_expressions:
        findings.extend(_lint_lf_tag_expression_definition(expression, tag_values))
    for assignment in desired.resource_tags:
        findings.extend(
            _lint_resource_tag_assignment(
                assignment,
                tag_values,
                tag_assignment_scopes,
            )
        )
    for grant in desired.grants:
        findings.extend(_lint_grant(grant, tag_values, tag_assignment_scopes, expression_index))
    findings.extend(_lint_combined_grant_conflicts(desired.grants, tag_assignment_scopes))
    return tuple(_apply_lint_config(findings, desired))


def _lint_lf_tag_definitions(tag_values: Mapping[str, set]) -> List[LintFinding]:
    findings: List[LintFinding] = []
    for tag_key, values in sorted(tag_values.items()):
        if len(values) > 1000:
            findings.append(
                LintFinding(
                    code="LF_TAG_VALUE_LIMIT_EXCEEDED",
                    severity="error",
                    target="lf_tag:{}".format(tag_key),
                    message="AWS Lake Formation supports at most 1000 values per LF-Tag key",
                    details={"tag_key": tag_key, "value_count": len(values)},
                )
            )
        case_sensitive_values = sorted(_case_sensitive_values((tag_key, *values)))
        if case_sensitive_values:
            findings.append(
                LintFinding(
                    code="LF_TAG_CASE_NORMALIZATION",
                    severity="error",
                    target="lf_tag:{}".format(tag_key),
                    message="AWS Lake Formation stores LF-Tag keys and values in lower case",
                    details={"values": case_sensitive_values},
                )
            )
    return findings


def _lint_resource_tag_assignment(
    assignment: ResourceTagAssignment,
    tag_values: Mapping[str, set],
    tag_assignment_scopes: Mapping[str, set],
) -> List[LintFinding]:
    findings: List[LintFinding] = []
    assignment_scope = _resource_tag_assignment_scope(assignment.resource.kind)
    if assignment_scope is None:
        findings.append(
            LintFinding(
                code="RESOURCE_TAG_KIND_UNSUPPORTED",
                severity="error",
                target=assignment.resource.identity,
                message="LF-Tag assignments are supported only on databases, tables, and columns",
                details={
                    "resource": assignment.resource.to_dict(),
                    "resource_kind": assignment.resource.kind,
                },
            )
        )
    if len(assignment.tags) > 50:
        findings.append(
            LintFinding(
                code="RESOURCE_TAG_LIMIT_EXCEEDED",
                severity="error",
                target=assignment.resource.identity,
                message="AWS Lake Formation supports at most 50 LF-Tags assigned to a resource",
                details={
                    "resource": assignment.resource.to_dict(),
                    "tag_count": len(assignment.tags),
                },
            )
        )
    for tag_key, values in sorted(assignment.tags.items()):
        if len(values) > 1:
            findings.append(
                LintFinding(
                    code="RESOURCE_TAG_MULTIPLE_VALUES",
                    severity="error",
                    target=assignment.resource.identity,
                    message="AWS Lake Formation allows only one value per LF-Tag key on a resource",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "tag_key": tag_key,
                        "tag_values": sorted(values),
                    },
                )
            )
        case_sensitive_values = sorted(_case_sensitive_values((tag_key, *values)))
        if case_sensitive_values:
            findings.append(
                LintFinding(
                    code="LF_TAG_CASE_NORMALIZATION",
                    severity="error",
                    target=assignment.resource.identity,
                    message="AWS Lake Formation stores LF-Tag keys and values in lower case",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "values": case_sensitive_values,
                    },
                )
            )
        if tag_key not in tag_values:
            findings.append(
                LintFinding(
                    code="RESOURCE_TAG_KEY_UNDEFINED",
                    severity="error",
                    target=assignment.resource.identity,
                    message="Resource tag assignment references an LF-Tag key that is not defined",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "tag_key": tag_key,
                        "tag_values": sorted(values),
                    },
                )
            )
            continue
        metadata_scopes = tag_assignment_scopes.get(tag_key)
        if (
            assignment_scope is not None
            and metadata_scopes is not None
            and assignment_scope not in metadata_scopes
        ):
            findings.append(
                LintFinding(
                    code="RESOURCE_TAG_SCOPE_UNSUPPORTED",
                    severity="error",
                    target=assignment.resource.identity,
                    message="Resource tag assignment uses an LF-Tag key outside its declared assignment scope",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "tag_key": tag_key,
                        "assignment_scope": assignment_scope,
                        "assignable_to": sorted(metadata_scopes),
                    },
                )
            )
        undefined_values = sorted(values - tag_values[tag_key])
        if undefined_values:
            findings.append(
                LintFinding(
                    code="RESOURCE_TAG_VALUE_UNDEFINED",
                    severity="error",
                    target=assignment.resource.identity,
                    message="Resource tag assignment uses LF-Tag values that are not defined",
                    details={
                        "resource": assignment.resource.to_dict(),
                        "tag_key": tag_key,
                        "undefined_values": undefined_values,
                    },
                )
            )
    return findings


def _lint_lf_tag_expression_definition(
    expression_definition: Any,
    tag_values: Mapping[str, set],
) -> List[LintFinding]:
    findings: List[LintFinding] = []
    if len(expression_definition.expression) > 50:
        findings.append(
            LintFinding(
                code="LF_TAG_EXPRESSION_TOO_LARGE",
                severity="error",
                target=expression_definition.identity,
                message="AWS Lake Formation supports at most 50 LF-Tag keys in a named expression",
                details={
                    "name": expression_definition.name,
                    "expression_key_count": len(expression_definition.expression),
                },
            )
        )
    for expression_item in expression_definition.expression:
        findings.extend(
            _lint_expression_item(
                expression_item,
                tag_values,
                target=expression_definition.identity,
                details={"name": expression_definition.name},
                code_prefix="LF_TAG_EXPRESSION",
            )
        )
    return findings


def _resource_tag_assignment_scope(resource_kind: str) -> Any:
    if resource_kind == "database":
        return "database"
    if resource_kind == "table":
        return "table"
    if resource_kind == "table_with_columns":
        return "column"
    return None


def _lint_duplicate_lf_tag_expression_keys(
    duplicate_keys: Tuple[LFTagExpressionKey, ...],
) -> List[LintFinding]:
    findings: List[LintFinding] = []
    for key in duplicate_keys:
        findings.append(
            LintFinding(
                code="LF_TAG_EXPRESSION_DUPLICATE_IDENTITY",
                severity="error",
                target=lf_tag_expression_key_identity(key),
                message="Desired state defines multiple LF-Tag expressions with the same catalog ID and name",
                details={"catalog_id": key[0], "name": key[1]},
            )
        )
    return findings


def _named_lf_tag_expression_defined(
    expression_index: Mapping[LFTagExpressionKey, Any],
    catalog_id: Optional[str],
    expression_name: str,
) -> bool:
    return resolve_lf_tag_expression_key(expression_index, catalog_id, expression_name) is not None


def _lint_grant(
    grant: Grant,
    tag_values: Mapping[str, set],
    tag_assignment_scopes: Mapping[str, set],
    expression_index: Mapping[LFTagExpressionKey, Any],
) -> List[LintFinding]:
    findings = _lint_grant_governance(grant, tag_assignment_scopes)
    if grant.resource.kind != "lf_tag_policy":
        return findings
    if grant.resource.expression_name:
        if not _named_lf_tag_expression_defined(
            expression_index,
            grant.resource.catalog_id,
            grant.resource.expression_name,
        ):
            findings.append(
                LintFinding(
                    code="LF_TAG_POLICY_EXPRESSION_NAME_UNDEFINED",
                    severity="error",
                    target=_grant_target(grant),
                    message="LF-Tag policy references a named LF-Tag expression that is not defined",
                    details={
                        "principal": grant.principal,
                        "resource": grant.resource.to_dict(),
                        "expression_name": grant.resource.expression_name,
                        "catalog_id": grant.resource.catalog_id,
                    },
                )
            )
        return findings

    if len(grant.resource.expression) > 50:
        findings.append(
            LintFinding(
                code="LF_TAG_POLICY_EXPRESSION_TOO_LARGE",
                severity="error",
                target=_grant_target(grant),
                message="AWS Lake Formation supports at most 50 LF-Tag keys in an expression",
                details={
                    "principal": grant.principal,
                    "resource": grant.resource.to_dict(),
                    "expression_key_count": len(grant.resource.expression),
                },
            )
        )
    for expression_item in grant.resource.expression:
        findings.extend(
            _lint_expression_item(
                expression_item,
                tag_values,
                target=_grant_target(grant),
                details={"principal": grant.principal, "resource": grant.resource.to_dict()},
                code_prefix="LF_TAG_POLICY",
            )
        )
    return findings


def _lint_expression_item(
    expression_item: Any,
    tag_values: Mapping[str, set],
    *,
    target: str,
    details: Mapping[str, Any],
    code_prefix: str,
) -> List[LintFinding]:
    findings: List[LintFinding] = []
    common_details = dict(details)
    if len(expression_item.values) > 1000:
        finding_details = dict(common_details)
        finding_details.update({"tag_key": expression_item.key, "value_count": len(expression_item.values)})
        findings.append(
            LintFinding(
                code="{}_VALUE_LIMIT_EXCEEDED".format(code_prefix),
                severity="error",
                target=target,
                message="AWS Lake Formation supports at most 1000 values per LF-Tag key in an expression",
                details=finding_details,
            )
        )
    case_sensitive_values = sorted(_case_sensitive_values((expression_item.key, *expression_item.values)))
    if case_sensitive_values:
        finding_details = dict(common_details)
        finding_details["values"] = case_sensitive_values
        findings.append(
            LintFinding(
                code="LF_TAG_CASE_NORMALIZATION",
                severity="error",
                target=target,
                message="AWS Lake Formation stores LF-Tag keys and values in lower case",
                details=finding_details,
            )
        )
    wildcard_values = sorted(value for value in expression_item.values if value == "*")
    if wildcard_values:
        finding_details = dict(common_details)
        finding_details["tag_key"] = expression_item.key
        findings.append(
            LintFinding(
                code="{}_WILDCARD_VALUE".format(code_prefix),
                severity="warning",
                target=target,
                message="LF-Tag expression uses * and grants access to all values for a key",
                details=finding_details,
            )
        )
    if expression_item.key not in tag_values:
        finding_details = dict(common_details)
        finding_details.update({"tag_key": expression_item.key, "tag_values": list(expression_item.values)})
        findings.append(
            LintFinding(
                code="{}_KEY_UNDEFINED".format(code_prefix),
                severity="error",
                target=target,
                message="LF-Tag expression references an LF-Tag key that is not defined",
                details=finding_details,
            )
        )
        return findings
    undefined_values = sorted(
        value for value in set(expression_item.values) - tag_values[expression_item.key] if value != "*"
    )
    if undefined_values:
        finding_details = dict(common_details)
        finding_details.update({"tag_key": expression_item.key, "undefined_values": undefined_values})
        findings.append(
            LintFinding(
                code="{}_VALUE_UNDEFINED".format(code_prefix),
                severity="error",
                target=target,
                message="LF-Tag expression uses LF-Tag values that are not defined",
                details=finding_details,
            )
        )
    return findings


def _lint_grant_governance(
    grant: Grant,
    tag_assignment_scopes: Mapping[str, set],
) -> List[LintFinding]:
    findings: List[LintFinding] = []
    target = _grant_target(grant)
    principal = _normalize_principal(grant.principal)
    if principal in BROAD_PRINCIPALS:
        findings.append(
            LintFinding(
                code="BROAD_PRINCIPAL_GRANT",
                severity="error",
                target=target,
                message="Lake Formation grants to broad IAM principal groups are not controlled policy",
                details={
                    "principal": grant.principal,
                    "resource": grant.resource.to_dict(),
                },
            )
        )

    broad_permissions = sorted(set(grant.permissions) & BROAD_PERMISSIONS)
    if broad_permissions:
        findings.append(
            LintFinding(
                code="BROAD_PERMISSION_GRANT",
                severity="error",
                target=target,
                message="Broad Lake Formation permissions such as ALL/SUPER are not allowed in desired policy",
                details={
                    "principal": grant.principal,
                    "resource": grant.resource.to_dict(),
                    "permissions": broad_permissions,
                },
            )
        )

    mutating_permissions = _mutating_permissions_requiring_review(grant, tag_assignment_scopes)
    if mutating_permissions:
        findings.append(
            LintFinding(
                code="MUTATING_PERMISSION_REVIEW",
                severity="warning",
                target=target,
                message="Mutating Lake Formation permissions should be isolated from routine read workflows",
                details={
                    "principal": grant.principal,
                    "resource": grant.resource.to_dict(),
                    "permissions": mutating_permissions,
                },
            )
        )

    if grant.grantable_permissions:
        findings.append(
            LintFinding(
                code="GRANTABLE_PERMISSION_REVIEW",
                severity="warning",
                target=target,
                message="Grant option delegates Lake Formation authority and should be separately reviewed",
                details={
                    "principal": grant.principal,
                    "resource": grant.resource.to_dict(),
                    "grantable_permissions": list(grant.grantable_permissions),
                },
            )
        )

    if grant.resource.kind in NAMED_GRANT_RESOURCE_KINDS:
        findings.append(
            LintFinding(
                code="NAMED_RESOURCE_GRANT_REVIEW",
                severity="warning",
                target=target,
                message="Named database/table grants should be documented exceptions; prefer LF-Tag policy grants",
                details={
                    "principal": grant.principal,
                    "resource": grant.resource.to_dict(),
                    "permissions": list(grant.permissions),
                },
            )
        )

    if (
        _is_lf_tag_table_policy(grant)
        and "SELECT" in grant.permissions
        and _lf_tag_policy_can_narrow_columns(grant.resource, tag_assignment_scopes)
    ):
        conflicting_permissions = sorted(set(grant.permissions) & TABLE_MUTATING_PERMISSIONS)
        if conflicting_permissions:
            findings.append(
                LintFinding(
                    code="LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT",
                    severity="error",
                    target=target,
                    message=(
                        "LF-Tag table policy grants must not combine SELECT with table mutation permissions"
                    ),
                    details={
                        "principal": grant.principal,
                        "resource": grant.resource.to_dict(),
                        "conflicting_permissions": conflicting_permissions,
                    },
                )
            )

    if grant.resource.kind == "table_with_columns":
        conflicting_permissions = sorted(set(grant.permissions) & TABLE_MUTATING_PERMISSIONS)
        if conflicting_permissions:
            findings.append(
                LintFinding(
                    code="COLUMN_FILTER_MUTATING_PERMISSION_CONFLICT",
                    severity="error",
                    target=target,
                    message=(
                        "Column-filtered grants must not include table mutation permissions"
                    ),
                    details={
                        "principal": grant.principal,
                        "resource": grant.resource.to_dict(),
                        "conflicting_permissions": conflicting_permissions,
                    },
                )
            )

    return findings


def _lint_combined_grant_conflicts(
    grants: Tuple[Grant, ...],
    tag_assignment_scopes: Mapping[str, set],
) -> List[LintFinding]:
    findings: List[LintFinding] = []
    combined: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for grant in grants:
        if not _is_lf_tag_table_policy(grant):
            continue
        key = (grant.principal, grant.resource.identity)
        entry = combined.setdefault(
            key,
            {
                "principal": grant.principal,
                "resource": grant.resource,
                "permissions": set(),
                "grant_count": 0,
            },
        )
        entry["permissions"].update(grant.permissions)
        entry["grant_count"] += 1

    for entry in combined.values():
        if entry["grant_count"] < 2:
            continue
        permissions = entry["permissions"]
        if "SELECT" not in permissions:
            continue
        if not _lf_tag_policy_can_narrow_columns(entry["resource"], tag_assignment_scopes):
            continue
        conflicting_permissions = sorted(permissions & TABLE_MUTATING_PERMISSIONS)
        if not conflicting_permissions:
            continue
        grant = Grant(
            principal=entry["principal"],
            resource=entry["resource"],
            permissions=tuple(sorted(permissions)),
        )
        target = _grant_target(grant)
        findings.append(
            LintFinding(
                code="LF_TAG_POLICY_COMBINED_TABLE_SELECT_MUTATION_CONFLICT",
                severity="error",
                target=target,
                message=(
                    "Separate grants for the same LF-Tag table policy combine SELECT with table mutation permissions"
                ),
                details={
                    "principal": grant.principal,
                    "resource": grant.resource.to_dict(),
                    "conflicting_permissions": conflicting_permissions,
                },
            )
        )
    return findings


def _is_lf_tag_table_policy(grant: Grant) -> bool:
    return grant.resource.kind == "lf_tag_policy" and grant.resource.resource_type == "TABLE"


def _mutating_permissions_requiring_review(
    grant: Grant,
    tag_assignment_scopes: Mapping[str, set],
) -> List[str]:
    mutating_permissions = sorted(set(grant.permissions) & MUTATING_PERMISSIONS)
    if not mutating_permissions:
        return []
    if (
        _is_lf_tag_table_policy(grant)
        and not _lf_tag_policy_can_narrow_columns(grant.resource, tag_assignment_scopes)
    ):
        return sorted(set(mutating_permissions) - {"DELETE", "INSERT"})
    if (
        grant.resource.kind == "lf_tag_policy"
        and grant.resource.resource_type == "DATABASE"
        and not _lf_tag_policy_can_narrow_columns(grant.resource, tag_assignment_scopes)
    ):
        return sorted(set(mutating_permissions) - {"CREATE_TABLE"})
    return mutating_permissions


def _lf_tag_policy_can_narrow_columns(
    resource: Any,
    tag_assignment_scopes: Mapping[str, set],
) -> bool:
    expression_keys = [item.key for item in resource.expression]
    if not expression_keys:
        return True
    for tag_key in expression_keys:
        scopes = tag_assignment_scopes.get(tag_key)
        if scopes is None:
            return True
        if "column" in scopes:
            return True
    return False


def _case_sensitive_values(values: Tuple[str, ...]) -> Tuple[str, ...]:
    return tuple(value for value in values if value != value.lower())


def _normalize_principal(principal: str) -> str:
    return principal.strip().lower().replace(" ", "").replace("-", "_")


def _grant_target(grant: Grant) -> str:
    return "{} -> {}".format(grant.principal, grant.resource.identity)


def _apply_lint_config(findings: List[LintFinding], desired: DesiredState) -> List[LintFinding]:
    configured: List[LintFinding] = []
    for finding in findings:
        severity = lint_severity(desired.config, finding.code, finding.severity)
        if severity is None:
            continue
        configured.append(finding.with_severity(severity))
    return configured
