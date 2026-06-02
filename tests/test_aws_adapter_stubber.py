import unittest

from lakeformation_guard import Change, DesiredState, Plan
from lakeformation_guard.aws import AWSLakeFormationAdapter

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

    def test_apply_uses_botocore_validated_request_shapes_for_all_actions(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        change_plan = Plan(
            (
                Change(
                    action="lf_tag.create",
                    target="lf_tag:domain",
                    reason="missing LF-Tag",
                    payload={"tag_key": "domain", "tag_values": ["sales", "finance"]},
                ),
                Change(
                    action="lf_tag.add_values",
                    target="lf_tag:domain",
                    reason="missing value",
                    payload={"tag_key": "domain", "tag_values": ["marketing"]},
                ),
                Change(
                    action="lf_tag.remove_values",
                    target="lf_tag:domain",
                    reason="extra value",
                    payload={"tag_key": "domain", "tag_values": ["legacy"]},
                    destructive=True,
                ),
                Change(
                    action="resource_tag.add_values",
                    target="table:database=analytics:table=orders",
                    reason="missing assignment",
                    payload={
                        "resource": {
                            "kind": "table",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    },
                ),
                Change(
                    action="resource_tag.remove_values",
                    target="table:database=analytics:table=orders",
                    reason="extra assignment",
                    payload={
                        "resource": {
                            "kind": "table",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["legacy"]},
                    },
                    destructive=True,
                ),
                Change(
                    action="grant.add_permissions",
                    target="principal -> lf_tag_policy",
                    reason="missing permissions",
                    payload={
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"]},
                        },
                        "permissions": ["DESCRIBE", "SELECT"],
                        "grantable_permissions": [],
                    },
                ),
                Change(
                    action="grant.revoke_permissions",
                    target="principal -> lf_tag_policy",
                    reason="extra permissions",
                    payload={
                        "principal": PRINCIPAL,
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["legacy"]},
                        },
                        "permissions": ["SELECT"],
                        "grantable_permissions": [],
                    },
                    destructive=True,
                ),
            )
        )

        self.stubber.add_response(
            "create_lf_tag",
            {},
            {
                "CatalogId": CATALOG_ID,
                "TagKey": "domain",
                "TagValues": ["sales", "finance"],
            },
        )
        self.stubber.add_response(
            "update_lf_tag",
            {},
            {
                "CatalogId": CATALOG_ID,
                "TagKey": "domain",
                "TagValuesToAdd": ["marketing"],
            },
        )
        self.stubber.add_response(
            "update_lf_tag",
            {},
            {
                "CatalogId": CATALOG_ID,
                "TagKey": "domain",
                "TagValuesToDelete": ["legacy"],
            },
        )
        self.stubber.add_response(
            "add_lf_tags_to_resource",
            {},
            {
                "CatalogId": CATALOG_ID,
                "Resource": {
                    "Table": {
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "LFTags": [{"TagKey": "domain", "TagValues": ["sales"]}],
            },
        )
        self.stubber.add_response(
            "remove_lf_tags_from_resource",
            {},
            {
                "CatalogId": CATALOG_ID,
                "Resource": {
                    "Table": {
                        "DatabaseName": "analytics",
                        "Name": "orders",
                    }
                },
                "LFTags": [{"TagKey": "domain", "TagValues": ["legacy"]}],
            },
        )
        self.stubber.add_response(
            "grant_permissions",
            {},
            {
                "CatalogId": CATALOG_ID,
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "LFTagPolicy": {
                        "ResourceType": "TABLE",
                        "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
                    }
                },
                "Permissions": ["DESCRIBE", "SELECT"],
                "PermissionsWithGrantOption": [],
            },
        )
        self.stubber.add_response(
            "revoke_permissions",
            {},
            {
                "CatalogId": CATALOG_ID,
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "LFTagPolicy": {
                        "ResourceType": "TABLE",
                        "Expression": [{"TagKey": "domain", "TagValues": ["legacy"]}],
                    }
                },
                "Permissions": ["SELECT"],
                "PermissionsWithGrantOption": [],
            },
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(len(results), 7)
        self.assertTrue(all(result.applied for result in results))
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

    def test_apply_lf_tag_payload_catalog_id_overrides_adapter_default(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "lf_tag.create",
                        "target": "lf_tag:catalog=222222222222:key=domain",
                        "reason": "missing",
                        "payload": {
                            "catalog_id": "222222222222",
                            "tag_key": "domain",
                            "tag_values": ["sales"],
                        },
                    }
                ]
            }
        )

        self.stubber.add_response(
            "create_lf_tag",
            {},
            {
                "CatalogId": "222222222222",
                "TagKey": "domain",
                "TagValues": ["sales"],
            },
        )

        results = adapter.apply(change_plan, dry_run=False)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].applied)
        self.stubber.assert_no_pending_responses()

    def test_apply_resource_tag_payload_catalog_id_overrides_adapter_default(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "resource_tag.add_values",
                        "target": "table:catalog=222222222222:database=analytics:table=orders",
                        "reason": "missing assignment",
                        "payload": {
                            "resource": {
                                "kind": "table",
                                "catalog_id": "222222222222",
                                "database": "analytics",
                                "table": "orders",
                            },
                            "tags": {"domain": ["sales"]},
                        },
                    }
                ]
            }
        )

        self.stubber.add_response(
            "add_lf_tags_to_resource",
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
                "LFTags": [
                    {
                        "CatalogId": "222222222222",
                        "TagKey": "domain",
                        "TagValues": ["sales"],
                    }
                ],
            },
        )

        results = adapter.apply(change_plan, dry_run=False)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].applied)
        self.stubber.assert_no_pending_responses()

    def test_apply_resource_tag_removal_payload_catalog_id_overrides_adapter_default(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "resource_tag.remove_values",
                        "target": "table:catalog=222222222222:database=analytics:table=orders",
                        "reason": "extra assignment",
                        "destructive": True,
                        "payload": {
                            "resource": {
                                "kind": "table",
                                "catalog_id": "222222222222",
                                "database": "analytics",
                                "table": "orders",
                            },
                            "tags": {"domain": ["legacy"]},
                        },
                    }
                ]
            }
        )

        self.stubber.add_response(
            "remove_lf_tags_from_resource",
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
                "LFTags": [
                    {
                        "CatalogId": "222222222222",
                        "TagKey": "domain",
                        "TagValues": ["legacy"],
                    }
                ],
            },
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].applied)
        self.stubber.assert_no_pending_responses()

    def test_apply_table_grant_uses_resource_catalog_id_over_adapter_default(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "grant.add_permissions",
                        "target": "principal -> table:catalog=222222222222:database=analytics:table=orders",
                        "reason": "missing table permissions",
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": {
                                "kind": "table",
                                "catalog_id": "222222222222",
                                "database": "analytics",
                                "table": "orders",
                            },
                            "permissions": ["SELECT"],
                            "grantable_permissions": [],
                        },
                    }
                ]
            }
        )

        self.stubber.add_response(
            "grant_permissions",
            {},
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
                "Permissions": ["SELECT"],
                "PermissionsWithGrantOption": [],
            },
        )

        results = adapter.apply(change_plan, dry_run=False)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].applied)
        self.stubber.assert_no_pending_responses()

    def test_apply_data_location_grant_and_revoke_use_resource_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        resource = {
            "kind": "data_location",
            "catalog_id": "222222222222",
            "location": "arn:aws:s3:::analytics-lake/raw/",
        }
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "grant.add_permissions",
                        "target": "principal -> data_location:catalog=222222222222:location=arn:aws:s3:::analytics-lake/raw/",
                        "reason": "missing data location access",
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": resource,
                            "permissions": ["DATA_LOCATION_ACCESS"],
                            "grantable_permissions": [],
                        },
                    },
                    {
                        "action": "grant.revoke_permissions",
                        "target": "principal -> data_location:catalog=222222222222:location=arn:aws:s3:::analytics-lake/raw/",
                        "reason": "extra data location access",
                        "destructive": True,
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": resource,
                            "permissions": ["DATA_LOCATION_ACCESS"],
                            "grantable_permissions": [],
                        },
                    },
                ]
            }
        )
        expected_resource = {
            "DataLocation": {
                "CatalogId": "222222222222",
                "ResourceArn": "arn:aws:s3:::analytics-lake/raw/",
            }
        }

        self.stubber.add_response(
            "grant_permissions",
            {},
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": expected_resource,
                "Permissions": ["DATA_LOCATION_ACCESS"],
                "PermissionsWithGrantOption": [],
            },
        )
        self.stubber.add_response(
            "revoke_permissions",
            {},
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": expected_resource,
                "Permissions": ["DATA_LOCATION_ACCESS"],
                "PermissionsWithGrantOption": [],
            },
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.applied for result in results))
        self.stubber.assert_no_pending_responses()

    def test_apply_data_cells_filter_grant_uses_table_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "grant.add_permissions",
                        "target": "principal -> data_cells_filter:catalog=222222222222:database=analytics:table=orders:filter_name=orders_public",
                        "reason": "missing filtered table permissions",
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": {
                                "kind": "data_cells_filter",
                                "catalog_id": "222222222222",
                                "database": "analytics",
                                "table": "orders",
                                "filter_name": "orders_public",
                            },
                            "permissions": ["SELECT"],
                            "grantable_permissions": [],
                        },
                    }
                ]
            }
        )

        self.stubber.add_response(
            "grant_permissions",
            {},
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "DataCellsFilter": {
                        "TableCatalogId": "222222222222",
                        "DatabaseName": "analytics",
                        "TableName": "orders",
                        "Name": "orders_public",
                    }
                },
                "Permissions": ["SELECT"],
                "PermissionsWithGrantOption": [],
            },
        )

        results = adapter.apply(change_plan, dry_run=False)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].applied)
        self.stubber.assert_no_pending_responses()

    def test_apply_data_cells_filter_revoke_uses_table_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "grant.revoke_permissions",
                        "target": "principal -> data_cells_filter:catalog=222222222222:database=analytics:table=orders:filter_name=orders_public",
                        "reason": "extra filtered table permissions",
                        "destructive": True,
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": {
                                "kind": "data_cells_filter",
                                "catalog_id": "222222222222",
                                "database": "analytics",
                                "table": "orders",
                                "filter_name": "orders_public",
                            },
                            "permissions": ["SELECT"],
                            "grantable_permissions": [],
                        },
                    }
                ]
            }
        )

        self.stubber.add_response(
            "revoke_permissions",
            {},
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {
                    "DataCellsFilter": {
                        "TableCatalogId": "222222222222",
                        "DatabaseName": "analytics",
                        "TableName": "orders",
                        "Name": "orders_public",
                    }
                },
                "Permissions": ["SELECT"],
                "PermissionsWithGrantOption": [],
            },
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].applied)
        self.stubber.assert_no_pending_responses()

    def test_apply_data_cells_filter_definition_changes_use_table_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        create_payload = {
            "name": "orders_public",
            "catalog_id": "222222222222",
            "database": "analytics",
            "table": "orders",
            "row_filter": "country = 'US'",
            "columns": ["order_id", "status"],
        }
        update_payload = {
            "name": "orders_public",
            "catalog_id": "222222222222",
            "database": "analytics",
            "table": "orders",
            "all_rows": True,
            "excluded_columns": ["notes"],
            "version_id": "v1",
        }
        delete_payload = {
            "name": "orders_legacy",
            "catalog_id": "222222222222",
            "database": "analytics",
            "table": "orders",
        }
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "data_cells_filter.create",
                        "target": "data_cells_filter:catalog=222222222222:database=analytics:table=orders:name=orders_public",
                        "reason": "missing filter",
                        "payload": create_payload,
                    },
                    {
                        "action": "data_cells_filter.update",
                        "target": "data_cells_filter:catalog=222222222222:database=analytics:table=orders:name=orders_public",
                        "reason": "filter drift",
                        "destructive": True,
                        "payload": update_payload,
                    },
                    {
                        "action": "data_cells_filter.delete",
                        "target": "data_cells_filter:catalog=222222222222:database=analytics:table=orders:name=orders_legacy",
                        "reason": "unmanaged filter",
                        "destructive": True,
                        "payload": delete_payload,
                    },
                ]
            }
        )

        self.stubber.add_response(
            "create_data_cells_filter",
            {},
            {
                "TableData": {
                    "TableCatalogId": "222222222222",
                    "DatabaseName": "analytics",
                    "TableName": "orders",
                    "Name": "orders_public",
                    "RowFilter": {"FilterExpression": "country = 'US'"},
                    "ColumnNames": ["order_id", "status"],
                }
            },
        )
        self.stubber.add_response(
            "update_data_cells_filter",
            {},
            {
                "TableData": {
                    "TableCatalogId": "222222222222",
                    "DatabaseName": "analytics",
                    "TableName": "orders",
                    "Name": "orders_public",
                    "RowFilter": {"AllRowsWildcard": {}},
                    "ColumnWildcard": {"ExcludedColumnNames": ["notes"]},
                    "VersionId": "v1",
                }
            },
        )
        self.stubber.add_response(
            "delete_data_cells_filter",
            {},
            {
                "TableCatalogId": "222222222222",
                "DatabaseName": "analytics",
                "TableName": "orders",
                "Name": "orders_legacy",
            },
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(
            [result.action for result in results],
            ["data_cells_filter.create", "data_cells_filter.update", "data_cells_filter.delete"],
        )
        self.stubber.assert_no_pending_responses()

    def test_apply_lf_tag_expression_changes_without_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client)
        change_plan = _lf_tag_expression_change_plan()

        self.stubber.add_response(
            "create_lf_tag_expression",
            {},
            {
                "Name": "sales_tables",
                "Description": "Sales tables",
                "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
            },
        )
        self.stubber.add_response(
            "update_lf_tag_expression",
            {},
            {
                "Name": "sales_tables",
                "Description": "",
                "Expression": [{"TagKey": "domain", "TagValues": ["finance"]}],
            },
        )
        self.stubber.add_response(
            "delete_lf_tag_expression",
            {},
            {"Name": "legacy"},
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(result.applied for result in results))
        self.stubber.assert_no_pending_responses()

    def test_apply_lf_tag_expression_changes_with_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id=CATALOG_ID)
        change_plan = _lf_tag_expression_change_plan()

        self.stubber.add_response(
            "create_lf_tag_expression",
            {},
            {
                "CatalogId": CATALOG_ID,
                "Name": "sales_tables",
                "Description": "Sales tables",
                "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
            },
        )
        self.stubber.add_response(
            "update_lf_tag_expression",
            {},
            {
                "CatalogId": CATALOG_ID,
                "Name": "sales_tables",
                "Description": "",
                "Expression": [{"TagKey": "domain", "TagValues": ["finance"]}],
            },
        )
        self.stubber.add_response(
            "delete_lf_tag_expression",
            {},
            {"CatalogId": CATALOG_ID, "Name": "legacy"},
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(result.applied for result in results))
        self.stubber.assert_no_pending_responses()

    def test_apply_lf_tag_expression_payload_catalog_id_overrides_adapter_default(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "lf_tag_expression.create",
                        "target": "lf_tag_expression:catalog=222222222222:name=sales_tables",
                        "reason": "missing",
                        "payload": {
                            "name": "sales_tables",
                            "catalog_id": "222222222222",
                            "expression": [{"key": "domain", "values": ["sales"]}],
                        },
                    }
                ]
            }
        )

        self.stubber.add_response(
            "create_lf_tag_expression",
            {},
            {
                "CatalogId": "222222222222",
                "Name": "sales_tables",
                "Description": "",
                "Expression": [{"TagKey": "domain", "TagValues": ["sales"]}],
            },
        )

        results = adapter.apply(change_plan, dry_run=False)

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].applied)
        self.stubber.assert_no_pending_responses()

    def test_apply_lf_tag_expression_grant_and_revoke_use_resource_catalog_id(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        resource = {
            "kind": "lf_tag_expression",
            "catalog_id": "222222222222",
            "expression_name": "sales_tables",
        }
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "grant.add_permissions",
                        "target": "principal -> lf_tag_expression:catalog=222222222222:expression_name=sales_tables",
                        "reason": "missing expression stewardship",
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": resource,
                            "permissions": ["DESCRIBE", "GRANT_WITH_LF_TAG_EXPRESSION"],
                            "grantable_permissions": [],
                        },
                    },
                    {
                        "action": "grant.revoke_permissions",
                        "target": "principal -> lf_tag_expression:catalog=222222222222:expression_name=sales_tables",
                        "reason": "extra expression stewardship",
                        "destructive": True,
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": resource,
                            "permissions": ["GRANT_WITH_LF_TAG_EXPRESSION"],
                            "grantable_permissions": [],
                        },
                    },
                ]
            }
        )
        expected_resource = {
            "LFTagExpression": {
                "CatalogId": "222222222222",
                "Name": "sales_tables",
            }
        }

        self.stubber.add_response(
            "grant_permissions",
            {},
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": expected_resource,
                "Permissions": ["DESCRIBE", "GRANT_WITH_LF_TAG_EXPRESSION"],
                "PermissionsWithGrantOption": [],
            },
        )
        self.stubber.add_response(
            "revoke_permissions",
            {},
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": expected_resource,
                "Permissions": ["GRANT_WITH_LF_TAG_EXPRESSION"],
                "PermissionsWithGrantOption": [],
            },
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.applied for result in results))
        self.stubber.assert_no_pending_responses()

    def test_apply_catalog_grant_and_revoke_use_resource_catalog_id_over_adapter_default(self):
        adapter = AWSLakeFormationAdapter(self.client, catalog_id="111111111111")
        resource = {
            "kind": "catalog",
            "catalog_id": "222222222222",
        }
        change_plan = Plan.from_dict(
            {
                "changes": [
                    {
                        "action": "grant.add_permissions",
                        "target": "principal -> catalog:catalog=222222222222",
                        "reason": "missing catalog permissions",
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": resource,
                            "permissions": ["CREATE_DATABASE"],
                            "grantable_permissions": [],
                        },
                    },
                    {
                        "action": "grant.revoke_permissions",
                        "target": "principal -> catalog:catalog=222222222222",
                        "reason": "extra catalog permissions",
                        "destructive": True,
                        "payload": {
                            "principal": PRINCIPAL,
                            "resource": resource,
                            "permissions": ["CREATE_DATABASE"],
                            "grantable_permissions": [],
                        },
                    }
                ]
            }
        )

        self.stubber.add_response(
            "grant_permissions",
            {},
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {"Catalog": {"Id": "222222222222"}},
                "Permissions": ["CREATE_DATABASE"],
                "PermissionsWithGrantOption": [],
            },
        )
        self.stubber.add_response(
            "revoke_permissions",
            {},
            {
                "CatalogId": "222222222222",
                "Principal": {"DataLakePrincipalIdentifier": PRINCIPAL},
                "Resource": {"Catalog": {"Id": "222222222222"}},
                "Permissions": ["CREATE_DATABASE"],
                "PermissionsWithGrantOption": [],
            },
        )

        results = adapter.apply(change_plan, dry_run=False, allow_destructive=True)

        self.assertEqual(len(results), 2)
        self.assertTrue(all(result.applied for result in results))
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
            "get_resource_lf_tags",
            {},
            {
                "CatalogId": "222222222222",
                "Resource": {"Catalog": {"Id": "222222222222"}},
                "ShowAssignedLFTags": True,
            },
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
            "get_resource_lf_tags",
            {},
            {
                "CatalogId": "222222222222",
                "Resource": resource,
                "ShowAssignedLFTags": True,
            },
        )
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
            "get_resource_lf_tags",
            {},
            {
                "CatalogId": "222222222222",
                "Resource": resource,
                "ShowAssignedLFTags": True,
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


def _lf_tag_expression_change_plan() -> Plan:
    return Plan.from_dict(
        {
            "changes": [
                {
                    "action": "lf_tag_expression.create",
                    "target": "lf_tag_expression:name=sales_tables",
                    "reason": "missing",
                    "payload": {
                        "name": "sales_tables",
                        "description": "Sales tables",
                        "expression": [{"key": "domain", "values": ["sales"]}],
                    },
                },
                {
                    "action": "lf_tag_expression.update",
                    "target": "lf_tag_expression:name=sales_tables",
                    "reason": "drift",
                    "destructive": True,
                    "payload": {
                        "name": "sales_tables",
                        "expression": [{"key": "domain", "values": ["finance"]}],
                    },
                },
                {
                    "action": "lf_tag_expression.delete",
                    "target": "lf_tag_expression:name=legacy",
                    "reason": "extra",
                    "destructive": True,
                    "payload": {"name": "legacy"},
                },
            ]
        }
    )


if __name__ == "__main__":
    unittest.main()
