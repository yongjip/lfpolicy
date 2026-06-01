import unittest

from lakeformation_guard import CurrentState, DesiredState, Plan, PlanOptions, audit, plan


class PlannerTests(unittest.TestCase):
    def test_plan_adds_missing_lf_tags_resource_tags_and_grants(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/Analyst",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        change_plan = plan(desired, CurrentState.empty())

        self.assertEqual(
            [change.action for change in change_plan.changes],
            ["lf_tag.create", "resource_tag.add_values", "grant.add_permissions"],
        )
        self.assertEqual(
            [change.id for change in change_plan.changes],
            ["change_001", "change_002", "change_003"],
        )
        self.assertEqual(change_plan.summary(), {"total": 3, "safe": 3, "destructive": 0})

    def test_plan_json_has_stable_fields(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/Analyst",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    }
                ],
            }
        )

        payload = plan(desired, CurrentState.empty()).to_dict()
        lf_tag_change, grant_change = payload["changes"]

        self.assertEqual(payload["schema_version"], "lfguard.plan.v1")
        self.assertEqual(lf_tag_change["id"], "change_001")
        self.assertEqual(lf_tag_change["risk"], "safe")
        self.assertIsNone(lf_tag_change["principal"])
        self.assertIsNone(lf_tag_change["resource"])
        self.assertIsNone(lf_tag_change["before"])
        self.assertEqual(lf_tag_change["after"], {"tag_key": "sensitivity", "tag_values": ["internal"]})
        self.assertIsNone(lf_tag_change["requires_flag"])
        self.assertEqual(lf_tag_change["aws_api"], "create_lf_tag")
        self.assertEqual(grant_change["id"], "change_002")
        self.assertEqual(grant_change["principal"], "arn:aws:iam::111122223333:role/Analyst")
        self.assertEqual(grant_change["resource"], {"kind": "database", "database": "analytics"})
        self.assertEqual(grant_change["aws_api"], "grant_permissions")

    def test_plan_omits_destructive_changes_by_default(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    }
                ],
            }
        )
        current = CurrentState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal", "restricted"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE", "DROP"],
                    }
                ],
            }
        )

        change_plan = plan(desired, current)

        self.assertEqual(change_plan.changes, ())

    def test_plan_lf_tag_expression_create_update_and_delete(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales", "finance"]},
                "lf_tag_expressions": {
                    "sales_tables": {
                        "description": "Sales tables",
                        "expression": {"domain": ["sales"]},
                    }
                },
            }
        )
        current = CurrentState.from_dict(
            {
                "lf_tags": {"domain": ["sales", "finance"]},
                "lf_tag_expressions": {
                    "sales_tables": {
                        "description": "Old",
                        "expression": {"domain": ["finance"]},
                    },
                    "legacy": {"expression": {"domain": ["finance"]}},
                },
            }
        )

        default_plan = plan(desired, current)
        full_plan = plan(
            desired,
            current,
            PlanOptions(allow_lf_tag_expression_updates=True, allow_lf_tag_expression_deletes=True),
        )

        self.assertEqual(default_plan.changes, ())
        self.assertEqual(
            [change.action for change in full_plan.changes],
            ["lf_tag_expression.update", "lf_tag_expression.delete"],
        )
        self.assertEqual(
            [change.requires_flag for change in full_plan.changes],
            ["--allow-lf-tag-expression-updates", "--allow-lf-tag-expression-deletes"],
        )
        self.assertTrue(all(change.destructive for change in full_plan.changes))

    def test_plan_creates_missing_lf_tag_expression(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "lf_tag_expressions": {"sales_tables": {"expression": {"domain": ["sales"]}}},
            }
        )

        change_plan = plan(desired, CurrentState.empty())

        self.assertEqual([change.action for change in change_plan.changes], ["lf_tag.create", "lf_tag_expression.create"])
        self.assertEqual(change_plan.changes[1].aws_api, "create_lf_tag_expression")
        self.assertFalse(change_plan.changes[1].destructive)

    def test_plan_keys_lf_tag_expressions_by_catalog_id(self):
        desired = DesiredState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "222222222222",
                        "expression": {"domain": ["sales"]},
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["sales"]},
                    }
                ]
            }
        )

        change_plan = plan(desired, current, PlanOptions(allow_lf_tag_expression_deletes=True))

        self.assertEqual(
            [change.action for change in change_plan.changes],
            ["lf_tag_expression.create", "lf_tag_expression.delete"],
        )
        self.assertEqual(change_plan.changes[0].payload["catalog_id"], "222222222222")
        self.assertEqual(change_plan.changes[1].payload["catalog_id"], "111111111111")

    def test_audit_keys_lf_tag_expressions_by_catalog_id(self):
        desired = DesiredState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "222222222222",
                        "expression": {"domain": ["sales"]},
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["sales"]},
                    }
                ]
            }
        )

        findings = audit(desired, current)

        self.assertEqual(
            [finding.code for finding in findings],
            ["LF_TAG_EXPRESSION_MISSING", "LF_TAG_EXPRESSION_UNMANAGED"],
        )
        self.assertEqual(findings[0].details["catalog_id"], "222222222222")
        self.assertEqual(findings[1].details["catalog_id"], "111111111111")

    def test_plan_includes_destructive_changes_when_allowed(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    }
                ],
            }
        )
        current = CurrentState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal", "restricted"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE", "DROP"],
                    },
                    {
                        "principal": "other-role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    },
                ],
            }
        )

        change_plan = plan(
            desired,
            current,
            PlanOptions(allow_lf_tag_value_removals=True, allow_permission_revokes=True),
        )

        self.assertEqual(
            [change.action for change in change_plan.changes],
            ["lf_tag.remove_values", "grant.revoke_permissions", "grant.revoke_permissions"],
        )
        self.assertTrue(all(change.destructive for change in change_plan.changes))
        self.assertEqual(
            [change.requires_flag for change in change_plan.changes],
            [
                "--allow-lf-tag-value-removals",
                "--allow-permission-revokes",
                "--allow-permission-revokes",
            ],
        )
        self.assertEqual(
            [change.aws_api for change in change_plan.changes],
            ["update_lf_tag", "revoke_permissions", "revoke_permissions"],
        )

    def test_plan_from_dict_accepts_current_schema_and_preserves_ids(self):
        payload = {
            "schema_version": "lfguard.plan.v1",
            "summary": {"total": 1, "safe": 1, "destructive": 0},
            "changes": [
                {
                    "id": "change_004",
                    "action": "grant.add_permissions",
                    "target": "role -> database:database=analytics",
                    "reason": "Principal is missing desired Lake Formation permissions",
                    "destructive": False,
                    "payload": {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                        "grantable_permissions": [],
                    },
                    "before": None,
                    "after": {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    },
                }
            ],
        }

        change_plan = Plan.from_dict(payload)

        self.assertEqual(change_plan.changes[0].id, "change_004")
        self.assertEqual(change_plan.to_dict()["changes"][0]["aws_api"], "grant_permissions")
        self.assertEqual(change_plan.to_dict()["changes"][0]["after"]["permissions"], ["DESCRIBE"])

    def test_plan_from_dict_accepts_legacy_plan_without_ids(self):
        change_plan = Plan.from_dict(
            {
                "summary": {"total": 1, "safe": 1, "destructive": 0},
                "changes": [
                    {
                        "action": "lf_tag.create",
                        "target": "lf_tag:sensitivity",
                        "reason": "LF-Tag is missing",
                        "destructive": False,
                        "payload": {"tag_key": "sensitivity", "tag_values": ["internal"]},
                    }
                ],
            }
        )

        self.assertEqual(change_plan.changes[0].id, "change_001")
        self.assertEqual(change_plan.to_dict()["schema_version"], "lfguard.plan.v1")


if __name__ == "__main__":
    unittest.main()
