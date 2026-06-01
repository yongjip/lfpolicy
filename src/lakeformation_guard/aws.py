"""Optional boto3 adapter for live Lake Formation inventory and apply."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .models import (
    CurrentState,
    DesiredState,
    Grant,
    LFTagDefinition,
    LFTagExpressionDefinition,
    ResourceRef,
    ResourceTagAssignment,
)
from .planner import Change, Plan


@dataclass(frozen=True)
class ApplyResult:
    """Result of applying or dry-running a single change."""

    action: str
    target: str
    applied: bool
    response: Mapping[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "target": self.target,
            "applied": self.applied,
            "response": dict(self.response),
        }


class AWSLakeFormationAdapter:
    """Thin boto3-backed adapter for Lake Formation operations."""

    def __init__(self, lakeformation_client: Any, *, catalog_id: Optional[str] = None) -> None:
        self.lakeformation = lakeformation_client
        self.catalog_id = catalog_id

    @classmethod
    def from_boto3(
        cls,
        *,
        profile_name: Optional[str] = None,
        region_name: Optional[str] = None,
        catalog_id: Optional[str] = None,
    ) -> "AWSLakeFormationAdapter":
        try:
            import boto3  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "boto3 is required for live AWS operations. Install lfguard[aws]."
            ) from exc
        session = boto3.Session(profile_name=profile_name, region_name=region_name)
        return cls(session.client("lakeformation"), catalog_id=catalog_id)

    def load_current_state_for(self, desired: DesiredState) -> CurrentState:
        """Load only the current AWS surface needed to compare with desired state."""

        lf_tags = list(self._load_lf_tags(desired))
        lf_tag_expressions = list(self._load_lf_tag_expressions(desired))
        resource_tags = list(self._load_resource_tags(desired))
        grants = list(self._load_grants(desired))
        return CurrentState(
            lf_tags=tuple(lf_tags),
            lf_tag_expressions=tuple(lf_tag_expressions),
            resource_tags=tuple(resource_tags),
            grants=tuple(grants),
        )

    def import_state(self, *, include: Iterable[str]) -> CurrentState:
        include_set = set(include)
        lf_tags = list(self._import_lf_tags()) if "lf-tags" in include_set else []
        lf_tag_expressions = (
            list(self._import_lf_tag_expressions()) if "lf-tag-expressions" in include_set else []
        )
        grants = list(self._import_grants()) if "grants" in include_set else []
        resource_tags = []
        if "resource-tags" in include_set:
            resources = {
                grant.resource
                for grant in grants
                if grant.resource.kind not in {"lf_tag_policy", "lf_tag_expression"}
            }
            resource_tags = list(self._load_tags_for_resources(resources))
        return CurrentState(
            lf_tags=tuple(lf_tags),
            lf_tag_expressions=tuple(lf_tag_expressions),
            resource_tags=tuple(resource_tags),
            grants=tuple(grants),
        )

    def apply(self, change_plan: Plan, *, dry_run: bool = True, allow_destructive: bool = False) -> List[ApplyResult]:
        results: List[ApplyResult] = []
        for change in change_plan.executable_changes(allow_destructive=allow_destructive):
            if dry_run:
                results.append(ApplyResult(change.action, change.target, False, {"dry_run": True}))
                continue
            results.append(self._apply_change(change))
        return results

    def _load_lf_tags(self, desired: DesiredState) -> Iterable[LFTagDefinition]:
        for tag in desired.lf_tags:
            kwargs = self._with_catalog_id({"TagKey": tag.key})
            try:
                response = self.lakeformation.get_lf_tag(**kwargs)
            except Exception as exc:
                if _is_not_found(exc):
                    continue
                raise
            values = response.get("TagValues", ())
            if values:
                yield LFTagDefinition(tag.key, tuple(values))

    def _load_lf_tag_expressions(self, desired: DesiredState) -> Iterable[LFTagExpressionDefinition]:
        expression_keys = {
            (expression.catalog_id, expression.name)
            for expression in desired.lf_tag_expressions
        }
        expression_keys.update(
            (grant.resource.catalog_id, grant.resource.expression_name)
            for grant in desired.grants
            if grant.resource.kind in {"lf_tag_policy", "lf_tag_expression"} and grant.resource.expression_name
        )
        for catalog_id, name in sorted(expression_keys, key=lambda item: (item[0] or "", item[1])):
            request = {"Name": name, "catalog_id": catalog_id}
            kwargs = self._with_catalog_id(request)
            try:
                response = self.lakeformation.get_lf_tag_expression(**kwargs)
            except Exception as exc:
                if _is_not_found(exc):
                    continue
                raise
            expression = _expression_definition_from_response(response, fallback_name=name)
            if expression:
                yield expression

    def _load_resource_tags(self, desired: DesiredState) -> Iterable[ResourceTagAssignment]:
        resources = {assignment.resource for assignment in desired.resource_tags}
        resources.update(grant.resource for grant in desired.grants if grant.resource.kind != "lf_tag_policy")
        yield from self._load_tags_for_resources(resources)

    def _load_tags_for_resources(self, resources: Iterable[ResourceRef]) -> Iterable[ResourceTagAssignment]:
        for resource in sorted(resources):
            if resource.kind == "lf_tag_expression":
                continue
            kwargs = self._with_catalog_id({"Resource": to_lf_resource(resource)})
            try:
                response = self.lakeformation.get_resource_lf_tags(**kwargs)
            except Exception as exc:
                if _is_not_found(exc):
                    continue
                raise
            tags = _extract_resource_tags(response)
            if tags:
                yield ResourceTagAssignment(resource=resource, tags=tags)

    def _import_lf_tags(self) -> Iterable[LFTagDefinition]:
        kwargs = self._with_catalog_id({"MaxResults": 100})
        for item in self._paginate_or_call("list_lf_tags", kwargs, "LFTags"):
            key = item.get("TagKey")
            values = item.get("TagValues", ())
            if key and values:
                yield LFTagDefinition(str(key), tuple(values))

    def _import_lf_tag_expressions(self) -> Iterable[LFTagExpressionDefinition]:
        kwargs = self._with_catalog_id({"MaxResults": 100})
        for item in self._paginate_or_call("list_lf_tag_expressions", kwargs, "LFTagExpressions"):
            expression = _expression_definition_from_response(item)
            if expression:
                yield expression

    def _import_grants(self) -> Iterable[Grant]:
        kwargs = self._with_catalog_id({"MaxResults": 100})
        for item in self._list_permissions(kwargs):
            grant = _grant_from_permission_item(item)
            if grant:
                yield grant

    def _load_grants(self, desired: DesiredState) -> Iterable[Grant]:
        seen = set()
        for desired_grant in desired.grants:
            key = desired_grant.identity
            if key in seen:
                continue
            seen.add(key)
            kwargs = {
                "Principal": {"DataLakePrincipalIdentifier": desired_grant.principal},
                "Resource": to_lf_resource(desired_grant.resource),
                "MaxResults": 100,
            }
            kwargs = self._with_catalog_id(kwargs)
            for item in self._list_permissions(kwargs):
                principal = item.get("Principal", {}).get("DataLakePrincipalIdentifier", desired_grant.principal)
                resource = from_lf_resource(item.get("Resource", {})) or desired_grant.resource
                permissions = tuple(item.get("Permissions", ()))
                grantables = tuple(item.get("PermissionsWithGrantOption", ()))
                if permissions:
                    yield Grant(principal=principal, resource=resource, permissions=permissions, grantable_permissions=grantables)

    def _list_permissions(self, kwargs: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
        if hasattr(self.lakeformation, "get_paginator"):
            try:
                paginator = self.lakeformation.get_paginator("list_permissions")
                for page in paginator.paginate(**dict(kwargs)):
                    for item in page.get("PrincipalResourcePermissions", ()):
                        yield item
                return
            except Exception as exc:
                if not _is_operation_not_pageable(exc):
                    raise
        next_token = None
        while True:
            request = dict(kwargs)
            if next_token:
                request["NextToken"] = next_token
            response = self.lakeformation.list_permissions(**request)
            for item in response.get("PrincipalResourcePermissions", ()):
                yield item
            next_token = response.get("NextToken")
            if not next_token:
                break

    def _apply_change(self, change: Change) -> ApplyResult:
        action = change.action
        payload = dict(change.payload)
        if action == "lf_tag.create":
            response = self.lakeformation.create_lf_tag(**self._with_catalog_id({
                "TagKey": payload["tag_key"],
                "TagValues": payload["tag_values"],
            }))
        elif action == "lf_tag.add_values":
            response = self.lakeformation.update_lf_tag(**self._with_catalog_id({
                "TagKey": payload["tag_key"],
                "TagValuesToAdd": payload["tag_values"],
            }))
        elif action == "lf_tag.remove_values":
            response = self.lakeformation.update_lf_tag(**self._with_catalog_id({
                "TagKey": payload["tag_key"],
                "TagValuesToDelete": payload["tag_values"],
            }))
        elif action == "lf_tag_expression.create":
            response = self.lakeformation.create_lf_tag_expression(**self._with_catalog_id({
                "Name": payload["name"],
                "Description": payload.get("description", ""),
                "Expression": _expression_pairs(payload["expression"]),
                "catalog_id": payload.get("catalog_id"),
            }))
        elif action == "lf_tag_expression.update":
            response = self.lakeformation.update_lf_tag_expression(**self._with_catalog_id({
                "Name": payload["name"],
                "Description": payload.get("description", ""),
                "Expression": _expression_pairs(payload["expression"]),
                "catalog_id": payload.get("catalog_id"),
            }))
        elif action == "lf_tag_expression.delete":
            response = self.lakeformation.delete_lf_tag_expression(**self._with_catalog_id({
                "Name": payload["name"],
                "catalog_id": payload.get("catalog_id"),
            }))
        elif action == "resource_tag.add_values":
            response = self.lakeformation.add_lf_tags_to_resource(**self._with_catalog_id({
                "Resource": to_lf_resource(ResourceRef.from_dict(payload["resource"])),
                "LFTags": _lf_tag_pairs(payload["tags"]),
            }))
        elif action == "resource_tag.remove_values":
            response = self.lakeformation.remove_lf_tags_from_resource(**self._with_catalog_id({
                "Resource": to_lf_resource(ResourceRef.from_dict(payload["resource"])),
                "LFTags": _lf_tag_pairs(payload["tags"]),
            }))
        elif action == "grant.add_permissions":
            response = self.lakeformation.grant_permissions(**self._with_catalog_id({
                "Principal": {"DataLakePrincipalIdentifier": payload["principal"]},
                "Resource": to_lf_resource(ResourceRef.from_dict(payload["resource"])),
                "Permissions": payload.get("permissions", ()),
                "PermissionsWithGrantOption": payload.get("grantable_permissions", ()),
            }))
        elif action == "grant.revoke_permissions":
            response = self.lakeformation.revoke_permissions(**self._with_catalog_id({
                "Principal": {"DataLakePrincipalIdentifier": payload["principal"]},
                "Resource": to_lf_resource(ResourceRef.from_dict(payload["resource"])),
                "Permissions": payload.get("permissions", ()),
                "PermissionsWithGrantOption": payload.get("grantable_permissions", ()),
            }))
        else:
            raise ValueError("Unsupported change action: {}".format(action))
        return ApplyResult(action=change.action, target=change.target, applied=True, response=response or {})

    def _with_catalog_id(self, kwargs: Mapping[str, Any]) -> Dict[str, Any]:
        request = dict(kwargs)
        payload_catalog_id = request.pop("catalog_id", None)
        if payload_catalog_id:
            request.setdefault("CatalogId", payload_catalog_id)
        if self.catalog_id:
            request.setdefault("CatalogId", self.catalog_id)
        return request

    def _paginate_or_call(
        self,
        operation_name: str,
        kwargs: Mapping[str, Any],
        result_key: str,
    ) -> Iterable[Mapping[str, Any]]:
        if hasattr(self.lakeformation, "get_paginator"):
            try:
                paginator = self.lakeformation.get_paginator(operation_name)
                for page in paginator.paginate(**dict(kwargs)):
                    for item in page.get(result_key, ()):
                        yield item
                return
            except Exception as exc:
                if not _is_operation_not_pageable(exc):
                    raise
        next_token = None
        method = getattr(self.lakeformation, operation_name)
        while True:
            request = dict(kwargs)
            if next_token:
                request["NextToken"] = next_token
            response = method(**request)
            for item in response.get(result_key, ()):
                yield item
            next_token = response.get("NextToken")
            if not next_token:
                break


def to_lf_resource(resource: ResourceRef) -> Dict[str, Any]:
    if resource.kind == "catalog":
        return {"Catalog": {}}
    if resource.kind == "database":
        return {"Database": _catalog_scoped({"Name": resource.database_name}, resource)}
    if resource.kind == "table":
        return {"Table": _catalog_scoped({
            "DatabaseName": resource.database_name,
            "Name": resource.table_name,
        }, resource)}
    if resource.kind == "table_with_columns":
        return {"TableWithColumns": _catalog_scoped({
            "DatabaseName": resource.database_name,
            "Name": resource.table_name,
            "ColumnNames": list(resource.columns),
        }, resource)}
    if resource.kind == "data_location":
        return {"DataLocation": _catalog_scoped({"ResourceArn": resource.location}, resource)}
    if resource.kind == "lf_tag_policy":
        policy = {"ResourceType": resource.resource_type}
        if resource.expression_name:
            policy["ExpressionName"] = resource.expression_name
        else:
            policy["Expression"] = [
                {"TagKey": item.key, "TagValues": list(item.values)}
                for item in resource.expression
            ]
        if resource.catalog_id:
            policy["CatalogId"] = resource.catalog_id
        return {"LFTagPolicy": policy}
    if resource.kind == "lf_tag_expression":
        return {
            "LFTagExpression": _catalog_scoped({"Name": resource.expression_name}, resource)
        }
    raise ValueError("Unsupported resource kind: {}".format(resource.kind))


def from_lf_resource(raw: Mapping[str, Any]) -> Optional[ResourceRef]:
    if "Catalog" in raw:
        return ResourceRef(kind="catalog")
    if "Database" in raw:
        item = raw["Database"]
        return ResourceRef(kind="database", database_name=item.get("Name"), catalog_id=item.get("CatalogId"))
    if "Table" in raw:
        item = raw["Table"]
        return ResourceRef(kind="table", database_name=item.get("DatabaseName"), table_name=item.get("Name"), catalog_id=item.get("CatalogId"))
    if "TableWithColumns" in raw:
        item = raw["TableWithColumns"]
        return ResourceRef(
            kind="table_with_columns",
            database_name=item.get("DatabaseName"),
            table_name=item.get("Name"),
            columns=tuple(item.get("ColumnNames", ())),
            catalog_id=item.get("CatalogId"),
        )
    if "DataLocation" in raw:
        item = raw["DataLocation"]
        return ResourceRef(kind="data_location", location=item.get("ResourceArn"), catalog_id=item.get("CatalogId"))
    if "LFTagPolicy" in raw:
        item = raw["LFTagPolicy"]
        data = {
            "kind": "lf_tag_policy",
            "resource_type": item.get("ResourceType"),
            "catalog_id": item.get("CatalogId"),
        }
        if item.get("ExpressionName"):
            data["expression_name"] = item.get("ExpressionName")
        else:
            data["expression"] = {
                expr.get("TagKey"): expr.get("TagValues", ())
                for expr in item.get("Expression", ())
            }
        return ResourceRef.from_dict(data)
    if "LFTagExpression" in raw:
        item = raw["LFTagExpression"]
        return ResourceRef(kind="lf_tag_expression", expression_name=item.get("Name"), catalog_id=item.get("CatalogId"))
    return None


def _catalog_scoped(data: Mapping[str, Any], resource: ResourceRef) -> Dict[str, Any]:
    result = {key: value for key, value in data.items() if value not in (None, "")}
    if resource.catalog_id:
        result["CatalogId"] = resource.catalog_id
    return result


def _lf_tag_pairs(tags: Mapping[str, Iterable[str]]) -> List[Dict[str, Any]]:
    return [{"TagKey": key, "TagValues": list(values)} for key, values in sorted(tags.items())]


def _expression_pairs(raw: Any) -> List[Dict[str, Any]]:
    if isinstance(raw, Mapping):
        return _lf_tag_pairs(raw)
    pairs = []
    for item in raw:
        pairs.append(
            {
                "TagKey": item.get("key") or item.get("TagKey"),
                "TagValues": item.get("values") or item.get("TagValues", ()),
            }
        )
    return pairs


def _expression_definition_from_response(
    raw: Mapping[str, Any],
    *,
    fallback_name: Optional[str] = None,
) -> Optional[LFTagExpressionDefinition]:
    name = raw.get("Name") or fallback_name
    expression = raw.get("Expression", ())
    if not name or not expression:
        return None
    return LFTagExpressionDefinition.from_raw(
        str(name),
        {
            "description": raw.get("Description"),
            "catalog_id": raw.get("CatalogId"),
            "expression": {
                item.get("TagKey"): item.get("TagValues", ())
                for item in expression
            },
        },
    )


def _grant_from_permission_item(item: Mapping[str, Any]) -> Optional[Grant]:
    principal = item.get("Principal", {}).get("DataLakePrincipalIdentifier")
    resource = from_lf_resource(item.get("Resource", {}))
    permissions = tuple(item.get("Permissions", ()))
    if not principal or resource is None or not permissions:
        return None
    return Grant(
        principal=principal,
        resource=resource,
        permissions=permissions,
        grantable_permissions=tuple(item.get("PermissionsWithGrantOption", ())),
    )


def _extract_resource_tags(response: Mapping[str, Any]) -> Dict[str, frozenset]:
    tags: Dict[str, set] = {}
    for key in ("LFTagOnDatabase", "LFTagsOnTable"):
        _merge_lf_tag_pairs(tags, response.get(key, ()))
    for column_tags in response.get("LFTagsOnColumns", ()):
        _merge_lf_tag_pairs(tags, column_tags.get("LFTags", ()))
    return {key: frozenset(values) for key, values in tags.items()}


def _merge_lf_tag_pairs(target: Dict[str, set], pairs: Iterable[Mapping[str, Any]]) -> None:
    for pair in pairs:
        key = pair.get("TagKey")
        values = pair.get("TagValues", ())
        if key and values:
            target.setdefault(str(key), set()).update(str(value) for value in values)


def _is_not_found(exc: Exception) -> bool:
    response = getattr(exc, "response", {})
    code = response.get("Error", {}).get("Code") if isinstance(response, Mapping) else None
    return code in {"EntityNotFoundException", "ResourceNotFoundException", "GlueEncryptionException"}


def _is_operation_not_pageable(exc: Exception) -> bool:
    if exc.__class__.__name__ in {"OperationNotPageableError", "PaginationError"}:
        return True
    return isinstance(exc, ValueError) and "Paginator for operation does not exist" in str(exc)
