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
                "CatalogId": CATALOG_ID,
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
