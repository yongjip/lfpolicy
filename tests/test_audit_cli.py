import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lakeformation_guard import CurrentState, DesiredState, __version__, audit, lint_desired
from lakeformation_guard.aws import ApplyResult
from lakeformation_guard.aws_permissions import IAMActionCheck, IAMPermissionCheckReport
from lakeformation_guard.cli import main


class AuditCliTests(unittest.TestCase):
    def test_audit_reports_missing_and_unmanaged_drift(self):
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
                "lf_tags": {"sensitivity": ["restricted"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DROP"],
                    }
                ],
            }
        )

        findings = audit(desired, current)

        self.assertEqual(
            {finding.code for finding in findings},
            {
                "LF_TAG_VALUES_MISSING",
                "LF_TAG_VALUES_UNMANAGED",
                "GRANT_PERMISSIONS_MISSING",
                "GRANT_PERMISSIONS_UNMANAGED",
            },
        )
        self.assertEqual(
            [finding.id for finding in findings],
            ["finding_001", "finding_002", "finding_003", "finding_004"],
        )

    def test_audit_treats_current_all_permission_as_covering_desired_permissions(self):
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

        findings = audit(desired, current)

        self.assertNotIn("GRANT_PERMISSIONS_MISSING", {finding.code for finding in findings})
        self.assertEqual([finding.code for finding in findings], ["GRANT_PERMISSIONS_UNMANAGED"])
        self.assertEqual(findings[0].details["unmanaged_permissions"], ["ALL"])

    def test_cli_plan_outputs_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
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
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["summary"], {"total": 2, "safe": 2, "destructive": 0})
            self.assertEqual(payload["schema_version"], "lfguard.plan.v1")
            self.assertEqual(
                [change["action"] for change in payload["changes"]],
                ["lf_tag.create", "grant.add_permissions"],
            )
            self.assertEqual([change["id"] for change in payload["changes"]], ["change_001", "change_002"])

    def test_cli_plan_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
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
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard plan", stdout.getvalue())
            self.assertIn("| ID | Safety | Action | Target | Reason |", stdout.getvalue())
            self.assertIn("| change_001 | safe | lf_tag.create | lf_tag:sensitivity | LF-Tag is missing |", stdout.getvalue())

    def test_cli_plan_can_fail_when_changes_are_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--fail-on-changes",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("Plan: 1 change(s), 1 safe, 0 destructive.", stdout.getvalue())

    def test_cli_plan_writes_report_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "lfguard-plan.md"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "markdown",
                        "--output-file",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("### lfguard plan", report)
            self.assertIn("| change_001 | safe | lf_tag.create | lf_tag:sensitivity | LF-Tag is missing |", report)

    def test_cli_plan_writes_json_report_before_failing_on_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "plan.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                        "--output-file",
                        str(output_path),
                        "--fail-on-changes",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["summary"], {"total": 1, "safe": 1, "destructive": 0})

    def test_cli_plan_fail_on_changes_passes_when_plan_is_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            state = {"lf_tags": {"sensitivity": ["internal"]}, "grants": []}
            desired_path.write_text(json.dumps(state), encoding="utf-8")
            current_path.write_text(json.dumps(state), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--fail-on-changes",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("Plan: 0 change(s), 0 safe, 0 destructive.", stdout.getvalue())

    def test_cli_audit_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
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
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard audit", stdout.getvalue())
            self.assertIn("- Total findings: 3", stdout.getvalue())
            self.assertIn("- Error findings: 2", stdout.getvalue())
            self.assertIn("- Warning findings: 1", stdout.getvalue())
            self.assertIn("| Severity | Code | Target | Message |", stdout.getvalue())
            self.assertIn("LF_TAG_VALUES_MISSING", stdout.getvalue())

    def test_cli_audit_outputs_json_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["schema_version"], "lfguard.audit.v1")
            self.assertEqual(payload["summary"], {"total": 2, "errors": 1, "warnings": 1})
            self.assertEqual(
                [finding["code"] for finding in payload["findings"]],
                ["LF_TAG_VALUES_MISSING", "LF_TAG_VALUES_UNMANAGED"],
            )
            self.assertEqual([finding["id"] for finding in payload["findings"]], ["finding_001", "finding_002"])
            self.assertIsNone(payload["findings"][0]["principal"])
            self.assertIsNone(payload["findings"][0]["resource"])

    def test_cli_audit_outputs_sarif(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "sarif",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            run = payload["runs"][0]
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["version"], "2.1.0")
            self.assertEqual(run["tool"]["driver"]["name"], "lfguard")
            self.assertEqual(
                [result["ruleId"] for result in run["results"]],
                ["LF_TAG_VALUES_MISSING", "LF_TAG_VALUES_UNMANAGED"],
            )
            self.assertEqual([result["level"] for result in run["results"]], ["error", "warning"])
            self.assertEqual(
                run["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
                str(desired_path),
            )

    def test_cli_audit_writes_report_output_file_before_failing_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "lfguard-audit.txt"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output-file",
                        str(output_path),
                        "--fail-on-findings",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("Findings: 2 total, 1 error(s), 1 warning(s).", report)
            self.assertIn("LF_TAG_VALUES_MISSING", report)

    def test_cli_audit_default_fail_on_findings_fails_for_warning_only_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal", "restricted"]}, "grants": []}),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--fail-on-findings",
                    ]
                )

            self.assertEqual(exit_code, 1)
            self.assertIn("[warning] LF_TAG_VALUES_UNMANAGED", stdout.getvalue())

    def test_cli_audit_can_fail_on_error_severity_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal", "restricted"]}, "grants": []}),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "audit",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--fail-on-findings",
                        "--fail-on-severity",
                        "error",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("[warning] LF_TAG_VALUES_UNMANAGED", stdout.getvalue())

    def test_cli_audit_writes_github_summary_before_failing_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            summary_path = tmp_path / "summary.md"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["restricted"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "audit",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--fail-on-findings",
                            "--github-summary",
                        ]
                    )

            self.assertEqual(exit_code, 1)
            self.assertIn("Findings:", stdout.getvalue())
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("### lfguard audit", summary)
            self.assertIn("LF_TAG_VALUES_MISSING", summary)

    def test_cli_plan_github_summary_requires_environment_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stderr = io.StringIO()
            with patch.dict(os.environ, {}, clear=True):
                with contextlib.redirect_stderr(stderr):
                    exit_code = main(
                        [
                            "plan",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--github-summary",
                        ]
                    )

            self.assertEqual(exit_code, 2)
            self.assertIn("GITHUB_STEP_SUMMARY is not set", stderr.getvalue())

    def test_cli_init_writes_valid_starter_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy" / "desired.json"

            exit_code = main(["init", "--output-file", str(output_path)])

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            desired = DesiredState.from_dict(payload)
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(desired.lf_tags), 2)
            self.assertEqual(len(desired.resource_tags), 1)
            self.assertEqual(len(desired.grants), 1)

    def test_cli_init_infers_yaml_format_from_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy" / "desired.yaml"

            exit_code = main(["init", "--output-file", str(output_path)])

            text = output_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertIn("lf_tags:", text)
            self.assertIn("domain:", text)
            self.assertIn("- analytics", text)
            self.assertIn("resource_tags:", text)
            self.assertFalse(text.lstrip().startswith("{"))

    def test_cli_init_json_format_overrides_yaml_extension(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "desired.yaml"

            exit_code = main(["init", "--output-file", str(output_path), "--format", "json"])

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertIn("lf_tags", payload)

    def test_cli_init_can_generate_blank_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "policy" / "desired.json"

            exit_code = main(["init", "--output-file", str(output_path), "--template", "blank"])

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            desired = DesiredState.from_dict(payload)
            self.assertEqual(exit_code, 0)
            self.assertEqual(len(desired.lf_tags), 0)
            self.assertEqual(len(desired.resource_tags), 0)
            self.assertEqual(len(desired.grants), 0)

    def test_cli_generate_writes_desired_state_from_python_policy(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            policy_path = tmp_path / "policy.py"
            output_path = tmp_path / "policy" / "desired.json"
            policy_path.write_text(_python_policy_source(), encoding="utf-8")

            exit_code = main(["generate", str(policy_path), "--output-file", str(output_path)])

            text = output_path.read_text(encoding="utf-8")
            desired = DesiredState.from_file(str(output_path))
            self.assertEqual(exit_code, 0)
            self.assertTrue(text.startswith("{"))
            self.assertEqual(len(desired.lf_tags), 2)
            self.assertEqual(len(desired.resource_tags), 3)
            self.assertEqual(len(desired.grants), 2)
            self.assertEqual(desired.grants[1].permissions, ("DESCRIBE", "SELECT"))

    def test_cli_generate_can_write_yaml_with_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            policy_path = tmp_path / "policy.py"
            output_path = tmp_path / "policy" / "desired.yaml"
            policy_path.write_text(_python_policy_source(), encoding="utf-8")

            exit_code = main(["generate", str(policy_path), "--output-file", str(output_path)])

            text = output_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertTrue(text.startswith("# Generated by policy.py. Do not edit directly."))
            self.assertIn("lf_tag_key_metadata:", text)

    def test_cli_generate_can_load_named_policy_factory(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            policy_path = tmp_path / "policy.py"
            output_path = tmp_path / "desired.json"
            policy_path.write_text(
                _python_policy_source(object_name="build_policy", as_factory=True),
                encoding="utf-8",
            )

            exit_code = main(
                [
                    "generate",
                    str(policy_path),
                    "--object",
                    "build_policy",
                    "--output-file",
                    str(output_path),
                ]
            )

            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["lf_tags"]["domain"], ["sales"])
            self.assertIn("lf_tag_key_metadata", payload)

    def test_cli_generate_check_passes_when_output_is_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            policy_path = tmp_path / "policy.py"
            output_path = tmp_path / "desired.json"
            policy_path.write_text(_python_policy_source(), encoding="utf-8")
            self.assertEqual(
                main(["generate", str(policy_path), "--output-file", str(output_path)]),
                0,
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["generate", str(policy_path), "--output-file", str(output_path), "--check"])

            self.assertEqual(exit_code, 0)
            self.assertIn("up to date", stdout.getvalue())

    def test_cli_generate_check_fails_when_output_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            policy_path = tmp_path / "policy.py"
            output_path = tmp_path / "desired.json"
            policy_path.write_text(_python_policy_source(), encoding="utf-8")
            output_path.write_text("{}", encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["generate", str(policy_path), "--output-file", str(output_path), "--check"])

            self.assertEqual(exit_code, 1)
            self.assertIn("out of date", stderr.getvalue())
            self.assertEqual(output_path.read_text(encoding="utf-8"), "{}")

    def test_cli_generate_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            policy_path = tmp_path / "policy.py"
            output_path = tmp_path / "desired.json"
            policy_path.write_text(_python_policy_source(), encoding="utf-8")
            output_path.write_text("{}", encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["generate", str(policy_path), "--output-file", str(output_path)])

            self.assertEqual(exit_code, 2)
            self.assertIn("already exists", stderr.getvalue())
            self.assertEqual(output_path.read_text(encoding="utf-8"), "{}")

    def test_cli_generate_reports_policy_syntax_errors_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.py"
            policy_path.write_text("def broken(:\n", encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["generate", str(policy_path)])

            error_text = stderr.getvalue()
            self.assertEqual(exit_code, 2)
            self.assertIn("could not execute policy file", error_text)
            self.assertIn("invalid syntax", error_text)
            self.assertNotIn("Traceback", error_text)

    def test_cli_generate_reports_policy_factory_errors_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.py"
            policy_path.write_text(
                """def build_policy():
    raise RuntimeError("missing environment")
""",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["generate", str(policy_path), "--object", "build_policy"])

            error_text = stderr.getvalue()
            self.assertEqual(exit_code, 2)
            self.assertIn("object 'build_policy' failed", error_text)
            self.assertIn("missing environment", error_text)
            self.assertNotIn("Traceback", error_text)

    def test_cli_generate_reports_policy_validation_paths_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.py"
            policy_path.write_text(
                """from lakeformation_guard.policy import LakePolicy, TagAssignmentScope, reader

policy = LakePolicy()
policy.tag_key("domain", values=["sales"], assignable_to=[TagAssignmentScope.DATABASE])
policy.group("dataconsumer", reader().where(domain="finance"))
""",
                encoding="utf-8",
            )

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["generate", str(policy_path)])

            error_text = stderr.getvalue()
            self.assertEqual(exit_code, 2)
            self.assertIn("POLICY_GROUP_UNDEFINED_TAG_VALUE", error_text)
            self.assertIn("groups.dataconsumer.filters.domain", error_text)
            self.assertIn("suggestion:", error_text)
            self.assertNotIn("Traceback", error_text)

    def test_cli_init_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "desired.json"
            output_path.write_text("{}", encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["init", "--output-file", str(output_path)])

            self.assertEqual(exit_code, 2)
            self.assertIn("already exists", stderr.getvalue())
            self.assertEqual(output_path.read_text(encoding="utf-8"), "{}")

    def test_cli_bootstrap_writes_policy_repo_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["bootstrap", "--output-dir", str(output_dir)])

            desired_path = output_dir / "policy" / "desired.json"
            policy_py_path = output_dir / "policy.py"
            schema_path = output_dir / "policy" / "lfguard.schema.json"
            workflow_path = output_dir / ".github" / "workflows" / "lfguard-policy.yml"
            pre_commit_path = output_dir / ".pre-commit-config.yaml"
            readme_path = output_dir / "README.md"
            desired = DesiredState.from_dict(json.loads(desired_path.read_text(encoding="utf-8")))
            policy_py = policy_py_path.read_text(encoding="utf-8")
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            workflow = workflow_path.read_text(encoding="utf-8")
            pre_commit = pre_commit_path.read_text(encoding="utf-8")
            readme = readme_path.read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn("lfguard policy bootstrap", stdout.getvalue())
            self.assertIn(str(policy_py_path), stdout.getvalue())
            self.assertIn("LakePolicy", policy_py)
            self.assertIn("table_creator", policy_py)
            self.assertIn("database_creator", policy_py)
            self.assertIn("catalog_admin", policy_py)
            self.assertNotIn('group("admin"', policy_py)
            self.assertEqual(len(desired.lf_tags), 2)
            self.assertEqual(schema["title"], "lfguard state")
            self.assertIn("python -m pip install lfguard", workflow)
            self.assertIn("lfguard generate policy.py --output-file policy/desired.json --check", workflow)
            self.assertIn("lfguard check", workflow)
            self.assertIn("--output-file artifacts/lfguard-check.md", workflow)
            self.assertIn("lfguard summary", workflow)
            self.assertIn("actions/upload-artifact@v6", workflow)
            self.assertIn("lfguard generate policy.py --output-file policy/desired.json --force", pre_commit)
            self.assertIn("lfguard check --desired policy/desired.json --fail-on-findings", pre_commit)
            self.assertIn("policy.py", pre_commit)
            self.assertIn("lfguard Policy Bootstrap", readme)
            self.assertIn("policy.py", readme)

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main([
                        "generate",
                        str(policy_py_path),
                        "--output-file",
                        str(desired_path),
                        "--force",
                    ]),
                    0,
                )
            regenerated = DesiredState.from_dict(json.loads(desired_path.read_text(encoding="utf-8")))
            self.assertEqual(desired.to_dict(), regenerated.to_dict())

    def test_cli_bootstrap_can_include_live_drift_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--include-live-drift",
                        "--aws-role-arn",
                        "arn:aws:iam::123456789012:role/LFGuardReadOnly",
                        "--aws-region",
                        "ap-northeast-2",
                    ]
                )

            workflow_path = output_dir / ".github" / "workflows" / "lfguard-live-drift.yml"
            iam_path = output_dir / "iam" / "lfguard-read-only.json"
            readme_path = output_dir / "README.md"
            workflow = workflow_path.read_text(encoding="utf-8")
            iam_policy = json.loads(iam_path.read_text(encoding="utf-8"))
            readme = readme_path.read_text(encoding="utf-8")
            actions = _policy_actions(iam_policy)

            self.assertEqual(exit_code, 0)
            self.assertIn(str(workflow_path), stdout.getvalue())
            self.assertIn("id-token: write", workflow)
            self.assertIn("arn:aws:iam::123456789012:role/LFGuardReadOnly", workflow)
            self.assertIn("aws-region: ap-northeast-2", workflow)
            self.assertIn('python -m pip install "lfguard[aws]"', workflow)
            self.assertIn("lfguard doctor --require aws", workflow)
            self.assertIn("lfguard generate policy.py --output-file policy/desired.json --check", workflow)
            self.assertIn("lfguard snapshot", workflow)
            self.assertIn("lfguard audit", workflow)
            self.assertIn("lfguard plan", workflow)
            self.assertIn("lfguard-live-drift-reports", workflow)
            self.assertIn("lakeformation:GetLFTag", actions)
            self.assertIn("lakeformation:ListPermissions", actions)
            self.assertNotIn("lakeformation:GrantPermissions", actions)
            self.assertIn(".github/workflows/lfguard-live-drift.yml", readme)
            self.assertIn("iam/lfguard-read-only.json", readme)
            self.assertIn("ap-northeast-2", readme)

    def test_cli_bootstrap_can_include_code_scanning_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--include-code-scanning",
                        "--aws-role-arn",
                        "arn:aws:iam::123456789012:role/LFGuardReadOnly",
                        "--aws-region",
                        "ap-northeast-2",
                    ]
                )

            workflow_path = output_dir / ".github" / "workflows" / "lfguard-code-scanning.yml"
            iam_path = output_dir / "iam" / "lfguard-read-only.json"
            readme_path = output_dir / "README.md"
            workflow = workflow_path.read_text(encoding="utf-8")
            iam_policy = json.loads(iam_path.read_text(encoding="utf-8"))
            readme = readme_path.read_text(encoding="utf-8")
            actions = _policy_actions(iam_policy)

            self.assertEqual(exit_code, 0)
            self.assertIn(str(workflow_path), stdout.getvalue())
            self.assertIn("security-events: write", workflow)
            self.assertIn("github/codeql-action/upload-sarif@v3", workflow)
            self.assertIn("category: lfguard-lint", workflow)
            self.assertIn("category: lfguard-audit", workflow)
            self.assertIn("arn:aws:iam::123456789012:role/LFGuardReadOnly", workflow)
            self.assertIn("aws-region: ap-northeast-2", workflow)
            self.assertIn('python -m pip install "lfguard[aws]"', workflow)
            self.assertIn("lfguard doctor --require aws", workflow)
            self.assertIn("lfguard generate policy.py --output-file policy/desired.json --check", workflow)
            self.assertIn("lfguard snapshot", workflow)
            self.assertIn("lfguard check", workflow)
            self.assertIn("lfguard audit", workflow)
            self.assertIn("lfguard-code-scanning-reports", workflow)
            self.assertIn("lakeformation:GetLFTag", actions)
            self.assertNotIn("lakeformation:GrantPermissions", actions)
            self.assertIn(".github/workflows/lfguard-code-scanning.yml", readme)
            self.assertIn("iam/lfguard-read-only.json", readme)
            self.assertIn("upload SARIF", readme)

    def test_cli_bootstrap_can_include_review_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--include-review-template",
                        "--policy-owner",
                        "@example/data-platform",
                    ]
                )

            codeowners_path = output_dir / ".github" / "CODEOWNERS"
            pr_template_path = output_dir / ".github" / "pull_request_template.md"
            readme_path = output_dir / "README.md"
            codeowners = codeowners_path.read_text(encoding="utf-8")
            pr_template = pr_template_path.read_text(encoding="utf-8")
            readme = readme_path.read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn(str(codeowners_path), stdout.getvalue())
            self.assertIn(str(pr_template_path), stdout.getvalue())
            self.assertIn("policy/* @example/data-platform", codeowners)
            self.assertIn(".github/workflows/lfguard-*.yml @example/data-platform", codeowners)
            self.assertIn("# Lake Formation Policy Change", pr_template)
            self.assertIn("lfguard check --desired policy/desired.json", pr_template)
            self.assertIn("--allow-permission-revokes", pr_template)
            self.assertIn(".github/CODEOWNERS", readme)
            self.assertIn("@example/data-platform", readme)

    def test_cli_bootstrap_can_include_editor_config_for_json_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--include-editor-config",
                    ]
                )

            settings_path = output_dir / ".vscode" / "settings.json"
            readme_path = output_dir / "README.md"
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
            readme = readme_path.read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn(str(settings_path), stdout.getvalue())
            self.assertFalse((output_dir / ".vscode" / "extensions.json").exists())
            self.assertEqual(
                settings["json.schemas"],
                [
                    {
                        "fileMatch": ["policy/desired.json", "snapshots/*.json"],
                        "url": "./policy/lfguard.schema.json",
                    }
                ],
            )
            self.assertIn(".vscode/settings.json", readme)
            self.assertIn("Editor Validation", readme)
            self.assertIn("policy/desired.json", readme)

    def test_cli_bootstrap_can_write_yaml_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(["bootstrap", "--output-dir", str(output_dir), "--format", "yaml"])

            workflow = (output_dir / ".github" / "workflows" / "lfguard-policy.yml").read_text(encoding="utf-8")
            pre_commit = (output_dir / ".pre-commit-config.yaml").read_text(encoding="utf-8")
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertTrue((output_dir / "policy" / "desired.yaml").exists())
            self.assertFalse((output_dir / "policy" / "desired.json").exists())
            self.assertTrue((output_dir / "policy.py").exists())
            self.assertIn('python -m pip install "lfguard[yaml]"', workflow)
            self.assertIn("lfguard doctor --require yaml", workflow)
            self.assertIn("lfguard generate policy.py --output-file policy/desired.yaml --check", workflow)
            self.assertIn("lfguard generate policy.py --output-file policy/desired.yaml --force", pre_commit)
            self.assertIn("lfguard check --desired policy/desired.yaml --fail-on-findings", pre_commit)
            self.assertIn('python -m pip install "lfguard[yaml]"', readme)

    def test_cli_bootstrap_blank_yaml_layout_is_generated_check_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(
                    main([
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--template",
                        "blank",
                        "--format",
                        "yaml",
                    ]),
                    0,
                )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "generate",
                        str(output_dir / "policy.py"),
                        "--output-file",
                        str(output_dir / "policy" / "desired.yaml"),
                        "--check",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("up to date", stdout.getvalue())

    def test_cli_bootstrap_live_drift_installs_yaml_and_aws_extras_for_yaml_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--format",
                        "yaml",
                        "--include-live-drift",
                    ]
                )

            workflow = (output_dir / ".github" / "workflows" / "lfguard-live-drift.yml").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn('python -m pip install "lfguard[aws,yaml]"', workflow)
            self.assertIn("lfguard doctor --require aws --require yaml", workflow)
            self.assertIn("--desired policy/desired.yaml", workflow)

    def test_cli_bootstrap_code_scanning_installs_yaml_and_aws_extras_for_yaml_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--format",
                        "yaml",
                        "--include-code-scanning",
                    ]
                )

            workflow = (output_dir / ".github" / "workflows" / "lfguard-code-scanning.yml").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn('python -m pip install "lfguard[aws,yaml]"', workflow)
            self.assertIn("lfguard doctor --require aws --require yaml", workflow)
            self.assertIn("--desired policy/desired.yaml", workflow)

    def test_cli_bootstrap_review_template_uses_yaml_policy_path_for_yaml_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--format",
                        "yaml",
                        "--include-review-template",
                    ]
                )

            pr_template = (output_dir / ".github" / "pull_request_template.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn("lfguard check --desired policy/desired.yaml", pr_template)
            self.assertIn("lfguard summary --desired policy/desired.yaml", pr_template)
            self.assertNotIn("policy/desired.json", pr_template)

    def test_cli_bootstrap_editor_config_recommends_yaml_extension_for_yaml_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "bootstrap",
                        "--output-dir",
                        str(output_dir),
                        "--format",
                        "yaml",
                        "--include-editor-config",
                    ]
                )

            settings = json.loads((output_dir / ".vscode" / "settings.json").read_text(encoding="utf-8"))
            extensions = json.loads((output_dir / ".vscode" / "extensions.json").read_text(encoding="utf-8"))
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertEqual(
                settings["yaml.schemas"],
                {
                    "./policy/lfguard.schema.json": [
                        "policy/desired.yaml",
                        "snapshots/*.yaml",
                        "snapshots/*.yml",
                    ]
                },
            )
            self.assertEqual(extensions["recommendations"], ["redhat.vscode-yaml"])
            self.assertIn(".vscode/extensions.json", readme)
            self.assertIn("policy/desired.yaml", readme)

    def test_cli_bootstrap_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "policy-repo"

            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(["bootstrap", "--output-dir", str(output_dir)]), 0)
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["bootstrap", "--output-dir", str(output_dir)])

            self.assertEqual(exit_code, 2)
            self.assertIn("already exists", stderr.getvalue())

    def test_cli_sample_writes_runnable_offline_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["sample", "--output-dir", str(output_dir)])

            desired_path = output_dir / "desired.json"
            current_path = output_dir / "current-snapshot.json"
            readme_path = output_dir / "README.md"
            desired = DesiredState.from_dict(json.loads(desired_path.read_text(encoding="utf-8")))
            current = CurrentState.from_dict(json.loads(current_path.read_text(encoding="utf-8")))
            sample_readme = readme_path.read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn("lfguard plan --desired", stdout.getvalue())
            self.assertIn("lfguard check --desired", stdout.getvalue())
            self.assertIn("README.md", stdout.getvalue())
            self.assertEqual(len(desired.lf_tags), 2)
            self.assertEqual(len(current.lf_tags), 2)
            self.assertEqual(len(desired.data_cells_filters), 1)
            self.assertEqual(len(current.data_cells_filters), 1)
            self.assertIn("lfguard Demo", sample_readme)
            self.assertIn("lfguard check --desired desired.json --current-snapshot current-snapshot.json", sample_readme)
            self.assertIn("lfguard summary --desired desired.json", sample_readme)
            self.assertIn("lfguard audit --desired desired.json", sample_readme)
            self.assertIn("lfguard plan --desired desired.json", sample_readme)
            self.assertIn("--data-cells-filter orders_public", sample_readme)
            self.assertIn("--current-cache .lfguard/prod-us-east-1-111122223333-current.json", sample_readme)
            self.assertEqual(lint_desired(desired), ())

            plan_stdout = io.StringIO()
            with contextlib.redirect_stdout(plan_stdout):
                plan_exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                    ]
                )

            self.assertEqual(plan_exit_code, 0)
            self.assertIn("Plan: 4 change(s), 4 safe, 0 destructive.", plan_stdout.getvalue())

    def test_cli_sample_can_include_github_actions_demo_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["sample", "--output-dir", str(output_dir), "--include-ci"])

            workflow_path = output_dir / ".github" / "workflows" / "lfguard-demo.yml"
            workflow = workflow_path.read_text(encoding="utf-8")
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn(str(workflow_path), stdout.getvalue())
            self.assertIn("GitHub Actions Demo", readme)
            self.assertIn("python -m pip install lfguard", workflow)
            self.assertIn("lfguard check", workflow)
            self.assertIn("--desired lfguard-demo/desired.json", workflow)
            self.assertIn("--current-snapshot lfguard-demo/current-snapshot.json", workflow)
            self.assertIn("--output-file artifacts/lfguard-check.md", workflow)
            self.assertIn("actions/upload-artifact@v6", workflow)

    def test_cli_sample_can_write_yaml_demo_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["sample", "--output-dir", str(output_dir), "--format", "yaml"])

            desired_path = output_dir / "desired.yaml"
            current_path = output_dir / "current-snapshot.yaml"
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertTrue(desired_path.exists())
            self.assertTrue(current_path.exists())
            self.assertFalse((output_dir / "desired.json").exists())
            self.assertIn("lfguard[yaml]", readme)
            self.assertIn("desired.yaml", readme)
            self.assertIn("current-snapshot.yaml", readme)

    def test_cli_sample_ci_workflow_installs_yaml_extra_for_yaml_demo(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            with contextlib.redirect_stdout(io.StringIO()):
                exit_code = main(["sample", "--output-dir", str(output_dir), "--format", "yaml", "--include-ci"])

            workflow = (output_dir / ".github" / "workflows" / "lfguard-demo.yml").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            self.assertIn('python -m pip install "lfguard[yaml]"', workflow)
            self.assertIn("--desired lfguard-demo/desired.yaml", workflow)
            self.assertIn("--current-snapshot lfguard-demo/current-snapshot.yaml", workflow)

    def test_cli_sample_can_write_both_json_and_yaml_demo_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["sample", "--output-dir", str(output_dir), "--format", "both"])
            readme = (output_dir / "README.md").read_text(encoding="utf-8")

            self.assertEqual(exit_code, 0)
            for name in ("desired.json", "current-snapshot.json", "desired.yaml", "current-snapshot.yaml"):
                self.assertTrue((output_dir / name).exists(), name)
            self.assertIn("both JSON and YAML state files", readme)
            self.assertIn("YAML state files require", readme)

    def test_cli_sample_refuses_to_overwrite_without_force(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "lfguard-demo"
            output_dir.mkdir()
            desired_path = output_dir / "desired.json"
            desired_path.write_text("{}", encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["sample", "--output-dir", str(output_dir)])

            self.assertEqual(exit_code, 2)
            self.assertIn("already exists", stderr.getvalue())
            self.assertEqual(desired_path.read_text(encoding="utf-8"), "{}")

    def test_cli_schema_outputs_json_schema(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["schema"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["$schema"], "https://json-schema.org/draft/2020-12/schema")
        self.assertEqual(payload["title"], "lfguard state")
        self.assertIn("lfTagPolicyResource", payload["$defs"])

    def test_cli_doctor_outputs_json_report(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["doctor", "--output", "json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertIn("version", payload)
        self.assertIn("python", payload)
        self.assertEqual(payload["optional_dependencies"]["boto3"]["extra"], "aws")
        self.assertEqual(payload["optional_dependencies"]["PyYAML"]["extra"], "yaml")
        self.assertFalse(payload["aws_calls_made"])

    def test_cli_doctor_outputs_text_report(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["doctor"])

        self.assertEqual(exit_code, 0)
        self.assertIn("lfguard:", stdout.getvalue())
        self.assertIn("Optional dependencies:", stdout.getvalue())
        self.assertIn("No AWS calls were made.", stdout.getvalue())

    def test_cli_doctor_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "artifacts" / "doctor.json"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["doctor", "--output", "json", "--output-file", str(output_path)])

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertIn("version", payload)
            self.assertIn("optional_dependencies", payload)
            self.assertFalse(payload["aws_calls_made"])

    def test_cli_doctor_can_fail_when_required_extra_is_missing(self):
        stdout = io.StringIO()
        with patch("lakeformation_guard.cli.util.find_spec", return_value=None):
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["doctor", "--require", "yaml", "--output", "json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["required_extras"], ["yaml"])
        self.assertEqual(payload["missing_required_extras"], ["yaml"])
        self.assertFalse(payload["optional_dependencies"]["PyYAML"]["installed"])

    def test_cli_permissions_outputs_read_only_policy_by_default(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["permissions"])

        payload = json.loads(stdout.getvalue())
        actions = _policy_actions(payload)
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["Version"], "2012-10-17")
        self.assertIn("lakeformation:GetLFTag", actions)
        self.assertIn("lakeformation:GetResourceLFTags", actions)
        self.assertIn("lakeformation:ListPermissions", actions)
        self.assertNotIn("lakeformation:GrantPermissions", actions)

    def test_cli_permissions_can_include_glue_read_and_write_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "artifacts" / "permissions.md"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "permissions",
                        "--template",
                        "additive-apply",
                        "--include-glue-read",
                        "--output",
                        "markdown",
                        "--output-file",
                        str(output_path),
                    ]
                )

            text = output_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("### lfguard permissions: additive-apply", text)
            self.assertIn("lakeformation:GrantPermissions", text)
            self.assertIn("glue:GetTable", text)
            self.assertNotIn("lakeformation:RevokePermissions", text)

    def test_cli_permissions_destructive_apply_policy_includes_revoke_actions(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["permissions", "--template", "destructive-apply", "--output", "json"])

        actions = _policy_actions(json.loads(stdout.getvalue()))
        self.assertEqual(exit_code, 0)
        self.assertIn("lakeformation:RemoveLFTagsFromResource", actions)
        self.assertIn("lakeformation:RevokePermissions", actions)

    def test_cli_permissions_check_outputs_json_and_returns_success_when_allowed(self):
        fake_checker = _FakePermissionChecker(
            IAMPermissionCheckReport(
                template="read-only",
                include_glue_read=False,
                principal_arn="arn:aws:iam::111122223333:role/LfguardReadOnly",
                caller_arn="arn:aws:sts::111122223333:assumed-role/LfguardReadOnly/session",
                actions=(
                    IAMActionCheck("lakeformation:GetLFTag", "allowed", True),
                    IAMActionCheck("lakeformation:ListPermissions", "allowed", True),
                ),
            )
        )

        stdout = io.StringIO()
        with patch("lakeformation_guard.cli.AWSIAMPermissionChecker.from_boto3", return_value=fake_checker) as factory:
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "permissions",
                        "--check",
                        "--template",
                        "read-only",
                        "--profile",
                        "prod",
                        "--region",
                        "us-east-1",
                        "--output",
                        "json",
                    ]
                )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        factory.assert_called_once_with(profile_name="prod", region_name="us-east-1")
        self.assertEqual(fake_checker.principal_arn, None)
        self.assertEqual(payload["schema_version"], "lfguard.permissions-check.v1")
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["summary"], {"total": 2, "allowed": 2, "denied": 0})
        self.assertEqual(payload["principal_arn"], "arn:aws:iam::111122223333:role/LfguardReadOnly")

    def test_cli_permissions_check_returns_failure_when_action_is_denied(self):
        fake_checker = _FakePermissionChecker(
            IAMPermissionCheckReport(
                template="additive-apply",
                include_glue_read=True,
                principal_arn="arn:aws:iam::111122223333:role/LfguardApply",
                caller_arn=None,
                actions=(
                    IAMActionCheck("lakeformation:GetLFTag", "allowed", True),
                    IAMActionCheck("lakeformation:GrantPermissions", "implicitDeny", False),
                    IAMActionCheck("glue:GetTable", "explicitDeny", False),
                ),
            )
        )

        stdout = io.StringIO()
        with patch("lakeformation_guard.cli.AWSIAMPermissionChecker.from_boto3", return_value=fake_checker):
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "permissions",
                        "--check",
                        "--template",
                        "additive-apply",
                        "--include-glue-read",
                        "--principal-arn",
                        "arn:aws:iam::111122223333:role/LfguardApply",
                        "--output",
                        "markdown",
                    ]
                )

        self.assertEqual(exit_code, 1)
        self.assertEqual(fake_checker.principal_arn, "arn:aws:iam::111122223333:role/LfguardApply")
        self.assertIn("### lfguard permissions check: additive-apply", stdout.getvalue())
        self.assertIn("Result: **fail**", stdout.getvalue())
        self.assertIn("lakeformation:GrantPermissions", stdout.getvalue())
        self.assertIn("glue:GetTable", stdout.getvalue())

    def test_cli_completion_outputs_bash_script_by_default(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["completion"])

        script = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("complete -F _lfguard_complete lfguard", script)
        self.assertNotIn("aws-lakeformation-guard", script)
        self.assertIn("bootstrap", script)
        self.assertIn("generate", script)
        self.assertIn("--object", script)
        self.assertIn("--check", script)
        self.assertIn("--include-code-scanning", script)
        self.assertIn("--include-review-template", script)
        self.assertIn("--include-editor-config", script)
        self.assertIn("--include-glue-read", script)

    def test_cli_completion_outputs_zsh_script(self):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = main(["completion", "--shell", "zsh"])

        script = stdout.getvalue()
        self.assertEqual(exit_code, 0)
        self.assertIn("#compdef lfguard", script)
        self.assertNotIn("aws-lakeformation-guard", script)
        self.assertIn("'permissions:permissions'", script)
        self.assertIn("compadd '--template'", script)

    def test_cli_completion_outputs_fish_script_to_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "completions" / "lfguard.fish"

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["completion", "--shell", "fish", "--output-file", str(output_path)])

            script = output_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("complete -c lfguard -f", script)
            self.assertNotIn("aws-lakeformation-guard", script)
            self.assertIn("__fish_seen_subcommand_from permissions", script)
            self.assertIn("-l include-glue-read", script)

    def test_cli_check_outputs_json_validation_and_lint_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "resource_tags": [], "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "check",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertTrue(payload["valid"])
            self.assertEqual(payload["desired"]["lf_tags"], 1)
            self.assertEqual(payload["current_snapshot"]["lf_tags"], 0)
            self.assertEqual(payload["lint"]["summary"], {"total": 0, "errors": 0, "warnings": 0})

    def test_cli_check_can_fail_on_lint_findings_after_writing_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            output_path = tmp_path / "artifacts" / "lfguard-check.md"
            summary_path = tmp_path / "summary.md"
            desired_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "check",
                            "--desired",
                            str(desired_path),
                            "--output",
                            "markdown",
                            "--output-file",
                            str(output_path),
                            "--github-summary",
                            "--fail-on-findings",
                        ]
                    )

            report = output_path.read_text(encoding="utf-8")
            summary = summary_path.read_text(encoding="utf-8")
            self.assertEqual(exit_code, 1)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn("### lfguard check", report)
            self.assertIn("DESIRED_STATE_EMPTY", report)
            self.assertIn("### lfguard check", summary)
            self.assertIn("DESIRED_STATE_EMPTY", summary)

    def test_cli_validate_outputs_json_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "resource_tags": [
                            {
                                "resource": {"kind": "database", "database": "analytics"},
                                "tags": {"sensitivity": ["internal"]},
                            }
                        ],
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "database", "database": "analytics"},
                                "permissions": ["DESCRIBE"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "validate",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(
                payload,
                {
                    "current_snapshot": {
                        "data_cells_filters": 0,
                        "grants": 0,
                        "lf_tag_expressions": 0,
                        "lf_tags": 0,
                        "resource_tags": 0,
                        "valid": True,
                    },
                    "desired": {
                        "data_cells_filters": 0,
                        "grants": 1,
                        "lf_tag_expressions": 0,
                        "lf_tags": 1,
                        "resource_tags": 1,
                        "valid": True,
                    },
                },
            )

    def test_cli_validate_writes_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "validate.txt"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "resource_tags": [], "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "validate",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output-file",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("Desired state is valid", report)
            self.assertIn("Current snapshot is valid", report)

    def test_cli_validate_rejects_duplicate_lf_tag_expression_identity_in_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")
            current_path.write_text(
                json.dumps(
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
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "validate",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "current snapshot: Duplicate LF-Tag expression identity: "
                "lf_tag_expression:catalog=111111111111:name=shared",
                stderr.getvalue(),
            )

    def test_cli_validate_rejects_duplicate_lf_tag_identity_in_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")
            current_path.write_text(
                json.dumps(
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
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "validate",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "current snapshot: Duplicate LF-Tag identity: lf_tag:catalog=111111111111:key=domain",
                stderr.getvalue(),
            )

    def test_cli_validate_rejects_duplicate_lf_tag_key_metadata_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"domain": ["sales"]},
                        "lf_tag_key_metadata": [
                            {
                                "key": "domain",
                                "catalog_id": "111111111111",
                                "assignable_to": ["table"],
                            },
                            {
                                "key": "domain",
                                "catalog_id": "111111111111",
                                "assignable_to": ["column"],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            stderr = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exit_code = main(["validate", "--desired", str(desired_path)])

            self.assertEqual(exit_code, 2)
            self.assertEqual(stdout.getvalue(), "")
            self.assertIn(
                "desired state: Duplicate LF-Tag key metadata identity: "
                "lf_tag_key_metadata:catalog=111111111111:key=domain",
                stderr.getvalue(),
            )

    def test_lint_desired_api_reports_undefined_tag_references(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"domain": ["sales"], "sensitivity": ["restricted"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"], "sensitivity": ["external"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual(
            [finding.code for finding in findings],
            [
                "RESOURCE_TAG_KEY_UNDEFINED",
                "RESOURCE_TAG_VALUE_UNDEFINED",
                "LF_TAG_POLICY_KEY_UNDEFINED",
                "LF_TAG_POLICY_VALUE_UNDEFINED",
            ],
        )

    def test_lint_desired_api_reports_lf_tag_behavior_that_will_not_match_aws(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"Sensitivity": ["Internal", "Restricted"]},
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"Sensitivity": ["Internal", "Restricted"]},
                    }
                ],
                "grants": [],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual(
            [finding.code for finding in findings],
            [
                "LF_TAG_CASE_NORMALIZATION",
                "RESOURCE_TAG_MULTIPLE_VALUES",
                "LF_TAG_CASE_NORMALIZATION",
            ],
        )
        self.assertEqual(findings[1].severity, "error")
        self.assertIn("only one value", findings[1].message)

    def test_lint_desired_api_allows_lf_tag_policy_wildcard_value(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"module": ["orders"]},
                "resource_tags": [],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "DATABASE",
                            "expression": {"module": ["*"]},
                        },
                        "permissions": ["DESCRIBE"],
                    }
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_POLICY_WILDCARD_VALUE"])
        self.assertEqual(findings[0].severity, "warning")

    def test_lint_desired_api_reports_governance_antipatterns(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "resource_tags": [],
                "grants": [
                    {
                        "principal": "IAMAllowedPrincipals",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"]},
                        },
                        "permissions": ["SELECT"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/DataAdmin",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["CREATE_TABLE"],
                        "grantable_permissions": ["CREATE_TABLE"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/Owner",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SUPER_USER"],
                    },
                ],
            }
        )

        findings = lint_desired(desired)
        codes = [finding.code for finding in findings]

        self.assertIn("BROAD_PRINCIPAL_GRANT", codes)
        self.assertIn("MUTATING_PERMISSION_REVIEW", codes)
        self.assertIn("GRANTABLE_PERMISSION_REVIEW", codes)
        self.assertIn("NAMED_RESOURCE_GRANT_REVIEW", codes)
        self.assertIn("BROAD_PERMISSION_GRANT", codes)
        self.assertEqual(
            {finding.code for finding in findings if finding.severity == "error"},
            {
                "BROAD_PRINCIPAL_GRANT",
                "BROAD_PERMISSION_GRANT",
                "GRANTABLE_PERMISSION_REVIEW",
                "MUTATING_PERMISSION_REVIEW",
                "NAMED_RESOURCE_GRANT_REVIEW",
            },
        )

    def test_lint_policy_exceptions_suppress_only_matching_governance_rules(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/DataAdmin",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["ALL"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/OtherAdmin",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["ALL"],
                    },
                ],
                "exceptions": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/DataAdmin",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["ALL"],
                        "rules": ["allow_broad_permissions", "allow_named_resource_grants"],
                        "reason": "break-glass database administration",
                        "expires_at": "2099-12-31",
                        "approved_by": "data-governance",
                    }
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual(
            [(finding.code, finding.details["principal"]) for finding in findings],
            [
                ("BROAD_PERMISSION_GRANT", "arn:aws:iam::111122223333:role/OtherAdmin"),
                ("NAMED_RESOURCE_GRANT_REVIEW", "arn:aws:iam::111122223333:role/OtherAdmin"),
            ],
        )

    def test_lint_reports_expired_policy_exception_and_does_not_suppress(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/DataAdmin",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["ALL"],
                    }
                ],
                "exceptions": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/DataAdmin",
                        "rules": ["allow_broad_permissions", "allow_named_resource_grants"],
                        "reason": "old temporary access",
                        "expires_at": "2000-01-01",
                        "owner": "data-platform",
                    }
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual(
            [finding.code for finding in findings],
            [
                "POLICY_EXCEPTION_EXPIRED",
                "BROAD_PERMISSION_GRANT",
                "NAMED_RESOURCE_GRANT_REVIEW",
            ],
        )

    def test_lint_desired_api_blocks_partial_column_permission_conflicts(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"sensitivity": ["internal"]},
                "resource_tags": [],
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/MwaaExecution",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"sensitivity": ["internal"]},
                        },
                        "permissions": ["SELECT", "DELETE", "INSERT"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/SplitPolicy",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"sensitivity": ["internal"]},
                        },
                        "permissions": ["SELECT"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/SplitPolicy",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"sensitivity": ["internal"]},
                        },
                        "permissions": ["INSERT"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/ColumnWriter",
                        "resource": {
                            "kind": "table_with_columns",
                            "database": "analytics",
                            "table": "users",
                            "columns": ["login_id"],
                        },
                        "permissions": ["SELECT", "DELETE"],
                    },
                ],
            }
        )

        findings = lint_desired(desired)
        findings_by_code = {finding.code: finding for finding in findings}

        self.assertIn("LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT", findings_by_code)
        self.assertIn("LF_TAG_POLICY_COMBINED_TABLE_SELECT_MUTATION_CONFLICT", findings_by_code)
        self.assertIn("COLUMN_FILTER_MUTATING_PERMISSION_CONFLICT", findings_by_code)
        self.assertEqual(findings_by_code["LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT"].severity, "error")
        self.assertEqual(
            findings_by_code["LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT"].details["conflicting_permissions"],
            ["DELETE", "INSERT"],
        )

    def test_lint_uses_named_lf_tag_expression_body_for_column_narrowing(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": [
                    {
                        "key": "domain",
                        "catalog_id": "222222222222",
                        "values": ["sales"],
                    }
                ],
                "lf_tag_key_metadata": [
                    {
                        "key": "domain",
                        "catalog_id": "222222222222",
                        "assignable_to": ["table"],
                    }
                ],
                "lf_tag_expressions": [
                    {
                        "name": "sales_tables",
                        "catalog_id": "222222222222",
                        "expression": {"domain": ["sales"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/NamedPolicy",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "222222222222",
                            "resource_type": "TABLE",
                            "expression_name": "sales_tables",
                        },
                        "permissions": ["SELECT", "DELETE", "INSERT"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/SplitNamedPolicy",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "222222222222",
                            "resource_type": "TABLE",
                            "expression_name": "sales_tables",
                        },
                        "permissions": ["SELECT"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/SplitNamedPolicy",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "222222222222",
                            "resource_type": "TABLE",
                            "expression_name": "sales_tables",
                        },
                        "permissions": ["INSERT"],
                    },
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual(findings, ())

    def test_lint_allows_safe_data_cells_filter_select_grants(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/FilteredReader",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        self.assertEqual(lint_desired(desired), ())

    def test_lint_flags_data_cells_filter_mutating_grants(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/FilteredWriter",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT", "DROP"],
                    }
                ],
            }
        )

        findings = lint_desired(desired)
        codes = [finding.code for finding in findings]

        self.assertIn("COLUMN_FILTER_MUTATING_PERMISSION_CONFLICT", codes)
        self.assertNotIn("NAMED_RESOURCE_GRANT_REVIEW", codes)
        self.assertEqual(
            next(
                finding
                for finding in findings
                if finding.code == "COLUMN_FILTER_MUTATING_PERMISSION_CONFLICT"
            ).details["resource"]["kind"],
            "data_cells_filter",
        )

    def test_lint_flags_duplicate_data_cells_filter_identity(self):
        desired = DesiredState.from_dict(
            {
                "data_cells_filters": [
                    {
                        "name": "orders_public",
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
                    },
                ]
            }
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["DATA_CELLS_FILTER_DUPLICATE_IDENTITY"])
        self.assertIn(
            "data_cells_filter:catalog=222222222222:database=analytics:table=orders:name=orders_public",
            findings[0].target,
        )

    def test_audit_reports_data_cells_filter_missing_drift_and_unmanaged(self):
        desired = DesiredState.from_dict(
            {
                "data_cells_filters": [
                    {
                        "name": "orders_internal",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "row_filter": "sensitivity <> 'restricted'",
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

        findings = audit(desired, current)

        self.assertEqual(
            [finding.code for finding in findings],
            ["DATA_CELLS_FILTER_MISSING", "DATA_CELLS_FILTER_DRIFT", "DATA_CELLS_FILTER_UNMANAGED"],
        )
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[1].details["desired"]["all_rows"], True)
        self.assertEqual(findings[2].severity, "warning")

    def test_cli_lint_outputs_json_and_can_fail_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "resource_tags": [
                            {
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "tags": {"sensitivity": ["restricted"]},
                            }
                        ],
                        "grants": [],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "lint",
                        "--desired",
                        str(desired_path),
                        "--output",
                        "json",
                        "--fail-on-findings",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 1)
            self.assertEqual(payload["summary"], {"total": 1, "errors": 1, "warnings": 0})
            self.assertEqual(payload["findings"][0]["code"], "RESOURCE_TAG_VALUE_UNDEFINED")

    def test_cli_lint_outputs_sarif(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"]},
                        "resource_tags": [
                            {
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "tags": {"sensitivity": ["restricted"]},
                            }
                        ],
                        "grants": [],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["lint", "--desired", str(desired_path), "--output", "sarif"])

            payload = json.loads(stdout.getvalue())
            result = payload["runs"][0]["results"][0]
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["version"], "2.1.0")
            self.assertEqual(payload["runs"][0]["tool"]["driver"]["name"], "lfguard")
            self.assertEqual(result["ruleId"], "RESOURCE_TAG_VALUE_UNDEFINED")
            self.assertEqual(result["level"], "error")
            self.assertEqual(
                result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"],
                str(desired_path),
            )

    def test_cli_lint_warning_only_can_pass_when_failing_on_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            desired_path = Path(tmp) / "desired.json"
            desired_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "lint",
                        "--desired",
                        str(desired_path),
                        "--output",
                        "markdown",
                        "--fail-on-findings",
                        "--fail-on-severity",
                        "error",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard lint", stdout.getvalue())
            self.assertIn("DESIRED_STATE_EMPTY", stdout.getvalue())

    def test_cli_lint_writes_github_summary_before_failing_on_findings(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            summary_path = tmp_path / "summary.md"
            desired_path.write_text(json.dumps({"lf_tags": {}, "resource_tags": [], "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "lint",
                            "--desired",
                            str(desired_path),
                            "--fail-on-findings",
                            "--github-summary",
                        ]
                    )

            self.assertEqual(exit_code, 1)
            self.assertIn("Lint findings:", stdout.getvalue())
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("### lfguard lint", summary)
            self.assertIn("DESIRED_STATE_EMPTY", summary)

    def test_cli_summary_outputs_policy_inventory_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(
                json.dumps(
                    {
                        "lf_tags": {"sensitivity": ["internal"], "domain": ["sales"]},
                        "lf_tag_expressions": [
                            {
                                "name": "shared",
                                "catalog_id": "111111111111",
                                "expression": {"domain": ["sales"]},
                            },
                            {
                                "name": "shared",
                                "catalog_id": "222222222222",
                                "expression": {"sensitivity": ["internal"]},
                            },
                        ],
                        "resource_tags": [
                            {
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "tags": {"sensitivity": ["internal"], "domain": ["sales"]},
                            }
                        ],
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "database", "database": "analytics"},
                                "permissions": ["DESCRIBE"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "summary",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["desired"]["lf_tag_keys"], ["domain", "sensitivity"])
            self.assertEqual(payload["desired"]["lf_tag_expression_names"], ["shared", "shared"])
            self.assertEqual(
                payload["desired"]["lf_tag_expression_ids"],
                [
                    "lf_tag_expression:catalog=111111111111:name=shared",
                    "lf_tag_expression:catalog=222222222222:name=shared",
                ],
            )
            self.assertEqual(payload["desired"]["resource_kinds"], {"table": 1})
            self.assertEqual(payload["desired"]["grant_principals"], ["role"])
            self.assertEqual(payload["desired"]["grant_resource_kinds"], {"database": 1})
            self.assertEqual(payload["desired"]["permissions"], ["DESCRIBE"])
            self.assertEqual(payload["current_snapshot"]["lf_tags"], 1)

    def test_cli_summary_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            desired_path = Path(tmp) / "desired.json"
            desired_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(["summary", "--desired", str(desired_path), "--output", "markdown"])

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard summary", stdout.getvalue())
            self.assertIn("| LF-Tag definitions | 1 (sensitivity) |", stdout.getvalue())

    def test_cli_summary_writes_github_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            summary_path = tmp_path / "summary.md"
            desired_path.write_text(json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(summary_path)}):
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["summary", "--desired", str(desired_path), "--github-summary"])

            self.assertEqual(exit_code, 0)
            self.assertIn("Desired summary:", stdout.getvalue())
            summary = summary_path.read_text(encoding="utf-8")
            self.assertIn("### lfguard summary", summary)
            self.assertIn("| LF-Tag definitions | 1 (sensitivity) |", summary)

    def test_cli_version_outputs_short_command_name(self):
        stdout = io.StringIO()
        with self.assertRaises(SystemExit) as raised:
            with contextlib.redirect_stdout(stdout):
                main(["--version"])

        self.assertEqual(raised.exception.code, 0)
        self.assertEqual(stdout.getvalue().strip(), "lfguard {}".format(__version__))

    def test_cli_snapshot_outputs_live_current_state_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            output_path = tmp_path / "snapshots" / "prod-current.json"
            desired_path.write_text(
                json.dumps(
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
                ),
                encoding="utf-8",
            )
            current = CurrentState.from_dict(
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

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                adapter_class.from_boto3.return_value.load_current_state_for.return_value = current
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "snapshot",
                            "--desired",
                            str(desired_path),
                            "--profile",
                            "prod",
                            "--output-file",
                            str(output_path),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            adapter_class.from_boto3.assert_called_once_with(
                profile_name="prod",
                region_name=None,
                catalog_id=None,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["lf_tags"], {"sensitivity": ["internal"]})
            self.assertEqual(payload["grants"][0]["resource"]["database"], "analytics")

    def test_cli_apply_dry_run_writes_report_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "lfguard-apply.md"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "apply",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "markdown",
                        "--output-file",
                        str(output_path),
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            report = output_path.read_text(encoding="utf-8")
            self.assertIn("Dry run: no changes applied.", report)
            self.assertIn("### lfguard plan", report)
            self.assertIn("| change_001 | safe | lf_tag.create | lf_tag:sensitivity | LF-Tag is missing |", report)

    def test_cli_apply_execute_writes_json_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            output_path = tmp_path / "artifacts" / "lfguard-apply.json"
            desired_path.write_text(
                json.dumps({"lf_tags": {"sensitivity": ["internal"]}, "grants": []}),
                encoding="utf-8",
            )
            current_path.write_text(json.dumps({"lf_tags": {}, "grants": []}), encoding="utf-8")
            apply_result = ApplyResult(
                action="lf_tag.create",
                target="lf_tag:sensitivity",
                applied=True,
                response={"ok": True},
            )

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                adapter_class.from_boto3.return_value.apply.return_value = [apply_result]
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "apply",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--execute",
                            "--output",
                            "json",
                            "--output-file",
                            str(output_path),
                            "--profile",
                            "prod",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertEqual(stdout.getvalue(), "")
            adapter_class.from_boto3.assert_called_once_with(
                profile_name="prod",
                region_name=None,
                catalog_id=None,
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["plan"]["summary"], {"total": 1, "safe": 1, "destructive": 0})
            self.assertEqual(payload["results"], [apply_result.to_dict()])

    def test_cli_apply_saved_plan_dry_run_does_not_load_aws(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            plan_path = tmp_path / "plan.json"
            plan_path.write_text(json.dumps(_saved_plan_payload()), encoding="utf-8")

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(["apply", "--plan", str(plan_path), "--only", "change_002"])

            self.assertEqual(exit_code, 0)
            adapter_class.from_boto3.assert_not_called()
            self.assertIn("Dry run: no changes applied.", stdout.getvalue())
            self.assertIn("change_002 grant.add_permissions", stdout.getvalue())
            self.assertNotIn("change_001 lf_tag.create", stdout.getvalue())

    def test_cli_apply_saved_plan_rejects_only_and_only_action_together(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(_saved_plan_payload()), encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "apply",
                        "--plan",
                        str(plan_path),
                        "--only",
                        "change_001",
                        "--only-action",
                        "lf_tag.create",
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("--only cannot be combined with --only-action", stderr.getvalue())

    def test_cli_apply_saved_plan_rejects_unknown_change_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(_saved_plan_payload()), encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(["apply", "--plan", str(plan_path), "--only", "change_999"])

            self.assertEqual(exit_code, 2)
            self.assertIn("Unknown change id(s): change_999", stderr.getvalue())

    def test_cli_apply_saved_plan_only_action_and_budget_execute_selected_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(_saved_plan_payload()), encoding="utf-8")
            apply_result = ApplyResult(
                action="grant.add_permissions",
                target="role -> database:database=analytics",
                applied=True,
                response={"ok": True},
            )

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                adapter_class.from_boto3.return_value.apply.return_value = [apply_result]
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "apply",
                            "--plan",
                            str(plan_path),
                            "--only-action",
                            "grant.add_permissions",
                            "--max-changes",
                            "1",
                            "--execute",
                            "--profile",
                            "prod",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            adapter_class.from_boto3.assert_called_once_with(
                profile_name="prod",
                region_name=None,
                catalog_id=None,
            )
            applied_plan = adapter_class.from_boto3.return_value.apply.call_args.args[0]
            self.assertEqual([change.id for change in applied_plan.changes], ["change_002"])
            self.assertEqual([change.action for change in applied_plan.changes], ["grant.add_permissions"])

    def test_cli_apply_budget_failure_returns_one_without_aws_calls(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(_saved_plan_payload()), encoding="utf-8")

            stderr = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                with contextlib.redirect_stderr(stderr):
                    exit_code = main(["apply", "--plan", str(plan_path), "--max-changes", "1", "--execute"])

            self.assertEqual(exit_code, 1)
            adapter_class.from_boto3.assert_not_called()
            self.assertIn("exceeding --max-changes 1", stderr.getvalue())

    def test_cli_apply_saved_destructive_plan_requires_exact_allow_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(_saved_plan_payload(destructive=True)), encoding="utf-8")

            for extra_args in ([], ["--allow-resource-tag-removals"]):
                stderr = io.StringIO()
                with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                    with contextlib.redirect_stderr(stderr):
                        exit_code = main(["apply", "--plan", str(plan_path), "--execute", *extra_args])
                self.assertEqual(exit_code, 2)
                adapter_class.from_boto3.assert_not_called()
                self.assertIn("requires --allow-permission-revokes", stderr.getvalue())

    def test_cli_apply_saved_destructive_plan_runs_with_matching_allow_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_path = Path(tmp) / "plan.json"
            plan_path.write_text(json.dumps(_saved_plan_payload(destructive=True)), encoding="utf-8")

            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                adapter_class.from_boto3.return_value.apply.return_value = []
                with contextlib.redirect_stdout(io.StringIO()):
                    exit_code = main(
                        [
                            "apply",
                            "--plan",
                            str(plan_path),
                            "--execute",
                            "--allow-permission-revokes",
                        ]
                    )

            self.assertEqual(exit_code, 0)
            self.assertTrue(adapter_class.from_boto3.return_value.apply.call_args.kwargs["allow_destructive"])

    def test_cli_import_writes_starter_desired_state_from_aws(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "desired.json"
            imported = CurrentState.from_dict(
                {
                    "lf_tags": {"domain": ["sales"]},
                    "lf_tag_expressions": {"sales_tables": {"expression": {"domain": ["sales"]}}},
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

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter") as adapter_class:
                adapter_class.from_boto3.return_value.import_state.return_value = imported
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "import",
                            "--catalog-id",
                            "123456789012",
                            "--include",
                            "lf-tags,lf-tag-expressions,grants",
                            "--output",
                            str(output_path),
                        ]
                    )

            self.assertEqual(exit_code, 0)
            adapter_class.from_boto3.assert_called_once_with(
                profile_name=None,
                region_name=None,
                catalog_id="123456789012",
            )
            adapter_class.from_boto3.return_value.import_state.assert_called_once_with(
                include=("lf-tags", "lf-tag-expressions", "grants")
            )
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["lf_tag_expressions"]["sales_tables"]["expression"], {"domain": ["sales"]})
            self.assertIn("Wrote imported desired state", stdout.getvalue())

    def test_lint_config_overrides_severity_and_can_ignore_rule(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"Sensitivity": ["Internal"]},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    }
                ],
                "lint": {
                    "lf_tag_case_normalization": "warning",
                    "named_resource_grant_review": "ignore",
                },
            }
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_CASE_NORMALIZATION"])
        self.assertEqual(findings[0].severity, "warning")

    def test_lint_checks_named_lf_tag_expressions_and_grants_by_name(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "lf_tag_expressions": {"sales_tables": {"expression": {"domain": ["sales"]}}},
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression_name": "missing_expression",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual(
            {finding.code for finding in findings},
            {"LF_TAG_POLICY_EXPRESSION_NAME_UNDEFINED"},
        )

    def test_lint_checks_named_lf_tag_expression_references_by_catalog_id(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["sales"]},
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

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_POLICY_EXPRESSION_NAME_UNDEFINED"])
        self.assertEqual(findings[0].details["catalog_id"], "222222222222")

    def test_lint_checks_resource_tag_values_by_catalog_id(self):
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
                        "catalog_id": "222222222222",
                        "values": ["finance"],
                    },
                ],
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
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["RESOURCE_TAG_VALUE_UNDEFINED"])
        self.assertEqual(findings[0].details["catalog_id"], "222222222222")

    def test_lint_checks_inline_lf_tag_policy_expression_by_catalog_id(self):
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
                        "catalog_id": "222222222222",
                        "values": ["finance"],
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "222222222222",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_POLICY_VALUE_UNDEFINED"])
        self.assertEqual(findings[0].details["catalog_id"], "222222222222")

    def test_lint_rejects_duplicate_lf_tag_expression_identity(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales", "finance"]},
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
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_EXPRESSION_DUPLICATE_IDENTITY"])
        self.assertEqual(findings[0].target, "lf_tag_expression:catalog=111111111111:name=shared")
        self.assertEqual(findings[0].details, {"catalog_id": "111111111111", "name": "shared"})

    def test_lint_rejects_duplicate_lf_tag_identity(self):
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
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_DUPLICATE_IDENTITY"])
        self.assertEqual(findings[0].target, "lf_tag:catalog=111111111111:key=domain")
        self.assertEqual(findings[0].details, {"catalog_id": "111111111111", "tag_key": "domain"})

    def test_lint_rejects_duplicate_lf_tag_key_metadata_identity(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "lf_tag_key_metadata": [
                    {
                        "key": "domain",
                        "catalog_id": "111111111111",
                        "assignable_to": ["table"],
                    },
                    {
                        "key": "domain",
                        "catalog_id": "111111111111",
                        "assignable_to": ["column"],
                    },
                ],
            }
        )

        findings = lint_desired(desired)

        self.assertEqual(
            [finding.code for finding in findings],
            ["LF_TAG_KEY_METADATA_DUPLICATE_IDENTITY"],
        )
        self.assertEqual(findings[0].target, "lf_tag_key_metadata:catalog=111111111111:key=domain")
        self.assertEqual(findings[0].details, {"catalog_id": "111111111111", "tag_key": "domain"})

    def test_lint_unscoped_named_lf_tag_expression_reference_requires_unambiguous_match(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales", "finance"]},
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["sales"]},
                    },
                    {
                        "name": "shared",
                        "catalog_id": "222222222222",
                        "expression": {"domain": ["finance"]},
                    },
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
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_POLICY_EXPRESSION_NAME_UNDEFINED"])

    def test_lint_named_lf_tag_expression_only_state_is_not_empty(self):
        desired = DesiredState.from_dict(
            {
                "lf_tag_expressions": {"sales_tables": {"expression": {"domain": ["sales"]}}},
            }
        )

        findings = lint_desired(desired)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_EXPRESSION_KEY_UNDEFINED"])

    def test_audit_ownership_and_ignore_control_unmanaged_grants(self):
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/data-analyst",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/app",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    },
                    {
                        "principal": "IAM_ALLOWED_PRINCIPALS",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    },
                    {
                        "principal": "arn:aws:iam::111122223333:role/data-legacy",
                        "resource": {"kind": "table", "database": "legacy_raw", "table": "orders"},
                        "permissions": ["DESCRIBE"],
                    },
                ]
            }
        )
        desired = DesiredState.from_dict(
            {
                "ownership": {
                    "managed_principals": ["arn:aws:iam::*:role/data-*"],
                    "unmanaged_action": "error",
                },
                "ignore": {
                    "principals": ["IAM_ALLOWED_PRINCIPALS"],
                    "resources": [{"database": "legacy_*"}],
                },
            }
        )

        findings = audit(desired, current)

        self.assertEqual([finding.details["principal"] for finding in findings], ["arn:aws:iam::111122223333:role/data-analyst"])
        self.assertEqual(findings[0].severity, "error")

    def test_audit_managed_principal_boundary_does_not_hide_resource_drift(self):
        desired = DesiredState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "database", "database": "analytics"},
                        "tags": {"domain": ["sales"]},
                    }
                ],
                "ownership": {
                    "managed_principals": ["arn:aws:iam::*:role/data-*"],
                },
            }
        )
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "database", "database": "analytics"},
                        "tags": {"domain": ["sales", "finance"]},
                    }
                ]
            }
        )

        findings = audit(desired, current)

        self.assertEqual([finding.code for finding in findings], ["RESOURCE_TAG_VALUES_UNMANAGED"])
        self.assertEqual(findings[0].severity, "warning")

    def test_audit_reports_unmanaged_resource_tag_assignment(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "111111111111",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    }
                ]
            }
        )

        findings = audit(DesiredState.empty(), current)

        self.assertEqual([finding.code for finding in findings], ["RESOURCE_TAG_UNMANAGED"])
        self.assertEqual(findings[0].details["resource"]["catalog_id"], "111111111111")
        self.assertEqual(findings[0].details["current_tags"], {"domain": ["sales"]})

    def test_audit_ignores_unmanaged_resource_tag_assignment_by_resource_rule(self):
        desired = DesiredState.from_dict(
            {
                "ignore": {
                    "resources": [
                        {
                            "kind": "table",
                            "catalog_id": "111111111111",
                            "database": "analytics",
                            "table": "orders",
                        }
                    ]
                },
            }
        )
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "111111111111",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    }
                ]
            }
        )

        findings = audit(desired, current)

        self.assertEqual(findings, ())

    def test_audit_ignores_unmanaged_data_cells_filter_grant_by_filter_pattern(self):
        desired = DesiredState.from_dict(
            {
                "ignore": {
                    "resources": [
                        {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_*",
                        }
                    ]
                },
            }
        )
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
                ],
            }
        )

        findings = audit(desired, current)

        self.assertEqual(findings, ())

    def test_audit_managed_resources_can_select_data_cells_filter_grants(self):
        desired = DesiredState.from_dict(
            {
                "ownership": {
                    "managed_resources": [
                        {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "filter_name": "orders_*",
                        }
                    ],
                    "unmanaged_action": "error",
                },
            }
        )
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
                    },
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "333333333333",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    },
                ],
            }
        )

        findings = audit(desired, current)

        self.assertEqual([finding.code for finding in findings], ["GRANT_UNMANAGED"])
        self.assertEqual(findings[0].severity, "error")
        self.assertEqual(findings[0].details["resource"]["catalog_id"], "222222222222")

    def test_audit_catalog_scoped_ownership_includes_unscoped_current_grants(self):
        desired = DesiredState.from_dict(
            {
                "ownership": {
                    "managed_resources": [
                        {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        }
                    ],
                    "unmanaged_action": "error",
                },
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
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

        findings = audit(desired, current)

        self.assertEqual([finding.code for finding in findings], ["GRANT_UNMANAGED"])
        self.assertEqual(findings[0].severity, "error")
        self.assertNotIn("catalog_id", findings[0].details["resource"])

    def test_audit_named_lf_tag_expression_drift(self):
        desired = DesiredState.from_dict(
            {
                "lf_tag_expressions": {"sales_tables": {"expression": {"domain": ["sales"]}}},
            }
        )
        current = CurrentState.from_dict(
            {
                "lf_tag_expressions": {"sales_tables": {"expression": {"domain": ["finance"]}}},
            }
        )

        findings = audit(desired, current)

        self.assertEqual([finding.code for finding in findings], ["LF_TAG_EXPRESSION_BODY_DRIFT"])


def _saved_plan_payload(destructive=False):
    if destructive:
        return {
            "schema_version": "lfguard.plan.v1",
            "summary": {"total": 1, "safe": 0, "destructive": 1},
            "changes": [
                {
                    "id": "change_001",
                    "action": "grant.revoke_permissions",
                    "target": "role -> database:database=analytics",
                    "reason": "Principal has Lake Formation permissions not present in desired state",
                    "destructive": True,
                    "payload": {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DROP"],
                        "grantable_permissions": [],
                    },
                    "before": {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE", "DROP"],
                    },
                    "after": {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    },
                }
            ],
        }
    return {
        "schema_version": "lfguard.plan.v1",
        "summary": {"total": 2, "safe": 2, "destructive": 0},
        "changes": [
            {
                "id": "change_001",
                "action": "lf_tag.create",
                "target": "lf_tag:sensitivity",
                "reason": "LF-Tag is missing",
                "destructive": False,
                "payload": {"tag_key": "sensitivity", "tag_values": ["internal"]},
                "before": None,
                "after": {"tag_key": "sensitivity", "tag_values": ["internal"]},
            },
            {
                "id": "change_002",
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
            },
        ],
    }


def _policy_actions(policy):
    return {
        action
        for statement in policy["Statement"]
        for action in statement["Action"]
    }


class _FakePermissionChecker:
    def __init__(self, report):
        self.report = report
        self.actions = None
        self.template = None
        self.include_glue_read = None
        self.principal_arn = None

    def check(self, actions, *, template, include_glue_read=False, principal_arn=None):
        self.actions = tuple(actions)
        self.template = template
        self.include_glue_read = include_glue_read
        self.principal_arn = principal_arn
        return self.report


def _python_policy_source(object_name="policy", as_factory=False):
    body = """from lakeformation_guard.policy import LakePolicy, TagAssignmentScope, reader

policy = LakePolicy()
policy.tag_key(
    "domain",
    values=["sales"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
)
policy.tag_key(
    "contains_pii",
    values=["false", "true"],
    assignable_to=[
        TagAssignmentScope.DATABASE,
        TagAssignmentScope.TABLE,
        TagAssignmentScope.COLUMN,
    ],
)
policy.tag_database("sales_curated", domain="sales", contains_pii="false")
policy.tag_table("sales_curated", "customers", contains_pii="false")
policy.tag_columns("sales_curated", "customers", "phone_number", contains_pii="true")
policy.group("dataconsumer", reader().where(domain="sales", contains_pii="false"))
policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")
"""
    if not as_factory:
        return body if object_name == "policy" else body.replace("policy =", "{} =".format(object_name), 1)
    return """from lakeformation_guard.policy import LakePolicy, TagAssignmentScope, reader


def {object_name}():
    policy = LakePolicy()
    policy.tag_key(
        "domain",
        values=["sales"],
        assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
    )
    policy.group("dataconsumer", reader().where(domain="sales"))
    policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")
    return policy
""".format(object_name=object_name)


if __name__ == "__main__":
    unittest.main()
