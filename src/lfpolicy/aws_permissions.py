"""AWS IAM permission templates and preflight checks for live read-only lfpolicy use."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


PERMISSIONS_CHECK_SCHEMA_VERSION = "lfpolicy.permissions-check.v1"


@dataclass(frozen=True)
class IAMActionCheck:
    """IAM simulation result for one required AWS action."""

    action: str
    decision: str
    allowed: bool
    missing_context_values: Tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "decision": self.decision,
            "allowed": self.allowed,
            "missing_context_values": list(self.missing_context_values),
        }


@dataclass(frozen=True)
class IAMPermissionCheckReport:
    """Report describing whether an IAM principal can run a live lfpolicy workflow."""

    template: str
    include_glue_read: bool
    principal_arn: str
    caller_arn: Optional[str]
    actions: Tuple[IAMActionCheck, ...]
    schema_version: str = PERMISSIONS_CHECK_SCHEMA_VERSION

    @property
    def allowed(self) -> bool:
        return all(action.allowed for action in self.actions)

    @property
    def denied_actions(self) -> Tuple[str, ...]:
        return tuple(action.action for action in self.actions if not action.allowed)

    def to_dict(self) -> Dict[str, Any]:
        allowed_count = sum(1 for action in self.actions if action.allowed)
        return {
            "schema_version": self.schema_version,
            "template": self.template,
            "include_glue_read": self.include_glue_read,
            "principal_arn": self.principal_arn,
            "caller_arn": self.caller_arn,
            "allowed": self.allowed,
            "summary": {
                "total": len(self.actions),
                "allowed": allowed_count,
                "denied": len(self.actions) - allowed_count,
            },
            "denied_actions": list(self.denied_actions),
            "actions": [action.to_dict() for action in self.actions],
        }


@dataclass(frozen=True)
class AWSIAMPermissionChecker:
    """Boto3-backed IAM policy simulation helper."""

    iam_client: Any
    sts_client: Any

    @classmethod
    def from_boto3(
        cls,
        *,
        profile_name: Optional[str] = None,
        region_name: Optional[str] = None,
    ) -> "AWSIAMPermissionChecker":
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for live AWS permission checks. Install lfpolicy[aws]."
            ) from exc
        session = boto3.Session(profile_name=profile_name, region_name=region_name)
        return cls(session.client("iam"), session.client("sts"))

    def check(
        self,
        actions: Sequence[str],
        *,
        template: str,
        include_glue_read: bool = False,
        principal_arn: Optional[str] = None,
    ) -> IAMPermissionCheckReport:
        caller_arn: Optional[str] = None
        if principal_arn:
            policy_source_arn = policy_source_arn_from_caller(principal_arn)
        else:
            identity = self.sts_client.get_caller_identity()
            caller_arn = str(identity.get("Arn") or "")
            policy_source_arn = policy_source_arn_from_caller(caller_arn)
        checks = tuple(_checks_from_simulation(actions, self._simulate(policy_source_arn, actions)))
        return IAMPermissionCheckReport(
            template=template,
            include_glue_read=include_glue_read,
            principal_arn=policy_source_arn,
            caller_arn=caller_arn,
            actions=checks,
        )

    def _simulate(self, policy_source_arn: str, actions: Sequence[str]) -> List[Mapping[str, Any]]:
        request: Dict[str, Any] = {
            "PolicySourceArn": policy_source_arn,
            "ActionNames": list(actions),
            "ResourceArns": ["*"],
        }
        results: List[Mapping[str, Any]] = []
        while True:
            response = self.iam_client.simulate_principal_policy(**request)
            results.extend(response.get("EvaluationResults", ()))
            if not response.get("IsTruncated"):
                return results
            marker = response.get("Marker")
            if not marker:
                return results
            request["Marker"] = marker


def iam_policy_template(template: str, *, include_glue_read: bool = False) -> Dict[str, Any]:
    """Return the starter IAM policy for a live lfpolicy workflow template."""

    if template != "read-only":
        raise ValueError("Unsupported IAM permission template: {}".format(template))

    statements = [
        _iam_statement(
            "ReadLakeFormationState",
            (
                "lakeformation:GetLFTag",
                "lakeformation:ListLFTags",
                "lakeformation:GetLFTagExpression",
                "lakeformation:ListLFTagExpressions",
                "lakeformation:GetResourceLFTags",
                "lakeformation:ListPermissions",
                "lakeformation:GetDataCellsFilter",
                "lakeformation:ListDataCellsFilter",
            ),
        )
    ]
    if include_glue_read:
        statements.append(
            _iam_statement(
                "ReadGlueCatalogMetadata",
                (
                    "glue:GetDatabase",
                    "glue:GetDatabases",
                    "glue:GetTable",
                    "glue:GetTables",
                ),
            )
        )
    return {"Version": "2012-10-17", "Statement": statements}


def iam_policy_actions(policy: Mapping[str, Any]) -> Tuple[str, ...]:
    """Return unique policy actions in template order."""

    actions: List[str] = []
    seen = set()
    for statement in policy.get("Statement", ()):
        raw_actions = statement.get("Action", ()) if isinstance(statement, Mapping) else ()
        if isinstance(raw_actions, str):
            raw_actions = (raw_actions,)
        for action in raw_actions:
            action_name = str(action)
            if action_name not in seen:
                actions.append(action_name)
                seen.add(action_name)
    return tuple(actions)


def policy_source_arn_from_caller(caller_arn: str) -> str:
    """Return an IAM user/role ARN suitable for SimulatePrincipalPolicy."""

    if not caller_arn:
        raise RuntimeError("AWS caller identity did not include an ARN")
    parts = caller_arn.split(":", 5)
    if len(parts) != 6 or not caller_arn.startswith("arn:"):
        raise RuntimeError("Cannot parse AWS caller ARN {!r}; pass --principal-arn".format(caller_arn))
    arn_prefix, partition, service, _region, account_id, resource = parts
    if service == "iam" and (resource.startswith("role/") or resource.startswith("user/")):
        return caller_arn
    if service == "sts" and resource.startswith("assumed-role/"):
        role_and_session = resource[len("assumed-role/") :]
        role_name = role_and_session.split("/", 1)[0]
        if role_name:
            return "{}:{}:iam::{}:role/{}".format(arn_prefix, partition, account_id, role_name)
    raise RuntimeError(
        "Cannot infer an IAM role/user ARN from caller ARN {!r}; pass --principal-arn".format(caller_arn)
    )


def _iam_statement(sid: str, actions: Iterable[str]) -> Dict[str, Any]:
    return {
        "Sid": sid,
        "Effect": "Allow",
        "Action": list(actions),
        "Resource": "*",
    }


def _checks_from_simulation(
    actions: Sequence[str],
    evaluation_results: Iterable[Mapping[str, Any]],
) -> Iterable[IAMActionCheck]:
    by_action = {str(result.get("EvalActionName")): result for result in evaluation_results}
    for action in actions:
        result = by_action.get(action)
        if result is None:
            yield IAMActionCheck(action=action, decision="notReturned", allowed=False)
            continue
        decision = str(result.get("EvalDecision") or "implicitDeny")
        yield IAMActionCheck(
            action=action,
            decision=decision,
            allowed=decision == "allowed",
            missing_context_values=tuple(str(value) for value in result.get("MissingContextValues", ())),
        )
