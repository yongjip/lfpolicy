import configparser
import re
import unittest
from pathlib import Path

from lfpolicy import __version__


class PackageMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.config = configparser.ConfigParser()
        cls.config.read(cls.root / "setup.cfg", encoding="utf-8")

    def test_setup_version_matches_imported_version(self):
        self.assertEqual(self.config["metadata"]["version"], __version__)

    def test_distribution_uses_lfpolicy_name(self):
        self.assertEqual(self.config["metadata"]["name"], "lfpolicy")
        self.assertTrue((self.root / "src" / "lfpolicy").is_dir())
        self.assertFalse((self.root / "src" / "lakeformation_guard").exists())

    def test_build_system_uses_modern_setuptools_backend(self):
        pyproject = (self.root / "pyproject.toml").read_text(encoding="utf-8")

        self.assertIn('build-backend = "setuptools.build_meta"', pyproject)
        self.assertRegex(pyproject, r'requires = \["setuptools>=70\.1"\]')
        self.assertIsNone(re.search(r'"wheel"', pyproject))

    def test_changelog_and_publishing_docs_reference_current_version(self):
        changelog = (self.root / "CHANGELOG.md").read_text(encoding="utf-8")
        publishing = (self.root / "docs" / "publishing.md").read_text(encoding="utf-8")

        self.assertIn("## {}".format(__version__), changelog)
        self.assertIn("v{}".format(__version__), publishing)

    def test_console_scripts_include_primary_command(self):
        console_scripts = self.config["options.entry_points"]["console_scripts"]

        self.assertIn("lfpolicy = lfpolicy.cli:main", console_scripts)
        self.assertNotIn("lfguard =", console_scripts)
        self.assertNotIn("aws-lakeformation-guard", console_scripts)

    def test_license_metadata_uses_spdx_expression(self):
        metadata = self.config["metadata"]
        classifiers = metadata["classifiers"]

        self.assertEqual(metadata["license"], "Apache-2.0")
        self.assertIn("license_files = LICENSE", (self.root / "setup.cfg").read_text(encoding="utf-8"))
        self.assertNotIn("License ::", classifiers)

    def test_source_distribution_includes_example_workflows(self):
        manifest = (self.root / "MANIFEST.in").read_text(encoding="utf-8")

        self.assertIn("include AGENTS.md", manifest)
        self.assertIn("include CLAUDE.md", manifest)
        self.assertIn("include llms.txt", manifest)
        self.assertIn("recursive-include examples *.json *.md *.py *.yaml *.yml", manifest)
        self.assertIn("recursive-include docs *.md *.json", manifest)
        self.assertTrue((self.root / "AGENTS.md").exists())
        self.assertTrue((self.root / "CLAUDE.md").exists())
        self.assertTrue((self.root / "llms.txt").exists())
        self.assertTrue((self.root / "docs" / "schemas" / "lfpolicy.review.summary.v1.schema.json").exists())
        self.assertTrue((self.root / "examples" / "policy.py").exists())
        self.assertTrue((self.root / "examples" / "github-actions" / "lakeformation-drift.yml").exists())
        self.assertTrue((self.root / "examples" / "pre-commit" / "pre-commit-config.yaml").exists())

    def test_project_urls_cover_user_evaluation_docs(self):
        project_urls = self.config["metadata"]["project_urls"]

        for label in (
            "Documentation",
            "CLI Reference",
            "Adoption Checklist",
            "LLM Agent Integration",
            "Service Integration",
            "Report Formats",
            "Report Schemas",
            "Finding Catalog",
            "Architecture",
            "Roadmap",
            "Safety Model",
            "Lake Formation Guide",
            "Tag and Permission Matrix",
            "Positioning",
            "State Format",
            "AWS API Coverage",
            "FAQ",
            "Troubleshooting",
            "Examples",
            "Changelog",
            "Security",
        ):
            self.assertIn("{} =".format(label), project_urls)

    def test_keywords_cover_discovery_terms(self):
        keywords = self.config["metadata"]["keywords"]

        for keyword in (
            "policy-as-code",
            "drift-detection",
            "data-governance",
            "data-lake",
            "aws-glue",
            "permissions",
        ):
            self.assertIn(keyword, keywords)

    def test_ci_and_release_smoke_cover_primary_cli_paths(self):
        workflow_paths = (
            self.root / ".github" / "workflows" / "ci.yml",
            self.root / ".github" / "workflows" / "release.yml",
        )

        for workflow_path in workflow_paths:
            workflow = workflow_path.read_text(encoding="utf-8")
            self.assertIn("/lfpolicy --version", workflow)
            self.assertNotIn("/aws-lakeformation-guard --version", workflow)
            self.assertIn("/lfpolicy generate examples/policy.py --output-file /tmp/lfpolicy-policy.json --check", workflow)
            self.assertIn("/lfpolicy bootstrap --output-dir /tmp/lfpolicy-policy-bootstrap", workflow)
            self.assertIn("/tmp/lfpolicy-policy-bootstrap/policy.py", workflow)
            self.assertIn("/lfpolicy check", workflow)
            self.assertIn("--current-snapshot /tmp/lfpolicy-demo/current-snapshot.json", workflow)
            self.assertIn("/lfpolicy review", workflow)
            self.assertIn("/lfpolicy explain", workflow)
            self.assertIn("/lfpolicy explain-batch", workflow)
            self.assertIn("LakePolicy", workflow)
            self.assertIn("CurrentStateProvider", workflow)
            self.assertIn("callable(explain)", workflow)
            self.assertIn("table_creator", workflow)

    def test_release_workflow_verifies_published_package(self):
        workflow = (self.root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertIn("Validate release tag", workflow)
        self.assertIn("workflow_dispatch:", workflow)
        self.assertIn("release_tag:", workflow)
        self.assertIn("Release tag ${RELEASE_TAG} must start with v.", workflow)
        self.assertNotIn("\n  push:", workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("group: release-${{ github.event.release.tag_name || github.event.inputs.release_tag }}", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("ref: ${{ env.RELEASE_TAG }}", workflow)
        self.assertIn("package_version=", workflow)
        self.assertIn("release_version=", workflow)
        self.assertIn("Check PyPI version", workflow)
        self.assertIn("pypi-version-exists", workflow)
        self.assertIn("https://pypi.org/pypi/lfpolicy/{}/json", workflow)
        self.assertIn("Verify distribution versions", workflow)
        self.assertIn("dist/lfpolicy-${version}.tar.gz", workflow)
        self.assertIn("lfpolicy-{}.dist-info/METADATA", workflow)
        self.assertIn("lfpolicy-{}/PKG-INFO", workflow)
        self.assertIn("verify-pypi:", workflow)
        self.assertIn("if: needs.build.outputs.pypi-version-exists != 'true'", workflow)
        self.assertIn("needs: [build, publish]", workflow)
        self.assertIn("needs.publish.result == 'skipped'", workflow)
        self.assertIn(
            "RELEASE_TAG: ${{ github.event.release.tag_name || github.event.inputs.release_tag }}",
            workflow,
        )
        self.assertIn('python -m pip install --no-cache-dir "lfpolicy==${version}"', workflow)
        self.assertIn('test "$(lfpolicy --version)" = "lfpolicy ${version}"', workflow)
        self.assertIn("sleep 15", workflow)
        self.assertIn("lfpolicy bootstrap --output-dir /tmp/lfpolicy-pypi-policy", workflow)
        self.assertIn("lfpolicy generate /tmp/lfpolicy-pypi-policy/policy.py", workflow)
        self.assertIn("--output-file /tmp/lfpolicy-pypi-policy/policy/desired.json --check", workflow)
        self.assertIn("lfpolicy sample --output-dir /tmp/lfpolicy-pypi-demo", workflow)
        self.assertIn("lfpolicy review", workflow)
        self.assertIn("lfpolicy explain", workflow)
        self.assertIn("lfpolicy explain-batch", workflow)
        self.assertIn("LakePolicy", workflow)
        self.assertIn("CurrentStateProvider", workflow)
        self.assertIn("callable(explain)", workflow)
        self.assertIn("table_creator", workflow)
        self.assertNotIn("aws-lakeformation-guard --version", workflow)
