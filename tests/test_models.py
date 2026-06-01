import unittest

from lakeformation_guard.models import DesiredState, LFTagKeyMetadata, ResourceRef


class ModelTests(unittest.TestCase):
    def test_state_from_dict_normalizes_tags_and_grants(self):
        state = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal", "public", "public"]},
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/Analyst",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["describe"],
                    }
                ],
            }
        )

        self.assertEqual(state.lf_tags[0].values, ("internal", "public"))
        self.assertEqual(state.resource_tags[0].resource.identity, "table:database=analytics:table=orders")
        self.assertEqual(state.grants[0].permissions, ("DESCRIBE",))

    def test_lf_tag_policy_resource_identity_is_stable(self):
        first = ResourceRef.from_dict(
            {
                "kind": "lf_tag_policy",
                "resource_type": "table",
                "expression": {"domain": ["sales"], "sensitivity": ["internal", "public"]},
            }
        )
        second = ResourceRef.from_dict(
            {
                "kind": "lf-tag-policy",
                "resource_type": "TABLE",
                "expression": [
                    {"key": "sensitivity", "values": ["public", "internal"]},
                    {"key": "domain", "values": ["sales"]},
                ],
            }
        )

        self.assertEqual(first, second)
        self.assertEqual(
            first.identity,
            "lf_tag_policy:resource_type=TABLE:expression=domain=sales,sensitivity=internal|public",
        )

    def test_lf_tag_policy_can_reference_named_expression(self):
        resource = ResourceRef.from_dict(
            {
                "kind": "lf_tag_policy",
                "resource_type": "TABLE",
                "expression_name": "sales_public",
            }
        )

        self.assertEqual(
            resource.identity,
            "lf_tag_policy:resource_type=TABLE:expression_name=sales_public",
        )
        self.assertEqual(
            resource.to_dict(),
            {
                "kind": "lf_tag_policy",
                "resource_type": "TABLE",
                "expression_name": "sales_public",
            },
        )

    def test_resource_name_aliases_stay_kind_specific(self):
        database = ResourceRef.from_dict({"kind": "database", "name": "analytics"})
        expression = ResourceRef.from_dict({"kind": "lf_tag_expression", "name": "sales_public"})

        self.assertEqual(database.identity, "database:database=analytics")
        self.assertEqual(expression.identity, "lf_tag_expression:expression_name=sales_public")
        self.assertEqual(expression.to_dict(), {"kind": "lf_tag_expression", "expression_name": "sales_public"})

    def test_state_parses_config_and_named_lf_tag_expressions(self):
        state = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "lf_tag_expressions": {
                    "sales_tables": {
                        "description": "Sales tables",
                        "expression": {"domain": ["sales"]},
                    }
                },
                "lint": {"named_resource_grant_review": "ignore"},
                "ownership": {
                    "managed_principals": ["arn:aws:iam::*:role/data-*"],
                    "unmanaged_action": "ignore",
                },
                "ignore": {
                    "principals": ["IAM_ALLOWED_PRINCIPALS"],
                    "resources": [{"database": "legacy_*"}],
                },
            }
        )

        self.assertEqual(state.lf_tag_expressions[0].name, "sales_tables")
        self.assertEqual(state.lf_tag_expressions[0].description, "Sales tables")
        self.assertEqual(state.config.lint["NAMED_RESOURCE_GRANT_REVIEW"], "ignore")
        self.assertEqual(state.config.ownership.unmanaged_action, "ignore")
        self.assertEqual(state.config.ignore.resources[0].database_name, "legacy_*")
        self.assertIn("lf_tag_expressions", state.to_dict())
        self.assertIn("lint", state.to_dict())

    def test_state_serializes_duplicate_named_lf_tag_expressions_as_list(self):
        state = DesiredState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["finance"]},
                    },
                    {
                        "name": "shared",
                        "catalog_id": "222222222222",
                        "expression": {"domain": ["sales"]},
                    },
                ]
            }
        )

        payload = state.to_dict()
        expressions = payload["lf_tag_expressions"]
        round_tripped = DesiredState.from_dict(payload)

        self.assertIsInstance(expressions, list)
        self.assertEqual(
            {(item["catalog_id"], item["name"]) for item in expressions},
            {("111111111111", "shared"), ("222222222222", "shared")},
        )
        self.assertEqual(
            {(expression.catalog_id, expression.name) for expression in round_tripped.lf_tag_expressions},
            {("111111111111", "shared"), ("222222222222", "shared")},
        )

    def test_state_parses_optional_lf_tag_key_metadata(self):
        state = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "lf_tag_key_metadata": {
                    "domain": {"assignable_to": ["table", "column", "database"]},
                },
            }
        )

        self.assertEqual(
            state.lf_tag_key_metadata,
            (LFTagKeyMetadata("domain", ("database", "table", "column")),),
        )
        self.assertEqual(
            state.to_dict()["lf_tag_key_metadata"],
            {"domain": {"assignable_to": ["database", "table", "column"]}},
        )


if __name__ == "__main__":
    unittest.main()
