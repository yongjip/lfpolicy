"""Stateless Lake Formation request-shape evidence for planned changes."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Union

from .models import DataCellsFilterDefinition, ResourceRef
from .planner import Change


ChangeLike = Union[Change, Mapping[str, Any]]


def boto3_kwargs_for(change: ChangeLike) -> Dict[str, Any]:
    """Return inert boto3 Lake Formation request evidence for a plan change.

    The return value is a data payload shaped as ``{"method": str, "kwargs": dict}``.
    This function constructs no boto3 client, performs no AWS call, and owns no
    retry, rollback, credential, approval, or IAM behavior.
    """

    change_obj = _coerce_change(change)
    method = change_obj.aws_api
    if method is None:
        raise ValueError("Unsupported change action: {}".format(change_obj.action))
    return {"method": method, "kwargs": _boto3_kwargs_for_change(change_obj)}


def _coerce_change(change: ChangeLike) -> Change:
    if isinstance(change, Change):
        return change
    if isinstance(change, Mapping):
        return Change.from_dict(change)
    raise ValueError("change must be a Change or plan change mapping")


def _boto3_kwargs_for_change(change: Change) -> Dict[str, Any]:
    action = change.action
    payload = dict(change.payload)
    if action == "lf_tag.create":
        return _with_payload_catalog_id(
            {
                "catalog_id": payload.get("catalog_id"),
                "TagKey": payload["tag_key"],
                "TagValues": list(payload.get("tag_values", ())),
            }
        )
    if action == "lf_tag.add_values":
        return _with_payload_catalog_id(
            {
                "catalog_id": payload.get("catalog_id"),
                "TagKey": payload["tag_key"],
                "TagValuesToAdd": list(payload.get("tag_values", ())),
            }
        )
    if action == "lf_tag.remove_values":
        return _with_payload_catalog_id(
            {
                "catalog_id": payload.get("catalog_id"),
                "TagKey": payload["tag_key"],
                "TagValuesToDelete": list(payload.get("tag_values", ())),
            }
        )
    if action == "lf_tag.delete":
        return _with_payload_catalog_id(
            {
                "catalog_id": payload.get("catalog_id"),
                "TagKey": payload["tag_key"],
            }
        )
    if action == "lf_tag_expression.create":
        return _lf_tag_expression_kwargs(payload)
    if action == "lf_tag_expression.update":
        return _lf_tag_expression_kwargs(payload)
    if action == "lf_tag_expression.delete":
        return _with_payload_catalog_id(
            {
                "Name": payload["name"],
                "catalog_id": payload.get("catalog_id"),
            }
        )
    if action == "data_cells_filter.create":
        definition = DataCellsFilterDefinition.from_dict(payload)
        return {"TableData": _data_cells_filter_table_data(definition)}
    if action == "data_cells_filter.update":
        definition = DataCellsFilterDefinition.from_dict(payload)
        return {"TableData": _data_cells_filter_table_data(definition)}
    if action == "data_cells_filter.delete":
        definition = DataCellsFilterDefinition.from_dict(payload)
        return _data_cells_filter_get_request(
            catalog_id=definition.catalog_id,
            database_name=definition.database_name,
            table_name=definition.table_name,
            name=definition.name,
        )
    if action == "resource_tag.add_values":
        return _resource_tag_kwargs(payload)
    if action == "resource_tag.remove_values":
        return _resource_tag_kwargs(payload)
    if action == "grant.add_permissions":
        return _grant_kwargs(payload)
    if action == "grant.revoke_permissions":
        return _grant_kwargs(payload)
    raise ValueError("Unsupported change action: {}".format(action))


def _lf_tag_expression_kwargs(payload: Mapping[str, Any]) -> Dict[str, Any]:
    return _with_payload_catalog_id(
        {
            "Name": payload["name"],
            "Description": payload.get("description", ""),
            "Expression": _expression_pairs(payload["expression"]),
            "catalog_id": payload.get("catalog_id"),
        }
    )


def _resource_tag_kwargs(payload: Mapping[str, Any]) -> Dict[str, Any]:
    resource = ResourceRef.from_dict(payload["resource"])
    return _with_payload_catalog_id(
        {
            "catalog_id": resource.catalog_id,
            "Resource": _to_lf_resource(resource),
            "LFTags": _lf_tag_pairs(payload["tags"], catalog_id=resource.catalog_id),
        }
    )


def _grant_kwargs(payload: Mapping[str, Any]) -> Dict[str, Any]:
    resource = ResourceRef.from_dict(payload["resource"])
    return _with_payload_catalog_id(
        {
            "catalog_id": resource.catalog_id,
            "Principal": {"DataLakePrincipalIdentifier": payload["principal"]},
            "Resource": _to_lf_resource(resource),
            "Permissions": list(payload.get("permissions", ())),
            "PermissionsWithGrantOption": list(payload.get("grantable_permissions", ())),
        }
    )


def _to_lf_resource(resource: ResourceRef) -> Dict[str, Any]:
    from .aws import to_lf_resource

    return to_lf_resource(resource)


def _with_payload_catalog_id(kwargs: Mapping[str, Any]) -> Dict[str, Any]:
    request = dict(kwargs)
    payload_catalog_id = request.pop("catalog_id", None)
    if payload_catalog_id:
        request.setdefault("CatalogId", payload_catalog_id)
    return {key: value for key, value in request.items() if value not in (None, "")}


def _lf_tag_pairs(
    tags: Mapping[str, Iterable[str]],
    *,
    catalog_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    pairs = []
    for key, values in sorted(tags.items()):
        pair: Dict[str, Any] = {"TagKey": key, "TagValues": list(values)}
        if catalog_id:
            pair["CatalogId"] = catalog_id
        pairs.append(pair)
    return pairs


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


def _data_cells_filter_get_request(
    *,
    catalog_id: Optional[str],
    database_name: str,
    table_name: str,
    name: str,
) -> Dict[str, Any]:
    request = {
        "TableCatalogId": catalog_id,
        "DatabaseName": database_name,
        "TableName": table_name,
        "Name": name,
    }
    return {key: value for key, value in request.items() if value not in (None, "")}


def _data_cells_filter_table_data(definition: DataCellsFilterDefinition) -> Dict[str, Any]:
    table_data: Dict[str, Any] = {
        "TableCatalogId": definition.catalog_id,
        "DatabaseName": definition.database_name,
        "TableName": definition.table_name,
        "Name": definition.name,
    }
    if definition.row_filter:
        table_data["RowFilter"] = {"FilterExpression": definition.row_filter}
    elif definition.all_rows:
        table_data["RowFilter"] = {"AllRowsWildcard": {}}
    if definition.columns:
        table_data["ColumnNames"] = list(definition.columns)
    elif definition.excluded_columns:
        table_data["ColumnWildcard"] = {"ExcludedColumnNames": list(definition.excluded_columns)}
    if definition.version_id:
        table_data["VersionId"] = definition.version_id
    return {key: value for key, value in table_data.items() if value not in (None, "")}
