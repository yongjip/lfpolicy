import unittest

from lfpolicy import Change, DesiredState, boto3_kwargs_for
from lfpolicy.aws import AWSLakeFormationAdapter

try:
    import botocore.session
    from botocore.stub import Stubber
except ImportError:  # pragma: no cover - exercised only without test extras.
    botocore = None
    Stubber = None  # type: ignore[assignment]


CATALOG_ID = "111122223333"
PRINCIPAL = "arn:aws:iam::111122223333:role/DataConsumer"


@unittest.skipIf(Stubber is None, "botocore is required for AWS contract tests")
class AwsAdapterStubberTests(unittest.TestCase):
    def setUp(self):
        session = botocore.session.get_session()
        self.client = session.create_client(
            "lakeformation",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            aws_session_token="testing",
        )
        self.stubber = Stubber(self.client)
        self.stubber.activate()
        self.addCleanup(self.stubber.deactivate)

    def test_boto3_kwargs_for_uses_botocore_validated_request_shapes(self):
        changes = (
            Change(
                action="lf_tag.create",
                target="lf_tag:catalog=111122223333:key=domain",
                reason="missing LF-Tag",
                payload={"catalog_id": CATALOG_ID, "tag_key": "domain", "tag_values": ["sales"]},
            ),
            Change(
                action="lf_tag.add_values",
                target="lf_tag:catalog=111122223333:key=domain",
                reason="missing value",
                payload={"catalog_id": CATALOG_ID, "tag_key": "domain", "tag_values": ["finance"]},
            ),
            Change(
                action="lf_tag.remove_values",
                target="lf_tag:catalog=111122223333:key=domain",
                reason="extra value",
                payload={"catalog_id": CATALOG_ID, "tag_key": "domain", "tag_values": ["legacy"]},
                destructive=True,
            ),
            Change(
                action="lf_tag.delete",
                target="lf_tag:catalog=111122223333:key=legacy",
                reason="extra LF-Tag",
                payload={"catalog_id": CATALOG_ID, "tag_key": "legacy"},
                destructive=True,
            ),
            Change(
                action="lf_tag_expression.create",
                target="lf_tag_expression:catalog=111122223333:name=sales_tables",
                reason="missing expression",
                payload={
                    "catalog_id": CATALOG_ID,
                    "name": "sales_tables",
                    "description": "Sales tables",
                    "expression": [{"key": "domain", "values": ["sales"]}],
                },
            ),
            Change(
                action="lf_tag_expression.update",
                target="lf_tag_expression:catalog=111122223333:name=sales_tables",
                reason="expression drift",
                payload={
                    "catalog_id": CATALOG_ID,
                    "name": "sales_tables",
                    "expression": {"domain": ["finance"]},
                },
                destructive=True,
            ),
            Change(
                action="lf_tag_expression.delete",
                target="lf_tag_expression:catalog=111122223333:name=legacy",
                reason="extra expression",
                payload={"catalog_id": CATALOG_ID, "name": "legacy"},
                destructive=True,
            ),
            Change(
                action="data_cells_filter.create",
                target="data_cells_filter:catalog=111122223333:database=analytics:table=orders:name=orders_public",
                reason="missing filter",
                payload={
                    "catalog_id": CATALOG_ID,
                    "database": "analytics",
                    "table": "orders",
                    "name": "orders_public",
                    "row_filter": "country = 'US'",
                    "columns": ["order_id", "status"],
                },
            ),
            Change(
                action="data_cells_filter.update",
                target="data_cells_filter:catalog=111122223333:database=analytics:table=orders:name=orders_public",
                reason="filter drift",
                payload={
                    "catalog_id": CATALOG_ID,
                    "database": "analytics",
                    "table": "orders",
                    "name": "orders_public",
                    "all_rows": True,
                    "excluded_columns": ["notes"],
                    "version_id": "v1",
                },
                destructive=True,
            ),
            Change(
                action="data_cells_filter.delete",
                target="data_cells_filter:catalog=111122223333:database=analytics:table=orders:name=orders_legacy",
                reason="extra filter",
                payload={
                    "catalog_id": CATALOG_ID,
                    "database": "analytics",
                    "table": "orders",
                    "name": "orders_legacy",
                },
                destructive=True,
            ),
            Change(
                action="resource_tag.add_values",
                target="table:catalog=111122223333:database=analytics:table=orders",
                reason="missing assignment",
                payload={
                    "resource": {
                        "kind": "table",
                        "catalog_id": CATALOG_ID,
                        "database": "analytics",
                        "table": "orders",
                    },
                    "tags": {"domain": ["sales"]},
                },
            ),
            Change(
                action="resource_tag.remove_values",
                target="table:catalog=111122223333:database=analytics:table=orders",
                reason="extra assignment",
                payload={
                    "resource": {
                        "kind": "table",
                        "catalog_id": CATALOG_ID,
                        "database": "analytics",
                        "table": "orders",
                    },
                    "tags": {"domain": ["legacy"]},
                },
                destructive=True,
            ),
            Change(
                action="grant.add_permissions",
                target="principal -> table_with_columns",
                reason="missing column-wildcard permissions",
                payload={
                    "principal": PRINCIPAL,
                    "resource": {
                        "kind": "table_with_columns",
                        "catalog_id": CATALOG_ID,
                        "database": "analytics",
                        "table": "orders",
                        "column_wildcard": True,
                        "excluded_columns": ["internal_notes"],
                    },
                    "permissions": ["SELECT"],
                    "grantable_permissions": [],
                },
            ),
            Change(
                action="grant.revoke_permissions",
                target="principal -> lf_tag_expression",
                reason="extra expression stewardship",
                payload={
                    "principal": PRINCIPAL,
                    "resource": {
                        "kind": "lf_tag_expression",
                        "catalog_id": CATALOG_ID,
                        "expression_name": "sales_tables",
                    },
                    "permissions": ["GRANT_WITH_LF_TAG_EXPRESSION"],
                    "grantable_permissions": [],
                },
                destructive=True,
            ),
        )

        for change in changes:
            request = boto3_kwargs_for(change)
            self.stubber.add_response(request["method"], {}, request["kwargs"])
            getattr(self.client, request["method"])(**request["kwargs"])

        self.stubber.assert_no_pending_responses()

    def test_load_current_state_uses_scoped_inventory_requests_and_pagination(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    }
                ],
                "grants": [
                    {
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "table",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        self.stubber.add_response(
            "get_lf_tag",
            {"TagKey": "domain", "TagValues": ["sales"]},
            {"CatalogId": CATALOG_ID, "TagKey": "domain"},
        )
        self.stubber.add_response(
            "get_resource_lf_tags",
            {"LFTagsOnTable": [{"TagKey": "domain", "TagValues": ["sales"]}]},
            {
                "CatalogId": CATALOG_ID,
                "Resource": {
                    "Table": {
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "ShowAssignedLFTags": True,
            },
        )
        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {
                            "Table": {
                                "DatabaseName": "analytics",
                                "Name": "orders",
                            }
                        },
                        "Permissions": ["SELECT"],
                        "PermissionsWithGrantOption": [],
                    }
                ],
                "NextToken": "page-2",
            },
            {
                "CatalogId": CATALOG_ID,
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "Table": {
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "MaxResults": 100,
            },
        )
        self.stubber.add_response(
            "list_permissions",
            {"PrincipalResourcePermissions": []},
            {
                "CatalogId": CATALOG_ID,
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "Table": {
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "MaxResults": 100,
                "NextToken": "page-2",
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.lf_tags[0].to_dict(), {"key": "domain", "values": ["sales"]})
        self.assertEqual(
            current.resource_tags[0].to_dict(),
            {
                "resource": {
                    "kind": "table",
                    "database": "analytics",
                    "table": "orders",
                },
                "tags": {"domain": ["sales"]},
            },
        )
        self.assertEqual(current.grants[0].permissions, ("SELECT",))
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_falls_back_when_scoped_list_permissions_is_denied(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "table",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        resource = {
            "Table": {
                "DatabaseName": "analytics",
                "Name": "orders",
            }
        }

        self.stubber.add_response(
            "get_resource_lf_tags",
            {},
            {
                "CatalogId": CATALOG_ID,
                "Resource": resource,
                "ShowAssignedLFTags": True,
            },
        )
        self.stubber.add_client_error(
            "list_permissions",
            service_error_code="AccessDeniedException",
            service_message="Resource does not exist or requester is not authorized",
            expected_params={
                "CatalogId": CATALOG_ID,
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": resource,
                "MaxResults": 100,
            },
        )
        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": resource,
                        "Permissions": ["SELECT"],
                        "PermissionsWithGrantOption": [],
                    },
                    {
                        "Principal": {"DataLakePrincipalIdentifier": "other"},
                        "Resource": resource,
                        "Permissions": ["SELECT"],
                        "PermissionsWithGrantOption": [],
                    },
                ]
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(len(current.grants), 1)
        self.assertEqual(current.grants[0].principal, PRINCIPAL)
        self.assertEqual(current.grants[0].resource.to_dict(), {
            "kind": "table",
            "database": "analytics",
            "table": "orders",
        })
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_keeps_column_lf_tags_separate_from_table_tags(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        desired = DesiredState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    }
                ]
            }
        )

        self.stubber.add_response(
            "get_resource_lf_tags",
            {
                "LFTagsOnTable": [{"TagKey": "domain", "TagValues": ["sales"]}],
                "LFTagsOnColumns": [
                    {
                        "Name": "customer_id",
                        "LFTags": [{"TagKey": "pii", "TagValues": ["yes"]}],
                    }
                ],
            },
            {
                "CatalogId": "222222222222",
                "Resource": {
                    "Table": {
                        "CatalogId": "222222222222",
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "ShowAssignedLFTags": True,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(
            [assignment.to_dict() for assignment in current.resource_tags],
            [
                {
                    "resource": {
                        "kind": "table",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                    },
                    "tags": {"domain": ["sales"]},
                },
                {
                    "resource": {
                        "kind": "table_with_columns",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "columns": ["customer_id"],
                    },
                    "tags": {"pii": ["yes"]},
                },
            ],
        )
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_fetches_all_column_tags_for_column_wildcard_resource(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        desired = DesiredState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table_with_columns",
                            "database": "analytics",
                            "table": "orders",
                            "column_wildcard": True,
                        },
                        "tags": {"domain": ["sales"]},
                    }
                ]
            }
        )

        self.stubber.add_response(
            "get_resource_lf_tags",
            {
                "LFTagsOnTable": [{"TagKey": "domain", "TagValues": ["sales"]}],
                "LFTagsOnColumns": [
                    {
                        "Name": "email",
                        "LFTags": [{"TagKey": "sensitivity", "TagValues": ["restricted"]}],
                    }
                ],
            },
            {
                "CatalogId": CATALOG_ID,
                "Resource": {
                    "Table": {
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "ShowAssignedLFTags": True,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(
            [assignment.resource.to_dict() for assignment in current.resource_tags],
            [
                {
                    "kind": "table",
                    "database": "analytics",
                    "table": "orders",
                },
                {
                    "kind": "table_with_columns",
                    "database": "analytics",
                    "table": "orders",
                    "columns": ["email"],
                },
            ],
        )
        self.stubber.assert_no_pending_responses()

    def test_not_found_lf_tag_is_treated_as_absent_current_state(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        desired = DesiredState.from_dict({"lf_tags": {"domain": ["sales"]}})

        self.stubber.add_client_error(
            "get_lf_tag",
            service_error_code="EntityNotFoundException",
            expected_params={"CatalogId": CATALOG_ID, "TagKey": "domain"},
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.lf_tags, ())
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_fetches_lf_tags_by_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        desired = DesiredState.from_dict(
            {
                "lf_tags": [
                    {
                        "key": "domain",
                        "catalog_id": "222222222222",
                        "values": ["sales"],
                    }
                ]
            }
        )

        self.stubber.add_response(
            "get_lf_tag",
            {"CatalogId": "222222222222", "TagKey": "domain", "TagValues": ["sales"]},
            {"CatalogId": "222222222222", "TagKey": "domain"},
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.lf_tags[0].catalog_id, "222222222222")
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_fetches_lf_tag_expressions_by_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        desired = DesiredState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "222222222222",
                        "expression": {"domain": ["sales"]},
                    }
                ],
                "grants": [
                    {
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "333333333333",
                            "resource_type": "TABLE",
                            "expression_name": "grant_expression",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        self.stubber.add_response(
            "get_lf_tag_expression",
            {
                "Name": "shared",
                "CatalogId": "222222222222",
                "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
            },
            {"CatalogId": "222222222222", "Name": "shared"},
        )
        self.stubber.add_response(
            "get_lf_tag_expression",
            {
                "Name": "grant_expression",
                "CatalogId": "333333333333",
                "Expression": [{"TagKey": "domain", "TagValues": ["finance"]}],
            },
            {"CatalogId": "333333333333", "Name": "grant_expression"},
        )
        self.stubber.add_response(
            "list_permissions",
            {"PrincipalResourcePermissions": []},
            {
                "CatalogId": "333333333333",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "LFTagPolicy": {
                        "CatalogId": "333333333333",
                        "ResourceType": "TABLE",
                        "ExpressionName": "grant_expression",
                    }
                },
                "MaxResults": 100,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(
            {(expression.catalog_id, expression.name) for expression in current.lf_tag_expressions},
            {("222222222222", "shared"), ("333333333333", "grant_expression")},
        )
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_preserves_requested_catalog_for_expression_response_without_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client)
        desired = DesiredState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "222222222222",
                        "expression": {"domain": ["sales"]},
                    }
                ],
            }
        )

        self.stubber.add_response(
            "get_lf_tag_expression",
            {
                "Name": "shared",
                "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
            },
            {"CatalogId": "222222222222", "Name": "shared"},
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.lf_tag_expressions[0].catalog_id, "222222222222")
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_preserves_lf_tag_expression_grant_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "lf_tag_expression",
                            "catalog_id": "222222222222",
                            "expression_name": "sales_tables",
                        },
                        "permissions": ["DESCRIBE", "GRANT_WITH_LF_TAG_EXPRESSION"],
                    }
                ]
            }
        )

        self.stubber.add_response(
            "get_lf_tag_expression",
            {
                "Name": "sales_tables",
                "CatalogId": "222222222222",
                "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
            },
            {"CatalogId": "222222222222", "Name": "sales_tables"},
        )
        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {"LFTagExpression": {"Name": "sales_tables"}},
                        "Permissions": ["DESCRIBE", "GRANT_WITH_LF_TAG_EXPRESSION"],
                        "PermissionsWithGrantOption": [],
                    }
                ]
            },
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "LFTagExpression": {
                        "CatalogId": "222222222222",
                        "Name": "sales_tables",
                    }
                },
                "MaxResults": 100,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.lf_tag_expressions[0].catalog_id, "222222222222")
        self.assertEqual(
            current.grants[0].resource.to_dict(),
            {
                "kind": "lf_tag_expression",
                "catalog_id": "222222222222",
                "expression_name": "sales_tables",
            },
        )
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_preserves_catalog_id_for_catalog_grants(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "catalog",
                            "catalog_id": "222222222222",
                        },
                        "permissions": ["CREATE_DATABASE"],
                    }
                ]
            }
        )

        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {"Catalog": {"Id": "222222222222"}},
                        "Permissions": ["CREATE_DATABASE"],
                        "PermissionsWithGrantOption": [],
                    }
                ]
            },
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {"Catalog": {"Id": "222222222222"}},
                "MaxResults": 100,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.grants[0].resource.kind, "catalog")
        self.assertEqual(current.grants[0].resource.catalog_id, "222222222222")
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_preserves_requested_catalog_for_grant_response_without_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client)
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        self.stubber.add_response(
            "get_resource_lf_tags",
            {},
            {
                "CatalogId": "222222222222",
                "Resource": {
                    "Table": {
                        "CatalogId": "222222222222",
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "ShowAssignedLFTags": True,
            },
        )
        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {"Table": {"DatabaseName": "analytics", "Name": "orders"}},
                        "Permissions": ["SELECT"],
                        "PermissionsWithGrantOption": [],
                    }
                ]
            },
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "Table": {
                        "CatalogId": "222222222222",
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "MaxResults": 100,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.grants[0].resource.catalog_id, "222222222222")
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_preserves_data_location_grant_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "data_location",
                            "catalog_id": "222222222222",
                            "location": "arn:aws:s3:::analytics-lake/raw/",
                        },
                        "permissions": ["DATA_LOCATION_ACCESS"],
                    }
                ]
            }
        )
        resource = {
            "DataLocation": {
                "CatalogId": "222222222222",
                "ResourceArn": "arn:aws:s3:::analytics-lake/raw/",
            }
        }

        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {"DataLocation": {"ResourceArn": "arn:aws:s3:::analytics-lake/raw/"}},
                        "Permissions": ["DATA_LOCATION_ACCESS"],
                        "PermissionsWithGrantOption": [],
                    }
                ]
            },
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": resource,
                "MaxResults": 100,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(
            current.grants[0].resource.to_dict(),
            {
                "kind": "data_location",
                "catalog_id": "222222222222",
                "location": "arn:aws:s3:::analytics-lake/raw/",
            },
        )
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_preserves_data_cells_filter_grants(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        resource = {
            "DataCellsFilter": {
                "TableCatalogId": "222222222222",
                "DatabaseName": "analytics",
                "TableName": "orders",
                "Name": "orders_public",
            }
        }

        self.stubber.add_response(
            "get_data_cells_filter",
            {
                "DataCellsFilter": {
                    "TableCatalogId": "222222222222",
                    "DatabaseName": "analytics",
                    "TableName": "orders",
                    "Name": "orders_public",
                    "RowFilter": {"AllRowsWildcard": {}},
                    "ColumnNames": ["order_id", "status"],
                }
            },
            {
                "TableCatalogId": "222222222222",
                "DatabaseName": "analytics",
                "TableName": "orders",
                "Name": "orders_public",
            },
        )
        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": resource,
                        "Permissions": ["SELECT"],
                        "PermissionsWithGrantOption": [],
                    }
                ]
            },
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": resource,
                "MaxResults": 100,
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(
            current.grants[0].resource.to_dict(),
            {
                "kind": "data_cells_filter",
                "catalog_id": "222222222222",
                "database": "analytics",
                "table": "orders",
                "filter_name": "orders_public",
            },
        )
        self.assertEqual(
            current.data_cells_filters[0].to_dict(),
            {
                "name": "orders_public",
                "catalog_id": "222222222222",
                "database": "analytics",
                "table": "orders",
                "all_rows": True,
                "columns": ["order_id", "status"],
            },
        )
        self.stubber.assert_no_pending_responses()

    def test_import_data_cells_filters_discovers_tables_from_grants_without_returning_grants(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)

        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {
                            "Table": {
                                "CatalogId": CATALOG_ID,
                                "DatabaseName": "analytics",
                                "Name": "orders",
                            }
                        },
                        "Permissions": ["SELECT"],
                        "PermissionsWithGrantOption": [],
                    }
                ]
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
            },
        )
        self.stubber.add_response(
            "list_data_cells_filter",
            {
                "DataCellsFilters": [
                    {
                        "TableCatalogId": CATALOG_ID,
                        "DatabaseName": "analytics",
                        "TableName": "orders",
                        "Name": "orders_public",
                        "RowFilter": {"FilterExpression": "country = 'US'"},
                        "ColumnWildcard": {"ExcludedColumnNames": ["notes"]},
                    }
                ]
            },
            {
                "Table": {
                    "CatalogId": CATALOG_ID,
                    "DatabaseName": "analytics",
                    "Name": "orders",
                },
                "MaxResults": 100,
            },
        )

        current = adapter.import_state(include=("data-cells-filters",))

        self.assertEqual(current.grants, ())
        self.assertEqual(
            current.data_cells_filters[0].to_dict(),
            {
                "name": "orders_public",
                "catalog_id": CATALOG_ID,
                "database": "analytics",
                "table": "orders",
                "row_filter": "country = 'US'",
                "excluded_columns": ["notes"],
            },
        )
        self.stubber.assert_no_pending_responses()

    def test_list_data_cells_filters_scopes_one_table_paginates_and_sorts(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        explicit_catalog_id = "222222222222"
        request = {
            "Table": {
                "CatalogId": explicit_catalog_id,
                "DatabaseName": "analytics",
                "Name": "orders",
            },
            "MaxResults": 100,
        }
        self.stubber.add_response(
            "list_data_cells_filter",
            {
                "DataCellsFilters": [
                    {
                        "TableCatalogId": explicit_catalog_id,
                        "DatabaseName": "analytics",
                        "TableName": "orders",
                        "Name": "orders_restricted",
                        "RowFilter": {"FilterExpression": "region = 'KR'"},
                        "ColumnNames": ["order_id"],
                    }
                ],
                "NextToken": "page-2",
            },
            request,
        )
        self.stubber.add_response(
            "list_data_cells_filter",
            {
                "DataCellsFilters": [
                    {
                        "TableCatalogId": explicit_catalog_id,
                        "DatabaseName": "analytics",
                        "TableName": "orders",
                        "Name": "orders_all",
                        "RowFilter": {"AllRowsWildcard": {}},
                        "ColumnWildcard": {"ExcludedColumnNames": ["notes"]},
                    }
                ]
            },
            {**request, "NextToken": "page-2"},
        )

        filters = adapter.list_data_cells_filters(
            "analytics",
            "orders",
            catalog_id=explicit_catalog_id,
        )

        self.assertEqual(
            [definition.to_dict() for definition in filters],
            [
                {
                    "name": "orders_all",
                    "catalog_id": explicit_catalog_id,
                    "database": "analytics",
                    "table": "orders",
                    "all_rows": True,
                    "excluded_columns": ["notes"],
                },
                {
                    "name": "orders_restricted",
                    "catalog_id": explicit_catalog_id,
                    "database": "analytics",
                    "table": "orders",
                    "row_filter": "region = 'KR'",
                    "columns": ["order_id"],
                },
            ],
        )
        self.stubber.assert_no_pending_responses()

    def test_list_data_cells_filters_uses_adapter_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        self.stubber.add_response(
            "list_data_cells_filter",
            {"DataCellsFilters": []},
            {
                "Table": {
                    "CatalogId": CATALOG_ID,
                    "DatabaseName": "analytics",
                    "Name": "orders",
                },
                "MaxResults": 100,
            },
        )

        filters = adapter.list_data_cells_filters("analytics", "orders")

        self.assertEqual(filters, ())
        self.stubber.assert_no_pending_responses()

    def test_import_grants_preserves_table_with_columns_column_wildcard(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)

        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {
                            "TableWithColumns": {
                                "CatalogId": CATALOG_ID,
                                "DatabaseName": "analytics",
                                "Name": "orders",
                                "ColumnWildcard": {},
                            }
                        },
                        "Permissions": ["SELECT"],
                        "PermissionsWithGrantOption": [],
                    }
                ]
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
            },
        )

        current = adapter.import_state(include=("grants",))

        self.assertEqual(
            current.grants[0].resource.to_dict(),
            {
                "kind": "table_with_columns",
                "catalog_id": CATALOG_ID,
                "database": "analytics",
                "table": "orders",
                "column_wildcard": True,
            },
        )
        self.stubber.assert_no_pending_responses()

    def test_import_resource_tags_discovers_resources_from_grants_without_returning_grants(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)

        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {"Database": {"Name": "analytics"}},
                        "Permissions": ["DESCRIBE"],
                        "PermissionsWithGrantOption": [],
                    }
                ]
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
            },
        )
        self.stubber.add_response(
            "get_resource_lf_tags",
            {
                "LFTagOnDatabase": [{"TagKey": "domain", "TagValues": ["sales"]}],
            },
            {
                "CatalogId": CATALOG_ID,
                "Resource": {
                    "Database": {
                        "CatalogId": CATALOG_ID,
                        "Name": "analytics",
                    }
                },
                "ShowAssignedLFTags": True,
            },
        )

        current = adapter.import_state(include=("resource-tags",))

        self.assertEqual(current.grants, ())
        self.assertEqual(
            current.resource_tags[0].to_dict(),
            {
                "resource": {
                    "kind": "database",
                    "catalog_id": CATALOG_ID,
                    "database": "analytics",
                },
                "tags": {"domain": ["sales"]},
            },
        )
        self.stubber.assert_no_pending_responses()

    def test_import_lf_tags_and_expressions_handles_manual_pagination(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)

        self.stubber.add_response(
            "list_lf_tags",
            {
                "LFTags": [
                    {
                        "CatalogId": CATALOG_ID,
                        "TagKey": "domain",
                        "TagValues": ["sales"],
                    }
                ],
                "NextToken": "tags-page-2",
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
            },
        )
        self.stubber.add_response(
            "list_lf_tags",
            {
                "LFTags": [
                    {
                        "CatalogId": CATALOG_ID,
                        "TagKey": "sensitivity",
                        "TagValues": ["internal"],
                    }
                ]
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
                "NextToken": "tags-page-2",
            },
        )
        self.stubber.add_response(
            "list_lf_tag_expressions",
            {
                "LFTagExpressions": [
                    {
                        "CatalogId": CATALOG_ID,
                        "Name": "sales_tables",
                        "Description": "Sales tables",
                        "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
                    }
                ],
                "NextToken": "expressions-page-2",
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
            },
        )
        self.stubber.add_response(
            "list_lf_tag_expressions",
            {
                "LFTagExpressions": [
                    {
                        "CatalogId": CATALOG_ID,
                        "Name": "internal_tables",
                        "Expression": [{"TagKey": "sensitivity", "TagValues": ["internal"]}],
                    }
                ]
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
                "NextToken": "expressions-page-2",
            },
        )

        current = adapter.import_state(include=("lf-tags", "lf-tag-expressions"))

        self.assertEqual(
            [(tag.catalog_id, tag.key, tag.values) for tag in current.lf_tags],
            [
                (CATALOG_ID, "domain", ("sales",)),
                (CATALOG_ID, "sensitivity", ("internal",)),
            ],
        )
        self.assertEqual(
            [(expression.catalog_id, expression.name) for expression in current.lf_tag_expressions],
            [(CATALOG_ID, "sales_tables"), (CATALOG_ID, "internal_tables")],
        )
        self.stubber.assert_no_pending_responses()

    def test_load_current_state_treats_missing_lf_tag_expression_and_data_cells_filter_as_absent(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        desired = DesiredState.from_dict(
            {
                "lf_tag_expressions": {
                    "sales_tables": {"expression": {"domain": ["sales"]}}
                },
                "data_cells_filters": [
                    {
                        "name": "orders_public",
                        "catalog_id": CATALOG_ID,
                        "database": "analytics",
                        "table": "orders",
                        "all_rows": True,
                    }
                ],
            }
        )

        self.stubber.add_client_error(
            "get_lf_tag_expression",
            service_error_code="EntityNotFoundException",
            expected_params={"CatalogId": CATALOG_ID, "Name": "sales_tables"},
        )
        self.stubber.add_client_error(
            "get_data_cells_filter",
            service_error_code="EntityNotFoundException",
            expected_params={
                "TableCatalogId": CATALOG_ID,
                "DatabaseName": "analytics",
                "TableName": "orders",
                "Name": "orders_public",
            },
        )

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.lf_tag_expressions, ())
        self.assertEqual(current.data_cells_filters, ())
        self.stubber.assert_no_pending_responses()

    def test_import_grants_skips_permission_items_without_principal_resource_or_permissions(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)

        self.stubber.add_response(
            "list_permissions",
            {
                "PrincipalResourcePermissions": [
                    {
                        "Resource": {"Database": {"CatalogId": CATALOG_ID, "Name": "analytics"}},
                        "Permissions": ["DESCRIBE"],
                    },
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {},
                        "Permissions": ["DESCRIBE"],
                    },
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {"Database": {"CatalogId": CATALOG_ID, "Name": "analytics"}},
                        "Permissions": [],
                    },
                    {
                        "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                        "Resource": {"Database": {"CatalogId": CATALOG_ID, "Name": "analytics"}},
                        "Permissions": ["DESCRIBE"],
                        "PermissionsWithGrantOption": [],
                    },
                ]
            },
            {
                "CatalogId": CATALOG_ID,
                "MaxResults": 100,
            },
        )

        current = adapter.import_state(include=("grants",))

        self.assertEqual(len(current.grants), 1)
        self.assertEqual(current.grants[0].principal, PRINCIPAL)
        self.assertEqual(current.grants[0].resource.catalog_id, CATALOG_ID)
        self.stubber.assert_no_pending_responses()

if __name__ == "__main__":
    unittest.main()
