"""JSON Schema helpers for guardrail state files."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


_STRING_VALUE = {"type": "string", "minLength": 1}
_VALUE_LIST = {
    "oneOf": [
        _STRING_VALUE,
        {
            "type": "array",
            "items": _STRING_VALUE,
            "minItems": 1,
            "uniqueItems": True,
        },
    ]
}

STATE_JSON_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://raw.githubusercontent.com/yongjip/aws-datalake-guard/main/docs/schema.json",
    "title": "lfguard state",
    "description": "Desired or current AWS Lake Formation LF-Tag guardrail state.",
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "lf_tags": {
            "description": "LF-Tag keys and allowed values.",
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": {
                        "oneOf": [
                            _VALUE_LIST,
                            {"$ref": "#/$defs/lfTagDefinitionValue"},
                        ]
                    },
                },
                {
                    "type": "array",
                    "items": {"$ref": "#/$defs/lfTagDefinition"},
                },
            ],
        },
        "lf_tag_key_metadata": {
            "description": "Optional authoring metadata for LF-Tag assignment scope.",
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/lfTagKeyMetadataValue"},
                },
                {
                    "type": "array",
                    "items": {"$ref": "#/$defs/lfTagKeyMetadata"},
                },
            ],
        },
        "lf_tag_expressions": {
            "description": "Named LF-Tag expressions.",
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": {"$ref": "#/$defs/lfTagExpressionValue"},
                },
                {
                    "type": "array",
                    "items": {"$ref": "#/$defs/lfTagExpression"},
                },
            ],
        },
        "data_cells_filters": {
            "type": "array",
            "items": {"$ref": "#/$defs/dataCellsFilterDefinition"},
        },
        "resource_tags": {
            "type": "array",
            "items": {"$ref": "#/$defs/resourceTagAssignment"},
        },
        "grants": {
            "type": "array",
            "items": {"$ref": "#/$defs/grant"},
        },
        "lint": {
            "type": "object",
            "additionalProperties": {"enum": ["error", "warning", "ignore"]},
        },
        "ownership": {"$ref": "#/$defs/ownershipConfig"},
        "ignore": {"$ref": "#/$defs/ignoreConfig"},
        "exceptions": {
            "type": "array",
            "items": {"$ref": "#/$defs/policyException"},
        },
    },
    "$defs": {
        "lfTagDefinition": {
            "type": "object",
            "additionalProperties": False,
            "required": ["key", "values"],
            "properties": {
                "key": _STRING_VALUE,
                "catalog_id": _STRING_VALUE,
                "values": _VALUE_LIST,
            },
        },
        "lfTagDefinitionValue": {
            "type": "object",
            "additionalProperties": False,
            "required": ["values"],
            "properties": {
                "catalog_id": _STRING_VALUE,
                "values": _VALUE_LIST,
            },
        },
        "lfTagKeyMetadata": {
            "type": "object",
            "additionalProperties": False,
            "required": ["key", "assignable_to"],
            "properties": {
                "key": _STRING_VALUE,
                "catalog_id": _STRING_VALUE,
                "assignable_to": {"$ref": "#/$defs/tagAssignmentScopeList"},
            },
        },
        "lfTagKeyMetadataValue": {
            "type": "object",
            "additionalProperties": False,
            "required": ["assignable_to"],
            "properties": {
                "catalog_id": _STRING_VALUE,
                "assignable_to": {"$ref": "#/$defs/tagAssignmentScopeList"},
            },
        },
        "lfTagExpression": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "expression"],
            "properties": {
                "name": _STRING_VALUE,
                "description": {"type": "string"},
                "catalog_id": _STRING_VALUE,
                "expression": {"$ref": "#/$defs/lfTagExpressionBody"},
            },
        },
        "lfTagExpressionValue": {
            "type": "object",
            "additionalProperties": False,
            "required": ["expression"],
            "properties": {
                "description": {"type": "string"},
                "catalog_id": _STRING_VALUE,
                "expression": {"$ref": "#/$defs/lfTagExpressionBody"},
            },
        },
        "lfTagExpressionBody": {
            "oneOf": [
                {
                    "type": "object",
                    "additionalProperties": _VALUE_LIST,
                },
                {
                    "type": "array",
                    "items": {"$ref": "#/$defs/lfTagExpressionItem"},
                    "minItems": 1,
                },
            ],
        },
        "lfTagExpressionItem": {
            "type": "object",
            "additionalProperties": False,
            "required": ["key", "values"],
            "properties": {
                "key": _STRING_VALUE,
                "values": _VALUE_LIST,
            },
        },
        "dataCellsFilterDefinition": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "database", "table"],
            "properties": {
                "name": _STRING_VALUE,
                "catalog_id": _STRING_VALUE,
                "database": _STRING_VALUE,
                "table": _STRING_VALUE,
                "row_filter": _STRING_VALUE,
                "all_rows": {"type": "boolean"},
                "columns": {
                    "type": "array",
                    "items": _STRING_VALUE,
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "excluded_columns": {
                    "type": "array",
                    "items": _STRING_VALUE,
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "version_id": _STRING_VALUE,
            },
            "not": {
                "anyOf": [
                    {"required": ["row_filter", "all_rows"]},
                    {"required": ["columns", "excluded_columns"]},
                ]
            },
        },
        "tagAssignmentScopeList": {
            "oneOf": [
                {"enum": ["database", "table", "column"]},
                {
                    "type": "array",
                    "items": {"enum": ["database", "table", "column"]},
                    "minItems": 1,
                    "uniqueItems": True,
                },
            ],
        },
        "resourceTagAssignment": {
            "type": "object",
            "additionalProperties": False,
            "required": ["resource", "tags"],
            "properties": {
                "resource": {"$ref": "#/$defs/resource"},
                "tags": {
                    "type": "object",
                    "additionalProperties": _VALUE_LIST,
                },
            },
        },
        "grant": {
            "type": "object",
            "additionalProperties": False,
            "required": ["principal", "resource", "permissions"],
            "properties": {
                "principal": _STRING_VALUE,
                "resource": {"$ref": "#/$defs/resource"},
                "permissions": _VALUE_LIST,
                "grantable_permissions": _VALUE_LIST,
            },
        },
        "resource": {
            "oneOf": [
                {"$ref": "#/$defs/catalogResource"},
                {"$ref": "#/$defs/databaseResource"},
                {"$ref": "#/$defs/tableResource"},
                {"$ref": "#/$defs/tableWithColumnsResource"},
                {"$ref": "#/$defs/dataLocationResource"},
                {"$ref": "#/$defs/dataCellsFilterResource"},
                {"$ref": "#/$defs/lfTagPolicyResource"},
                {"$ref": "#/$defs/lfTagExpressionResource"},
            ],
        },
        "catalogResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind"],
            "properties": {
                "kind": {"const": "catalog"},
                "catalog_id": _STRING_VALUE,
            },
        },
        "databaseResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "database"],
            "properties": {
                "kind": {"const": "database"},
                "catalog_id": _STRING_VALUE,
                "database": _STRING_VALUE,
            },
        },
        "tableResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "database", "table"],
            "properties": {
                "kind": {"const": "table"},
                "catalog_id": _STRING_VALUE,
                "database": _STRING_VALUE,
                "table": _STRING_VALUE,
            },
        },
        "tableWithColumnsResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "database", "table"],
            "anyOf": [
                {"required": ["columns"]},
                {"required": ["column_wildcard"]},
                {"required": ["excluded_columns"]},
            ],
            "not": {
                "anyOf": [
                    {"required": ["columns", "column_wildcard"]},
                    {"required": ["columns", "excluded_columns"]},
                ]
            },
            "properties": {
                "kind": {"const": "table_with_columns"},
                "catalog_id": _STRING_VALUE,
                "database": _STRING_VALUE,
                "table": _STRING_VALUE,
                "column_wildcard": {"type": "boolean"},
                "columns": {
                    "type": "array",
                    "items": _STRING_VALUE,
                    "minItems": 1,
                    "uniqueItems": True,
                },
                "excluded_columns": {
                    "type": "array",
                    "items": _STRING_VALUE,
                    "minItems": 1,
                    "uniqueItems": True,
                },
            },
        },
        "dataLocationResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "location"],
            "properties": {
                "kind": {"const": "data_location"},
                "catalog_id": _STRING_VALUE,
                "location": _STRING_VALUE,
            },
        },
        "dataCellsFilterResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "database", "table", "filter_name"],
            "properties": {
                "kind": {"const": "data_cells_filter"},
                "catalog_id": _STRING_VALUE,
                "database": _STRING_VALUE,
                "table": _STRING_VALUE,
                "filter_name": _STRING_VALUE,
            },
        },
        "lfTagPolicyResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "resource_type"],
            "properties": {
                "kind": {"const": "lf_tag_policy"},
                "catalog_id": _STRING_VALUE,
                "resource_type": {"enum": ["DATABASE", "TABLE"]},
                "expression": {"$ref": "#/$defs/lfTagExpressionBody"},
                "expression_name": _STRING_VALUE,
            },
            "oneOf": [
                {"required": ["expression"]},
                {"required": ["expression_name"]},
            ],
        },
        "lfTagExpressionResource": {
            "type": "object",
            "additionalProperties": False,
            "required": ["kind", "expression_name"],
            "properties": {
                "kind": {"const": "lf_tag_expression"},
                "catalog_id": _STRING_VALUE,
                "expression_name": _STRING_VALUE,
            },
        },
        "ownershipConfig": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "managed_principals": {
                    "type": "array",
                    "items": _STRING_VALUE,
                    "uniqueItems": True,
                },
                "managed_resources": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/resourcePattern"},
                },
                "unmanaged_action": {"enum": ["warn", "warning", "error", "ignore"]},
            },
        },
        "ignoreConfig": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "principals": {
                    "type": "array",
                    "items": _STRING_VALUE,
                    "uniqueItems": True,
                },
                "resources": {
                    "type": "array",
                    "items": {"$ref": "#/$defs/resourcePattern"},
                },
            },
        },
        "policyException": {
            "type": "object",
            "additionalProperties": False,
            "required": ["principal", "rules", "reason", "ticket", "expires_at", "approved_by", "owner"],
            "properties": {
                "principal": _STRING_VALUE,
                "resource": {"$ref": "#/$defs/resourcePattern"},
                "permissions": _VALUE_LIST,
                "rules": {
                    "oneOf": [
                        {"$ref": "#/$defs/exceptionRule"},
                        {
                            "type": "array",
                            "items": {"$ref": "#/$defs/exceptionRule"},
                            "minItems": 1,
                            "uniqueItems": True,
                        },
                    ],
                },
                "reason": _STRING_VALUE,
                "ticket": _STRING_VALUE,
                "expires_at": {"type": "string", "format": "date"},
                "approved_by": _STRING_VALUE,
                "owner": _STRING_VALUE,
            },
        },
        "exceptionRule": {
            "enum": [
                "allow_broad_principals",
                "allow_broad_principal",
                "allow_broad_permissions",
                "allow_mutating_permissions",
                "allow_grantable_permissions",
                "allow_named_resource_grants",
                "allow_named_resource_grant",
                "allow_lf_tag_policy_select_mutation",
                "allow_column_filter_mutation",
            ]
        },
        "resourcePattern": {
            "oneOf": [
                _STRING_VALUE,
                {
                    "type": "object",
                    "minProperties": 1,
                    "additionalProperties": False,
                    "properties": {
                        "kind": {
                            "enum": [
                                "catalog",
                                "database",
                                "table",
                                "table_with_columns",
                                "data_location",
                                "data_cells_filter",
                                "lf_tag_policy",
                                "lf_tag_expression",
                            ]
                        },
                        "catalog_id": _STRING_VALUE,
                        "database": _STRING_VALUE,
                        "table": _STRING_VALUE,
                        "location": _STRING_VALUE,
                        "expression_name": _STRING_VALUE,
                        "filter_name": _STRING_VALUE,
                    },
                },
            ],
        },
    },
}


def state_json_schema() -> Dict[str, Any]:
    """Return a JSON Schema for desired/current state files."""

    return deepcopy(STATE_JSON_SCHEMA)
