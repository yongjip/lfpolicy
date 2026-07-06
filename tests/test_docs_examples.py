import json
import re
import unittest
from pathlib import Path

from lakeformation_guard import DesiredState, Grant, ResourceRef, __version__, lint_desired
from lakeformation_guard.policy import load_policy


class DocumentationExampleTests(unittest.TestCase):
    def test_internal_markdown_links_resolve(self):
        root = Path(__file__).resolve().parents[1]
        docs_paths = [
            root / "README.md",
            *sorted((root / ".github").glob("*.md")),
            *sorted((root / ".github").glob("*.yml")),
            *sorted((root / ".github").glob("*.yaml")),
            *sorted((root / ".github" / "ISSUE_TEMPLATE").glob("*.md")),
            *sorted((root / ".github" / "ISSUE_TEMPLATE").glob("*.yml")),
            *sorted((root / ".github" / "ISSUE_TEMPLATE").glob("*.yaml")),
            *sorted((root / "docs").rglob("*.md")),
            *sorted((root / "examples").glob("*.md")),
            root / "AGENTS.md",
            root / "CLAUDE.md",
            root / "CHANGELOG.md",
            root / "CONTRIBUTING.md",
            root / "SECURITY.md",
        ]
        link_pattern = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")

        for docs_path in docs_paths:
            text = docs_path.read_text(encoding="utf-8")
            for match in link_pattern.finditer(text):
                target = match.group(1).strip()
                if not target or _is_external_link(target) or target.startswith("#"):
                    continue
                target_path = target.split("#", 1)[0]
                if not target_path:
                    continue
                resolved = (docs_path.parent / target_path).resolve()
                self.assertTrue(
                    resolved.exists(),
                    "{} links to missing {}".format(docs_path.relative_to(root), target),
                )

    def test_state_format_json_examples_parse(self):
        docs_path = Path(__file__).resolve().parents[1] / "docs" / "state-format.md"
        text = docs_path.read_text(encoding="utf-8")
        blocks = re.findall(r"```json\n(.*?)\n```", text, flags=re.DOTALL)

        self.assertGreater(len(blocks), 0)
        for block in blocks:
            data = json.loads(block)
            if isinstance(data, dict) and data.get("kind"):
                ResourceRef.from_dict(data)
            elif isinstance(data, dict) and "principal" in data:
                Grant.from_dict(data)
            else:
                DesiredState.from_dict(data)

    def test_aws_api_coverage_mentions_adapter_methods(self):
        root = Path(__file__).resolve().parents[1]
        docs_text = (root / "docs" / "aws-api-coverage.md").read_text(encoding="utf-8")
        source_text = (root / "src" / "lakeformation_guard" / "aws.py").read_text(encoding="utf-8")
        methods = (
            "get_lf_tag",
            "get_lf_tag_expression",
            "get_resource_lf_tags",
            "list_lf_tags",
            "list_lf_tag_expressions",
            "list_permissions",
            "create_lf_tag",
            "delete_lf_tag",
            "update_lf_tag",
            "create_lf_tag_expression",
            "update_lf_tag_expression",
            "delete_lf_tag_expression",
            "add_lf_tags_to_resource",
            "remove_lf_tags_from_resource",
            "grant_permissions",
            "revoke_permissions",
        )

        for method in methods:
            self.assertIn(method, source_text)
            self.assertIn(method, docs_text)

        for action in (
            "lakeformation:GetLFTag",
            "lakeformation:GetLFTagExpression",
            "lakeformation:GetResourceLFTags",
            "lakeformation:ListLFTags",
            "lakeformation:ListLFTagExpressions",
            "lakeformation:ListPermissions",
            "lakeformation:CreateLFTag",
            "lakeformation:DeleteLFTag",
            "lakeformation:UpdateLFTag",
            "lakeformation:CreateLFTagExpression",
            "lakeformation:UpdateLFTagExpression",
            "lakeformation:DeleteLFTagExpression",
            "lakeformation:AddLFTagsToResource",
            "lakeformation:RemoveLFTagsFromResource",
            "lakeformation:GrantPermissions",
            "lakeformation:RevokePermissions",
        ):
            self.assertIn(action, docs_text)

    def test_code_scanning_workflow_uploads_lint_and_audit_sarif(self):
        root = Path(__file__).resolve().parents[1]
        workflow_text = (root / "examples" / "github-actions" / "lakeformation-code-scanning.yml").read_text(
            encoding="utf-8"
        )

        for expected in (
            "security-events: write",
            "github/codeql-action/upload-sarif@v3",
            "artifacts/lfguard-lint.sarif",
            "artifacts/lfguard-audit.sarif",
            "artifacts/lfguard-check.md",
            "lfguard check",
            "lfguard generate policy.py --output-file policy/desired.json --check",
            "--desired policy/desired.json",
            "category: lfguard-lint",
            "category: lfguard-audit",
        ):
            self.assertIn(expected, workflow_text)
        self.assertNotIn("policy/desired.yaml", workflow_text)

    def test_drift_workflow_uses_generated_json_policy(self):
        root = Path(__file__).resolve().parents[1]
        workflow_text = (root / "examples" / "github-actions" / "lakeformation-drift.yml").read_text(
            encoding="utf-8"
        )

        for expected in (
            'python -m pip install "lfguard[aws]"',
            "lfguard doctor --require aws",
            "lfguard generate policy.py --output-file policy/desired.json --check",
            "mkdir -p artifacts snapshots",
            "--desired policy/desired.json",
        ):
            self.assertIn(expected, workflow_text)
        self.assertNotIn("policy/desired.yaml", workflow_text)

    def test_pre_commit_example_regenerates_desired_policy(self):
        root = Path(__file__).resolve().parents[1]
        hook_text = (root / "examples" / "pre-commit" / "pre-commit-config.yaml").read_text(
            encoding="utf-8"
        )

        for expected in (
            "lfguard generate policy.py --output-file policy/desired.json --force",
            "lfguard check --desired policy/desired.json --fail-on-findings",
            "policy\\.py",
        ):
            self.assertIn(expected, hook_text)

    def test_python_policy_example_compiles_to_clean_desired_state(self):
        root = Path(__file__).resolve().parents[1]
        policy_path = root / "examples" / "policy.py"

        policy = load_policy(policy_path)
        desired = policy.to_desired_state()
        findings = lint_desired(desired)

        self.assertEqual(len(desired.lf_tags), 2)
        self.assertEqual(len(desired.resource_tags), 5)
        self.assertEqual(len(desired.grants), 7)
        self.assertFalse(findings)
        policy_source = policy_path.read_text(encoding="utf-8")
        self.assertIn("table_creator", policy_source)
        self.assertIn("catalog_admin", policy_source)
        self.assertNotIn('group("admin"', policy_source)
        self.assertNotRegex(policy_source, r"(?<!_)creator\(\)\.")

    def test_policy_bundle_example_compiles_to_clean_desired_state(self):
        root = Path(__file__).resolve().parents[1]
        policy_path = root / "examples" / "policy-bundles.py"

        policy = load_policy(policy_path)
        desired = policy.to_desired_state()
        findings = lint_desired(desired)

        self.assertFalse(findings)
        self.assertEqual(
            {grant.resource.kind for grant in desired.grants},
            {"catalog", "data_location", "lf_tag_expression", "lf_tag_policy"},
        )
        permissions = {permission for grant in desired.grants for permission in grant.permissions}
        self.assertIn("GRANT_WITH_LF_TAG_EXPRESSION", permissions)

    def test_permission_request_example_compiles_to_clean_desired_state(self):
        root = Path(__file__).resolve().parents[1]
        policy_path = root / "examples" / "permission-requests.py"

        policy = load_policy(policy_path)
        desired = policy.to_desired_state()
        findings = lint_desired(desired)

        self.assertFalse(findings)
        self.assertEqual(len(desired.grants), 6)
        self.assertEqual(
            {grant.principal for grant in desired.grants},
            {
                "arn:aws:iam::111122223333:role/FinanceAnalyst",
                "arn:aws:iam::111122223333:role/FinanceProducer",
                "arn:aws:iam::111122223333:role/FinanceSteward",
            },
        )
        policy_source = policy_path.read_text(encoding="utf-8")
        self.assertIn("DATA-1042", policy_source)
        self.assertIn("review_by", policy_source)

    def test_policy_from_import_example_compiles_to_clean_desired_state(self):
        root = Path(__file__).resolve().parents[1]
        policy_path = root / "examples" / "policy-from-import.py"

        policy = load_policy(policy_path)
        desired = policy.to_desired_state()
        findings = lint_desired(desired)

        self.assertFalse(findings)
        self.assertEqual(len(desired.lf_tags), 2)
        self.assertEqual(len(desired.resource_tags), 3)
        self.assertEqual(len(desired.grants), 5)
        self.assertIn("IMPORTED_DESIRED_REFERENCE", policy_path.read_text(encoding="utf-8"))

    def test_evidence_artifact_fixtures_are_parseable_and_use_stable_schemas(self):
        root = Path(__file__).resolve().parents[1]
        artifacts = root / "examples" / "artifacts"

        audit = json.loads((artifacts / "lfguard-audit.json").read_text(encoding="utf-8"))
        plan = json.loads((artifacts / "lfguard-plan.json").read_text(encoding="utf-8"))
        explain = json.loads((artifacts / "lfguard-explain.json").read_text(encoding="utf-8"))
        explain_batch = json.loads((artifacts / "lfguard-explain-batch.json").read_text(encoding="utf-8"))
        apply_dry_run = (artifacts / "lfguard-apply-dry-run.md").read_text(encoding="utf-8")

        self.assertEqual(audit["schema_version"], "lfguard.audit.v1")
        self.assertEqual(plan["schema_version"], "lfguard.plan.v1")
        self.assertEqual(explain["schema_version"], "lfguard.explain.v1")
        self.assertEqual(explain_batch["schema_version"], "lfguard.explain_batch.v1")
        self.assertEqual([change["id"] for change in plan["changes"]], ["change_001", "change_002", "change_003"])
        self.assertEqual(explain["summary"]["matched"], 1)
        self.assertEqual(explain_batch["summary"], {"total": 3, "allowed": 1, "denied": 2})
        self.assertEqual(
            [(result["id"], result["decision"]) for result in explain_batch["results"]],
            [
                ("analyst-orders-select", "allowed"),
                ("analyst-orders-describe", "denied"),
                ("engineer-orders-select", "denied"),
            ],
        )
        self.assertEqual(explain_batch["results"][1]["explain"]["summary"]["matched"], 0)
        self.assertEqual(explain_batch["results"][1]["explain"]["summary"]["not_matched"], 1)
        self.assertEqual(explain_batch["results"][0]["diagnosis"]["matched_sources"], ["direct_grant"])
        self.assertEqual(explain_batch["results"][1]["diagnosis"]["missing_permissions"], ["DESCRIBE"])
        self.assertIn("Dry run: no changes applied.", apply_dry_run)
        self.assertIn("change_003", apply_dry_run)

    def test_report_contract_schemas_validate_checked_in_fixtures(self):
        root = Path(__file__).resolve().parents[1]
        schemas = root / "docs" / "schemas"
        artifacts = root / "examples" / "artifacts"
        pairs = (
            ("lfguard.audit.v1.schema.json", artifacts / "lfguard-audit.json"),
            ("lfguard.lint.v1.schema.json", artifacts / "review-bundle" / "lint.json"),
            ("lfguard.plan.v1.schema.json", artifacts / "lfguard-plan.json"),
            ("lfguard.review.manifest.v1.schema.json", artifacts / "review-bundle" / "manifest.json"),
            ("lfguard.review.summary.v1.schema.json", artifacts / "review-bundle" / "summary.json"),
            ("lfguard.review.explain.v1.schema.json", artifacts / "review-bundle" / "explain.json"),
            ("lfguard.explain_batch.v1.schema.json", artifacts / "lfguard-explain-batch.json"),
        )

        for schema_name, fixture_path in pairs:
            schema = json.loads((schemas / schema_name).read_text(encoding="utf-8"))
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            self.assertEqual(schema["$schema"], "https://json-schema.org/draft/2020-12/schema")
            self.assertEqual(schema["type"], "object")
            _validate_schema_subset(fixture, schema, path=str(fixture_path.relative_to(root)))

        review_case_root = artifacts / "review-cases"
        for case_dir in sorted(path for path in review_case_root.iterdir() if path.is_dir()):
            for schema_name, artifact_name in (
                ("lfguard.review.manifest.v1.schema.json", "manifest.json"),
                ("lfguard.review.summary.v1.schema.json", "summary.json"),
                ("lfguard.lint.v1.schema.json", "lint.json"),
                ("lfguard.audit.v1.schema.json", "audit.json"),
                ("lfguard.plan.v1.schema.json", "plan.json"),
                ("lfguard.review.explain.v1.schema.json", "explain.json"),
            ):
                schema = json.loads((schemas / schema_name).read_text(encoding="utf-8"))
                fixture = json.loads((case_dir / artifact_name).read_text(encoding="utf-8"))
                _validate_schema_subset(fixture, schema, path=str((case_dir / artifact_name).relative_to(root)))

        explain_case_root = artifacts / "explain-batch-cases"
        explain_schema = json.loads((schemas / "lfguard.explain_batch.v1.schema.json").read_text(encoding="utf-8"))
        for fixture_path in sorted(explain_case_root.glob("*.json")):
            fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
            _validate_schema_subset(fixture, explain_schema, path=str(fixture_path.relative_to(root)))

    def test_service_contract_fixture_matrix_covers_review_and_explain_outcomes(self):
        root = Path(__file__).resolve().parents[1]
        artifacts = root / "examples" / "artifacts"

        expected_review = {
            "passed": ("passed", "inform", False),
            "review_required": ("review_required", "review_required", False),
            "approval_required": ("review_required", "approval_required", False),
            "blocked": ("blocked", "block", True),
        }
        for case_name, (status, action, hard_block) in expected_review.items():
            summary = json.loads(
                (artifacts / "review-cases" / case_name / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(summary["status"], status)
            self.assertEqual(summary["recommended_action"], action)
            self.assertEqual(summary["hard_block"], hard_block)
            self.assertEqual(summary["action_summary"]["block"] > 0, hard_block)
            self.assertIn("evidence", summary)
            self.assertEqual(summary["evidence"]["truncation"], {"truncated": False, "artifacts": []})

        expected_explain = {
            "allowed": ("allowed", ["direct_grant"], []),
            "denied_missing_permission": ("denied", [], ["DESCRIBE"]),
            "denied_no_matching_grant": ("denied", [], []),
        }
        for case_name, (decision, matched_sources, missing_permissions) in expected_explain.items():
            payload = json.loads(
                (artifacts / "explain-batch-cases" / "{}.json".format(case_name)).read_text(encoding="utf-8")
            )
            result = payload["results"][0]
            self.assertEqual(result["decision"], decision)
            self.assertEqual(result["diagnosis"]["matched_sources"], matched_sources)
            self.assertEqual(result["diagnosis"]["missing_permissions"], missing_permissions)

    def test_review_bundle_contract_fixture_is_service_safe(self):
        root = Path(__file__).resolve().parents[1]
        bundle = root / "examples" / "artifacts" / "review-bundle"

        manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
        summary = json.loads((bundle / "summary.json").read_text(encoding="utf-8"))
        lint_payload = json.loads((bundle / "lint.json").read_text(encoding="utf-8"))
        audit_payload = json.loads((bundle / "audit.json").read_text(encoding="utf-8"))
        plan_payload = json.loads((bundle / "plan.json").read_text(encoding="utf-8"))
        explain_payload = json.loads((bundle / "explain.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["schema_version"], "lfguard.review.manifest.v1")
        self.assertEqual(manifest["lfguard_version"], __version__)
        self.assertEqual(manifest["inputs"]["current"]["source"], "current_snapshot")
        self.assertIn("sha256", manifest["inputs"]["desired"])
        self.assertIn("sha256", manifest["inputs"]["current"])
        self.assertEqual(summary["schema_version"], "lfguard.review.summary.v1")
        self.assertEqual(summary["status"], "review_required")
        self.assertEqual(summary["recommended_action"], "review_required")
        self.assertFalse(summary["hard_block"])
        self.assertEqual(summary["blocking_reasons"], [])
        self.assertEqual(set(summary["action_summary"]), {"inform", "review_required", "approval_required", "block"})
        self.assertEqual(summary["evidence"]["lfguard_version"], manifest["lfguard_version"])
        self.assertEqual(summary["evidence"]["inputs"]["current"]["source"], "current_snapshot")
        self.assertEqual(summary["evidence"]["truncation"], {"truncated": False, "artifacts": []})
        self.assertEqual(lint_payload["schema_version"], "lfguard.lint.v1")
        self.assertEqual(audit_payload["schema_version"], "lfguard.audit.v1")
        self.assertEqual(plan_payload["schema_version"], "lfguard.plan.v1")
        self.assertEqual(explain_payload["schema_version"], "lfguard.review.explain.v1")
        self.assertIn("Planned grant-change evidence", explain_payload["description"])
        self.assertIn("explain-batch", explain_payload["description"])
        self.assertEqual(explain_payload["summary"], {"planned_grant_changes": 1})
        grant_change = explain_payload["grant_changes"][0]
        for key in (
            "change_id",
            "action",
            "risk",
            "principal",
            "resource",
            "requested_permissions",
            "before",
            "after",
            "reason",
            "recommended_action",
            "hard_block",
            "title",
            "docs_anchor",
            "docs_url",
        ):
            self.assertIn(key, grant_change)
        self.assertEqual(grant_change["risk"], "safe")
        self.assertFalse(grant_change["hard_block"])

    def test_service_integration_docs_define_cli_contract_boundary(self):
        root = Path(__file__).resolve().parents[1]
        service_docs = (root / "docs" / "service-integration.md").read_text(encoding="utf-8")
        llm_docs = (root / "docs" / "llm-agent-integration.md").read_text(encoding="utf-8")

        for expected in (
            'sys.executable, "-m", "lakeformation_guard"',
            "Do not import private",
            "Do not run `lfguard apply` automatically",
            "`recommended_action`",
            "`hard_block`",
            "`severity: \"error\"`",
        ):
            self.assertIn(expected, service_docs)
        self.assertIn("Do not convert every `severity: \"error\"` into a user-facing block", llm_docs)

    def test_lake_formation_guide_covers_operating_model(self):
        root = Path(__file__).resolve().parents[1]
        guide_text = (root / "docs" / "lake-formation-guide.md").read_text(encoding="utf-8")
        readme_text = (root / "README.md").read_text(encoding="utf-8")

        for expected in (
            "IAMAllowedPrincipals",
            "hybrid access mode",
            "Best Practices",
            "Antipatterns",
            "AWS stores LF-Tag keys and values in lower case",
            "only one value for a given key",
            "are OR. Multiple keys are AND",
            "`*` as all values for a tag key",
            "Source References",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-overview.html",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/tag-based-access-control.html",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/lf-tag-considerations.html",
        ):
            self.assertIn(expected, guide_text)
        self.assertIn("docs/lake-formation-guide.md", readme_text)

    def test_tag_permission_matrix_covers_effective_tag_and_permission_cases(self):
        root = Path(__file__).resolve().parents[1]
        matrix_text = (root / "docs" / "tag-permission-matrix.md").read_text(encoding="utf-8")
        readme_text = (root / "README.md").read_text(encoding="utf-8")

        for expected in (
            "Effective Tag Values",
            "Fast Answer",
            "Same-Key Inheritance Matrix",
            "Different-Key Inheritance Matrix",
            "Expression Matching",
            "Grant Shape Matrix",
            "Table and Column Scenarios",
            "Effective Access Matrix",
            "Permission Matrix",
            "Permission Behavior Matrix",
            "Grant Option",
            "Controlled-Lake Guardrails",
            "`ALL`/`SUPER` permissions",
            "LF-Tag `TABLE` policies that combine",
            "illegal permission combinations this project blocks",
            "Same key: table `k=a`, column `k=b`",
            "Named and LF-TBAC grants union together",
            "`k=a` | `k=b` | `k=c`",
            "`domain=sales|finance AND sensitivity=internal`",
            "Table has `sensitivity=internal`; column `email` has `sensitivity=restricted`.",
            "LF-Tag values",
            "Data filters / cell filters",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/lf-permissions-reference.html",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-assigning-tags.html",
            "https://docs.aws.amazon.com/lake-formation/latest/dg/TBAC-granting-tags.html",
        ):
            self.assertIn(expected, matrix_text)
        self.assertIn("docs/tag-permission-matrix.md", readme_text)

    def test_policy_authoring_direction_defines_rigid_modes(self):
        root = Path(__file__).resolve().parents[1]
        direction_text = (root / "docs" / "policy-authoring-direction.md").read_text(encoding="utf-8")
        readme_text = (root / "README.md").read_text(encoding="utf-8")
        roadmap_text = (root / "docs" / "roadmap.md").read_text(encoding="utf-8")
        architecture_text = (root / "docs" / "architecture.md").read_text(encoding="utf-8")

        for expected in (
            "Python-native policy builder",
            "policy.py -> generated desired.json -> lfguard check/audit/plan/apply",
            "Permission group names are not enums",
            "reader()",
            "editor()",
            "producer()",
            "table_creator()",
            "database_creator()",
            "steward()",
            "data_location_access()",
            "CREATE_DATABASE",
            "CREATE_TABLE",
            "platform_admins",
            "TagAssignmentScope",
            "contains_pii",
            "editor, producer, and table_creator must stay whole-table",
            "tags assignable to columns",
            "lf_tag_key_metadata",
            "Generated by policy.py. Do not edit directly.",
            "arn:aws:iam::111122223333:role/DataEngineer",
        ):
            self.assertIn(expected, direction_text)
        self.assertIn("docs/policy-authoring-direction.md", readme_text)
        self.assertIn("permission group authoring layer", roadmap_text)
        self.assertIn("lakeformation_guard.policy", architecture_text)


def _is_external_link(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:"))


def _validate_schema_subset(data, schema, *, path):
    if "const" in schema:
        assert data == schema["const"], "{} expected const {!r}, got {!r}".format(path, schema["const"], data)
    if "enum" in schema:
        assert data in schema["enum"], "{} expected one of {!r}, got {!r}".format(path, schema["enum"], data)

    if "type" in schema:
        expected_types = schema["type"]
        if isinstance(expected_types, str):
            expected_types = [expected_types]
        assert any(_matches_json_type(data, expected_type) for expected_type in expected_types), (
            "{} expected type {!r}, got {}".format(path, expected_types, type(data).__name__)
        )

    if "minimum" in schema and isinstance(data, (int, float)) and not isinstance(data, bool):
        assert data >= schema["minimum"], "{} expected minimum {}".format(path, schema["minimum"])

    if isinstance(data, dict):
        for key in schema.get("required", []):
            assert key in data, "{} missing required key {}".format(path, key)
        for key, child_schema in schema.get("properties", {}).items():
            if key in data:
                _validate_schema_subset(data[key], child_schema, path="{}.{}".format(path, key))

    if isinstance(data, list) and "items" in schema:
        for index, item in enumerate(data):
            _validate_schema_subset(item, schema["items"], path="{}[{}]".format(path, index))


def _matches_json_type(data, expected_type):
    if expected_type == "object":
        return isinstance(data, dict)
    if expected_type == "array":
        return isinstance(data, list)
    if expected_type == "string":
        return isinstance(data, str)
    if expected_type == "integer":
        return isinstance(data, int) and not isinstance(data, bool)
    if expected_type == "number":
        return isinstance(data, (int, float)) and not isinstance(data, bool)
    if expected_type == "boolean":
        return isinstance(data, bool)
    if expected_type == "null":
        return data is None
    return True
