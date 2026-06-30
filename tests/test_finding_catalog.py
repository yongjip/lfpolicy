import ast
import unittest
from pathlib import Path

from lakeformation_guard.finding_catalog import AUDIT_FINDINGS, LINT_FINDINGS, PLAN_ACTIONS
from lakeformation_guard.planner import _ACTION_AWS_API


class FindingCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.catalog_doc = (cls.root / "docs" / "finding-catalog.md").read_text(encoding="utf-8")

    def test_lint_finding_codes_have_catalog_entries(self):
        source_path = self.root / "src" / "lakeformation_guard" / "lint.py"
        codes = _finding_codes(source_path, "LintFinding") | _dynamic_lint_codes(source_path)

        self.assertEqual(codes - set(LINT_FINDINGS), set())

    def test_audit_finding_codes_have_catalog_entries(self):
        codes = _finding_codes(self.root / "src" / "lakeformation_guard" / "audit.py", "AuditFinding")

        self.assertEqual(codes - set(AUDIT_FINDINGS), set())

    def test_plan_actions_have_catalog_entries(self):
        self.assertEqual(set(_ACTION_AWS_API) - set(PLAN_ACTIONS), set())

    def test_catalog_entries_have_docs_anchors(self):
        for catalog in (LINT_FINDINGS, AUDIT_FINDINGS, PLAN_ACTIONS):
            for identifier, entry in catalog.items():
                with self.subTest(identifier=identifier):
                    self.assertIn("title", entry)
                    self.assertIn("category", entry)
                    self.assertIn("default_recommended_action", entry)
                    self.assertIn("hard_block", entry)
                    self.assertIn("docs_url", entry)
                    anchor = entry["docs_url"].split("#", 1)[1]
                    self.assertIn('id="{}"'.format(anchor), self.catalog_doc)


def _finding_codes(path: Path, class_name: str) -> set:
    codes = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Name) or node.func.id != class_name:
            continue
        for keyword in node.keywords:
            if keyword.arg == "code" and isinstance(keyword.value, ast.Constant):
                codes.add(keyword.value.value)
    return codes


def _dynamic_lint_codes(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    prefixes = set()
    templates = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_lint_expression_item":
            for keyword in node.keywords:
                if keyword.arg == "code_prefix" and isinstance(keyword.value, ast.Constant):
                    prefixes.add(keyword.value.value)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
            if isinstance(node.func.value, ast.Constant) and isinstance(node.func.value.value, str):
                template = node.func.value.value
                if template.startswith("{}_"):
                    templates.add(template)
    return {template.format(prefix) for prefix in prefixes for template in templates}
