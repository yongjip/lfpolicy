import json
import re
import unittest
from pathlib import Path

from lakeformation_guard import DesiredState, Grant, ResourceRef, lint_desired
from lakeformation_guard.policy import load_policy


class DocumentationExampleTests(unittest.TestCase):
    def test_internal_markdown_links_resolve(self):
        root = Path(__file__).resolve().parents[1]
        docs_paths = [
            root / "README.md",
            *sorted((root / ".github").glob("*.md")),
            *sorted((root / ".github" / "ISSUE_TEMPLATE").glob("*.md")),
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
        apply_dry_run = (artifacts / "lfguard-apply-dry-run.md").read_text(encoding="utf-8")

        self.assertEqual(audit["schema_version"], "lfguard.audit.v1")
        self.assertEqual(plan["schema_version"], "lfguard.plan.v1")
        self.assertEqual(explain["schema_version"], "lfguard.explain.v1")
        self.assertEqual([change["id"] for change in plan["changes"]], ["change_001", "change_002", "change_003"])
        self.assertEqual(explain["summary"]["matched"], 1)
        self.assertIn("Dry run: no changes applied.", apply_dry_run)
        self.assertIn("change_003", apply_dry_run)

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
