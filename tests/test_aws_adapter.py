import unittest

from lakeformation_guard import DesiredState
from lakeformation_guard.aws import AWSLakeFormationAdapter, from_lf_resource, to_lf_resource
from lakeformation_guard.models import ResourceRef


class FakeLakeFormation:
    def __init__(self):
        self.calls = []

    def list_lf_tags(self, **kwargs):
        self.calls.append(("list_lf_tags", kwargs))
        return {"LFTags": [{"TagKey": "domain", "TagValues": ["sales"]}]}

    def list_lf_tag_expressions(self, **kwargs):
        self.calls.append(("list_lf_tag_expressions", kwargs))
        return {
            "LFTagExpressions": [
                {
                    "Name": "sales_tables",
                    "Description": "Sales tables",
                    "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
                }
            ]
        }

    def list_permissions(self, **kwargs):
        self.calls.append(("list_permissions", kwargs))
        return {
            "PrincipalResourcePermissions": [
                {
                    "Principal": {"DataLakePrincipalIdentifier": "role"},
                    "Resource": {"Database": {"Name": "analytics"}},
                    "Permissions": ["DESCRIBE"],
                }
            ]
        }

    def get_resource_lf_tags(self, **kwargs):
        self.calls.append(("get_resource_lf_tags", kwargs))
        return {"LFTagOnDatabase": [{"TagKey": "domain", "TagValues": ["sales"]}]}


