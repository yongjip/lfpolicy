import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lakeformation_guard import (
    CurrentState,
    DesiredState,
    ResourceRef,
    SnapshotCurrentStateProvider,
    SnapshotFileCurrentStateProvider,
    explain,
    lint_desired,
)
from lakeformation_guard.cli import main


class ProviderExplainTests(unittest.TestCase):
    def test_snapshot_providers_return_current_state(self):
        current = CurrentState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "grants": [],
            }
        )

        provider = SnapshotCurrentStateProvider(current)
        self.assertEqual(provider.load_current_state_for(DesiredState.empty()), current)

        with tempfile.TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "current.json"
            snapshot_path.write_text(json.dumps(current.to_dict()), encoding="utf-8")
            file_provider = SnapshotFileCurrentStateProvider(str(snapshot_path))

            loaded = file_provider.load_current_state_for(DesiredState.empty())

        self.assertEqual(loaded, current)

    def test_explain_reports_direct_table_grant_and_effective_tags(self):
        desired = DesiredState.empty()
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "database", "database": "analytics"},
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            desired,
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.effective_lf_tags["domain"], ("sales",))
        self.assertEqual(report.effective_lf_tags["sensitivity"], ("internal",))
        self.assertEqual(report.findings[0].source, "direct_grant")

    def test_explain_resolves_named_lf_tag_expression_grant(self):
        current = CurrentState.from_dict(
            {
                "lf_tag_expressions": {
                    "sales_tables": {"expression": {"domain": ["sales"], "sensitivity": ["internal"]}}
                },
                "resource_tags": [
                    {
                        "resource": {"kind": "database", "database": "analytics"},
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression_name": "sales_tables",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].source, "named_lf_tag_policy")
        self.assertIn("sales_tables", report.findings[0].message)

    def test_explain_resolves_named_lf_tag_expression_by_catalog_id(self):
        current = CurrentState.from_dict(
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
                ],
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"domain": ["sales"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "222222222222",
                            "resource_type": "TABLE",
                            "expression_name": "shared",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].details["expression_name"], "shared")

    def test_explain_resolves_unscoped_named_lf_tag_expression_to_single_scoped_definition(self):
        state = {
            "lf_tags": {"domain": ["sales"]},
            "lf_tag_expressions": [
                {
                    "name": "shared",
                    "catalog_id": "222222222222",
                    "expression": {"domain": ["sales"]},
                }
            ],
            "resource_tags": [
                {
                    "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                    "tags": {"domain": ["sales"]},
                }
            ],
            "grants": [
                {
                    "principal": "role",
                    "resource": {
                        "kind": "lf_tag_policy",
                        "resource_type": "TABLE",
                        "expression_name": "shared",
                    },
                    "permissions": ["SELECT"],
                }
            ],
        }
        desired = DesiredState.from_dict(state)
        current = CurrentState.from_dict(state)

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(lint_desired(desired), ())
        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].details["expression"], {"domain": ["sales"]})

    def test_explain_reports_non_matching_lf_tag_policy_conditions(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"domain": ["sales"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["finance"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["not_matched"], 1)
        self.assertEqual(report.findings[0].details["mismatched_values"][0]["actual"], ["sales"])
        self.assertEqual(report.findings[0].details["mismatched_values"][0]["expected"], ["finance"])

    def test_explain_reports_desired_grant_missing_from_current(self):
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
        current = CurrentState.empty()

        report = explain(
            desired,
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["missing"], 1)
        self.assertEqual(report.findings[0].source, "desired_grant")

    def test_cli_explain_uses_current_snapshot_without_aws(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(json.dumps({"grants": []}), encoding="utf-8")
            current_path.write_text(
                json.dumps(
                    {
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "permissions": ["SELECT"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter.from_boto3") as from_boto3:
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "explain",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--principal",
                            "role",
                            "--database",
                            "analytics",
                            "--table",
                            "orders",
                            "--permissions",
                            "SELECT",
                            "--output",
                            "json",
                        ]
                    )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["schema_version"], "lfguard.explain.v1")
            self.assertEqual(payload["summary"]["matched"], 1)
            from_boto3.assert_not_called()

    def test_cli_explain_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(json.dumps({"grants": []}), encoding="utf-8")
            current_path.write_text(json.dumps({"grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "explain",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--principal",
                        "role",
                        "--database",
                        "analytics",
                        "--output",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard explain", stdout.getvalue())
            self.assertIn("No current or desired grants matched", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
