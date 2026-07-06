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

    def test_plan_lf_tag_delete_requires_explicit_flag_and_runs_last(self):
        desired = DesiredState.from_dict({"lf_tags": {"sensitivity": ["internal"]}})
        current = CurrentState.from_dict(
            {
                "lf_tags": {
                    "domain": ["sales"],
                    "sensitivity": ["internal"],
                },
                "resource_tags": [
                    {
                        "resource": {"kind": "database", "database": "analytics"},
                        "tags": {"domain": ["sales"]},
                    }
                ],
            }
        )

        default_plan = plan(desired, current)
        destructive_plan = plan(
            desired,
            current,
            PlanOptions(allow_lf_tag_deletes=True, allow_resource_tag_removals=True),
        )

        self.assertEqual(default_plan.changes, ())
        self.assertEqual(
            [change.action for change in destructive_plan.changes],
            ["resource_tag.remove_values", "lf_tag.delete"],
        )
        self.assertEqual(destructive_plan.changes[1].requires_flag, "--allow-lf-tag-deletes")
        self.assertEqual(destructive_plan.changes[1].aws_api, "delete_lf_tag")
        self.assertTrue(all(change.destructive for change in destructive_plan.changes))

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

    def test_plan_data_cells_filter_create_update_and_delete(self):
        desired = DesiredState.from_dict(
            {
                "data_cells_filters": [
                    {
                        "name": "orders_internal",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "row_filter": "sensitivity <> 'restricted'",
                        "excluded_columns": ["notes"],
                    },
                    {
                        "name": "orders_public",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "all_rows": True,
                        "columns": ["order_id", "status"],
                    },
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "data_cells_filters": [
                    {
                        "name": "orders_legacy",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "all_rows": True,
                    },
                    {
                        "name": "orders_public",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "row_filter": "country = 'US'",
                        "columns": ["order_id"],
                    },
                ]
            }
        )

        default_plan = plan(desired, current)
        full_plan = plan(
            desired,
            current,
            PlanOptions(
                allow_data_cells_filter_updates=True,
                allow_data_cells_filter_deletes=True,
            ),
        )

        self.assertEqual([change.action for change in default_plan.changes], ["data_cells_filter.create"])
        self.assertEqual(
            [change.action for change in full_plan.changes],
            ["data_cells_filter.create", "data_cells_filter.update", "data_cells_filter.delete"],
        )
        self.assertEqual(full_plan.changes[0].aws_api, "create_data_cells_filter")
        self.assertEqual(full_plan.changes[1].requires_flag, "--allow-data-cells-filter-updates")
        self.assertEqual(full_plan.changes[2].requires_flag, "--allow-data-cells-filter-deletes")
        self.assertEqual(full_plan.changes[1].before["row_filter"], "country = 'US'")
        self.assertIsNone(full_plan.changes[2].after)

    def test_plan_ignores_current_data_cells_filter_version_id(self):
        desired = DesiredState.from_dict(
            {
                "data_cells_filters": [
                    {
                        "name": "orders_public",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "all_rows": True,
                        "columns": ["order_id"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "data_cells_filters": [
                    {
                        "name": "orders_public",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "all_rows": True,
                        "columns": ["order_id"],
                        "version_id": "aws-version",
                    }
                ]
            }
        )

        self.assertEqual(plan(desired, current, PlanOptions(allow_data_cells_filter_updates=True)).changes, ())

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

    def test_plan_keys_lf_tags_by_catalog_id(self):
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
        current = CurrentState.from_dict(
            {
                "lf_tags": [
                    {
                        "key": "domain",
                        "catalog_id": "111111111111",
                        "values": ["sales"],
                    }
                ]
            }
        )

        change_plan = plan(desired, current)

        self.assertEqual([change.action for change in change_plan.changes], ["lf_tag.create"])
        self.assertEqual(change_plan.changes[0].target, "lf_tag:catalog=222222222222:key=domain")
        self.assertEqual(change_plan.changes[0].payload["catalog_id"], "222222222222")

    def test_plan_rejects_duplicate_lf_tag_identity(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": [
                    {
                        "key": "domain",
                        "catalog_id": "111111111111",
                        "values": ["sales"],
                    },
                    {
                        "key": "domain",
                        "catalog_id": "111111111111",
                        "values": ["finance"],
                    },
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "Duplicate LF-Tag identity"):
            plan(desired, CurrentState.empty())

    def test_plan_rejects_duplicate_lf_tag_expression_identity(self):
        desired = DesiredState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["sales"]},
                    },
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["finance"]},
                    },
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "Duplicate LF-Tag expression identity"):
            plan(desired, CurrentState.empty())

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

    def test_audit_keys_lf_tags_by_catalog_id(self):
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
        current = CurrentState.from_dict(
            {
                "lf_tags": [
                    {
                        "key": "domain",
                        "catalog_id": "111111111111",
                        "values": ["sales"],
                    }
                ]
            }
        )

        findings = audit(desired, current)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_MISSING", "LF_TAG_UNMANAGED"])
        self.assertEqual(findings[0].details["catalog_id"], "222222222222")
        self.assertEqual(findings[1].details["catalog_id"], "111111111111")
        self.assertEqual(findings[1].details["current"]["values"], ["sales"])

    def test_audit_ignores_unmanaged_lf_tags_by_catalog_resource_rule(self):
        desired = DesiredState.from_dict(
            {
                "ignore": {
                    "resources": [{"kind": "catalog", "catalog_id": "111111111111"}],
                },
            }
        )
        current = CurrentState.from_dict(
            {
                "lf_tags": [
                    {
                        "key": "domain",
                        "catalog_id": "111111111111",
                        "values": ["sales"],
                    }
                ]
            }
        )

        findings = audit(desired, current)

        self.assertEqual(findings, ())

    def test_plan_removes_unmanaged_resource_tags_when_allowed(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {
                            "domain": ["legacy"],
                            "sensitivity": ["restricted"],
                        },
                    }
                ]
            }
        )

        default_plan = plan(DesiredState.empty(), current)
        removal_plan = plan(
            DesiredState.empty(),
            current,
            PlanOptions(allow_resource_tag_removals=True),
        )

        self.assertEqual(default_plan.changes, ())
        self.assertEqual([change.action for change in removal_plan.changes], ["resource_tag.remove_values"])
        change = removal_plan.changes[0]
        expected_resource = {
            "kind": "table",
            "catalog_id": "222222222222",
            "database": "analytics",
            "table": "orders",
        }
        self.assertEqual(change.target, "table:catalog=222222222222:database=analytics:table=orders")
        self.assertTrue(change.destructive)
        self.assertEqual(change.requires_flag, "--allow-resource-tag-removals")
        self.assertEqual(change.aws_api, "remove_lf_tags_from_resource")
        self.assertEqual(change.payload["resource"], expected_resource)
        self.assertEqual(
            change.payload["tags"],
            {"domain": ["legacy"], "sensitivity": ["restricted"]},
        )
        self.assertEqual(
            change.before,
            {
                "resource": expected_resource,
                "tags": {"domain": ["legacy"], "sensitivity": ["restricted"]},
            },
        )
        self.assertEqual(change.after, {"resource": expected_resource, "tags": {}})

    def test_plan_resource_tag_changes_have_deterministic_order(self):
        desired = DesiredState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders_z",
                        },
                        "tags": {"sensitivity": ["internal"], "domain": ["sales"]},
                    },
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "111111111111",
                            "database": "analytics",
                            "table": "orders_a",
                        },
                        "tags": {"sensitivity": ["internal"], "domain": ["sales"]},
                    },
                ]
            }
        )

        change_plan = plan(desired, CurrentState.empty())

        self.assertEqual(
            [change.target for change in change_plan.changes],
            [
                "table:catalog=111111111111:database=analytics:table=orders_a",
                "table:catalog=222222222222:database=analytics:table=orders_z",
            ],
        )
        self.assertEqual(
            change_plan.changes[0].payload["tags"],
            {"domain": ["sales"], "sensitivity": ["internal"]},
        )

    def test_plan_removes_unmanaged_resource_tag_keys_when_resource_is_desired(self):
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
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {
                            "domain": ["sales"],
                            "sensitivity": ["restricted"],
                        },
                    }
                ]
            }
        )

        default_plan = plan(desired, current)
        removal_plan = plan(
            desired,
            current,
            PlanOptions(allow_resource_tag_removals=True),
        )

        self.assertEqual(default_plan.changes, ())
        self.assertEqual([change.action for change in removal_plan.changes], ["resource_tag.remove_values"])
        self.assertEqual(removal_plan.changes[0].payload["tags"], {"sensitivity": ["restricted"]})
        self.assertEqual(
            removal_plan.changes[0].after,
            {
                "resource": {
                    "kind": "table",
                    "catalog_id": "222222222222",
                    "database": "analytics",
                    "table": "orders",
                },
                "tags": {"domain": ["sales"]},
            },
        )

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

    def test_plan_only_adds_all_covered_desired_permission_when_revoking_current_all(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["ALL"],
                    }
                ]
            }
        )

        default_plan = plan(desired, current)
        revoke_plan = plan(desired, current, PlanOptions(allow_permission_revokes=True))

        self.assertEqual(default_plan.changes, ())
        self.assertEqual(
            [change.action for change in revoke_plan.changes],
            ["grant.add_permissions", "grant.revoke_permissions"],
        )
        self.assertEqual(revoke_plan.changes[0].payload["permissions"], ["SELECT"])
        self.assertEqual(revoke_plan.changes[1].payload["permissions"], ["ALL"])
        self.assertEqual(revoke_plan.changes[1].after["permissions"], [])

    def test_plan_adds_desired_grantable_permission_when_revoking_current_all_grantable(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                        "grantable_permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["ALL"],
                        "grantable_permissions": ["ALL"],
                    }
                ]
            }
        )

        revoke_plan = plan(desired, current, PlanOptions(allow_permission_revokes=True))

        self.assertEqual(
            [change.action for change in revoke_plan.changes],
            ["grant.add_permissions", "grant.revoke_permissions"],
        )
        self.assertEqual(revoke_plan.changes[0].payload["permissions"], ["SELECT"])
        self.assertEqual(revoke_plan.changes[0].payload["grantable_permissions"], ["SELECT"])
        self.assertEqual(revoke_plan.changes[1].payload["permissions"], ["ALL"])
        self.assertEqual(revoke_plan.changes[1].payload["grantable_permissions"], ["ALL"])

    def test_plan_revoke_preserves_data_cells_filter_resource_identity(self):
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
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

        change_plan = plan(DesiredState.empty(), current, PlanOptions(allow_permission_revokes=True))

        self.assertEqual(len(change_plan.changes), 1)
        change = change_plan.changes[0]
        self.assertEqual(change.action, "grant.revoke_permissions")
        self.assertEqual(
            change.payload["resource"],
            {
                "kind": "data_cells_filter",
                "catalog_id": "222222222222",
                "database": "analytics",
                "table": "orders",
                "filter_name": "orders_public",
            },
        )
        self.assertEqual(change.requires_flag, "--allow-permission-revokes")
        self.assertEqual(change.aws_api, "revoke_permissions")

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