class AwsAdapterTests(unittest.TestCase):
    def test_lf_tag_policy_resource_conversion(self):
        resource = ResourceRef.from_dict(
            {
                "kind": "lf_tag_policy",
                "resource_type": "TABLE",
                "expression": {"domain": ["sales"], "sensitivity": ["internal"]},
            }
        )

        self.assertEqual(
            to_lf_resource(resource),
            {
                "LFTagPolicy": {
                    "ResourceType": "TABLE",
                    "Expression": [
                        {"TagKey": "domain", "TagValues": ["sales"]},
                        {"TagKey": "sensitivity", "TagValues": ["internal"]},
                    ],
                }
            },
        )

    def test_lf_tag_policy_named_expression_resource_conversion(self):
        resource = ResourceRef.from_dict(
            {
                "kind": "lf_tag_policy",
                "resource_type": "TABLE",
                "expression_name": "sales_tables",
            }
        )

        self.assertEqual(
            to_lf_resource(resource),
            {"LFTagPolicy": {"ResourceType": "TABLE", "ExpressionName": "sales_tables"}},
        )

    def test_catalog_resource_conversion_preserves_catalog_id(self):
        resource = ResourceRef.from_dict({"kind": "catalog", "catalog_id": "222222222222"})

        self.assertEqual(to_lf_resource(resource), {"Catalog": {"Id": "222222222222"}})
        self.assertEqual(
            from_lf_resource({"Catalog": {"Id": "222222222222"}}),
            resource,
        )

    def test_resource_conversion_uses_fallback_catalog_id_when_response_omits_it(self):
        resource = from_lf_resource(
            {"Table": {"DatabaseName": "analytics", "Name": "orders"}},
            fallback_catalog_id="222222222222",
        )

        self.assertEqual(resource.catalog_id, "222222222222")

    def test_data_cells_filter_resource_conversion_preserves_table_catalog_id(self):
        resource = ResourceRef.from_dict(
            {
                "kind": "data_cells_filter",
                "catalog_id": "222222222222",
                "database": "analytics",
                "table": "orders",
                "filter_name": "orders_public",
            }
        )

        payload = {
            "DataCellsFilter": {
                "TableCatalogId": "222222222222",
                "DatabaseName": "analytics",
                "TableName": "orders",
                "Name": "orders_public",
            }
        }

        self.assertEqual(to_lf_resource(resource), payload)
        self.assertEqual(from_lf_resource(payload), resource)

    def test_table_with_columns_resource_conversion_preserves_column_wildcard(self):
        resource = ResourceRef.from_dict(
            {
                "kind": "table_with_columns",
                "catalog_id": "222222222222",
                "database": "analytics",
                "table": "orders",
                "column_wildcard": True,
                "excluded_columns": ["internal_notes"],
            }
        )
        payload = {
            "TableWithColumns": {
                "CatalogId": "222222222222",
                "DatabaseName": "analytics",
                "Name": "orders",
                "ColumnWildcard": {"ExcludedColumnNames": ["internal_notes"]},
            }
        }

        self.assertEqual(to_lf_resource(resource), payload)
        self.assertEqual(from_lf_resource(payload), resource)

    def test_import_grants_accepts_table_with_columns_column_wildcard(self):
        class Client:
            def list_permissions(self, **kwargs):
                return {
                    "PrincipalResourcePermissions": [
                        {
                            "Principal": {"DataLakePrincipalIdentifier": "role"},
                            "Resource": {
                                "TableWithColumns": {
                                    "DatabaseName": "analytics",
                                    "Name": "orders",
                                    "ColumnWildcard": {},
                                }
                            },
                            "Permissions": ["SELECT"],
                            "PermissionsWithGrantOption": [],
                        }
                    ]
                }

        state = AWSLakeFormationAdapter(Client()).import_state(include=("grants",))

        self.assertEqual(state.grants[0].resource.to_dict(), {
            "kind": "table_with_columns",
            "database": "analytics",
            "table": "orders",
            "column_wildcard": True,
        })

    def test_import_state_reads_lf_tags_expressions_grants_and_resource_tags(self):
        client = FakeLakeFormation()
        adapter = AWSLakeFormationAdapter(client)

        state = adapter.import_state(include=("lf-tags", "lf-tag-expressions", "resource-tags", "grants"))

        self.assertEqual(state.lf_tags[0].key, "domain")
        self.assertEqual(state.lf_tag_expressions[0].name, "sales_tables")
        self.assertEqual(state.grants[0].principal, "role")
        self.assertEqual(state.resource_tags[0].resource.database_name, "analytics")
        self.assertIn("list_lf_tags", [name for name, _ in client.calls])

    def test_import_state_preserves_adapter_catalog_id_when_responses_omit_it(self):
        client = FakeLakeFormation()
        adapter = AWSLakeFormationAdapter(client, catalog_id="222222222222")

        state = adapter.import_state(include=("lf-tags", "lf-tag-expressions", "resource-tags", "grants"))

        self.assertEqual(state.lf_tags[0].catalog_id, "222222222222")
        self.assertEqual(state.lf_tag_expressions[0].catalog_id, "222222222222")
        self.assertEqual(state.grants[0].resource.catalog_id, "222222222222")
        self.assertEqual(state.resource_tags[0].resource.catalog_id, "222222222222")

    def test_import_state_uses_grants_for_resource_tag_discovery_without_returning_grants(self):
        client = FakeLakeFormation()
        adapter = AWSLakeFormationAdapter(client)

        state = adapter.import_state(include=("resource-tags",))

        self.assertEqual(state.grants, ())
        self.assertEqual(state.resource_tags[0].resource.database_name, "analytics")
        self.assertEqual(
            [name for name, _ in client.calls],
            ["list_permissions", "get_resource_lf_tags"],
        )

    def test_import_resource_tags_ignores_non_taggable_grant_resources(self):
        class Client:
            def __init__(self):
                self.calls = []

            def list_permissions(self, **kwargs):
                self.calls.append(("list_permissions", kwargs))
                return {
                    "PrincipalResourcePermissions": [
                        {
                            "Principal": {"DataLakePrincipalIdentifier": "role"},
                            "Resource": {"Catalog": {}},
                            "Permissions": ["CREATE_DATABASE"],
                        },
                        {
                            "Principal": {"DataLakePrincipalIdentifier": "role"},
                            "Resource": {"DataLocation": {"ResourceArn": "arn:aws:s3:::lake/"}},
                            "Permissions": ["DATA_LOCATION_ACCESS"],
                        },
                        {
                            "Principal": {"DataLakePrincipalIdentifier": "role"},
                            "Resource": {"Database": {"Name": "analytics"}},
                            "Permissions": ["DESCRIBE"],
                        },
                    ]
                }

            def get_resource_lf_tags(self, **kwargs):
                self.calls.append(("get_resource_lf_tags", kwargs))
                return {"LFTagOnDatabase": [{"TagKey": "domain", "TagValues": ["sales"]}]}

        client = Client()
        state = AWSLakeFormationAdapter(client).import_state(include=("resource-tags",))

        self.assertEqual(len(state.resource_tags), 1)
        self.assertEqual(
            [name for name, _ in client.calls],
            ["list_permissions", "get_resource_lf_tags"],
        )

    def test_load_resource_tags_sorts_scoped_and_unscoped_resources_stably(self):
        desired = DesiredState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    },
                ]
            }
        )
        client = FakeLakeFormation()
        adapter = AWSLakeFormationAdapter(client)

        current = adapter.load_current_state_for(desired)

        self.assertEqual(len(current.resource_tags), 2)
        self.assertEqual(
            [name for name, _ in client.calls],
            ["get_resource_lf_tags", "get_resource_lf_tags"],
        )

if __name__ == "__main__":
    unittest.main()
