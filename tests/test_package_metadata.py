import configparser
import re
import unittest
from pathlib import Path

from lakeformation_guard import __version__


class PackageMetadataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[1]
        cls.config = configparser.ConfigParser()
        cls.config.read(cls.root / "setup.cfg", encoding="utf-8")

    def test_setup_version_matches_imported_version(self):
        self.assertEqual(self.config["metadata"]["version"], __version__)

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

        self.assertIn("lfguard = lakeformation_guard.cli:main", console_scripts)
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
        self.assertTrue((self.root / "AGENTS.md").exists())
        self.assertTrue((self.root / "CLAUDE.md").exists())
        self.assertTrue((self.root / "llms.txt").exists())
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
            self.assertIn("/lfguard --version", workflow)
            self.assertNotIn("/aws-lakeformation-guard --version", workflow)
            self.assertIn("/lfguard generate examples/policy.py --output-file /tmp/lfguard-policy.json --check", workflow)
            self.assertIn("/lfguard bootstrap --output-dir /tmp/lfguard-policy-bootstrap", workflow)
            self.assertIn("/tmp/lfguard-policy-bootstrap/policy.py", workflow)
            self.assertIn("/lfguard check", workflow)
            self.assertIn("--current-snapshot /tmp/lfguard-demo/current-snapshot.json", workflow)
            self.assertIn("/lfguard review", workflow)
            self.assertIn("/lfguard explain", workflow)
            self.assertIn("/lfguard explain-batch", workflow)
            self.assertIn("LakePolicy", workflow)
            self.assertIn("CurrentStateProvider", workflow)
            self.assertIn("callable(explain)", workflow)
            self.assertIn("table_creator", workflow)

    def test_release_workflow_verifies_published_package(self):
        workflow = (self.root / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertIn("Validate release tag", workflow)
        self.assertIn("tags:", workflow)
        self.assertIn('"v*"', workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("group: release-${{ github.event.release.tag_name || github.ref_name }}", workflow)
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("package_version=", workflow)
        self.assertIn("release_version=", workflow)
        self.assertIn("Check PyPI version", workflow)
        self.assertIn("pypi-version-exists", workflow)
        self.assertIn("https://pypi.org/pypi/lfguard/{}/json", workflow)
        self.assertIn("Verify distribution versions", workflow)
        self.assertIn("dist/lfguard-${version}.tar.gz", workflow)
        self.assertIn("lfguard-{}.dist-info/METADATA", workflow)
        self.assertIn("lfguard-{}/PKG-INFO", workflow)
        self.assertIn("verify-pypi:", workflow)
        self.assertIn("if: needs.build.outputs.pypi-version-exists != 'true'", workflow)
        self.assertIn("needs: [build, publish]", workflow)
        self.assertIn("needs.publish.result == 'skipped'", workflow)
        self.assertIn(
            "RELEASE_TAG: ${{ github.event.release.tag_name || github.ref_name }}",
            workflow,
        )
        self.assertIn('python -m pip install --no-cache-dir "lfguard==${version}"', workflow)
        self.assertIn('test "$(lfguard --version)" = "lfguard ${version}"', workflow)
        self.assertIn("sleep 15", workflow)
        self.assertIn("lfguard bootstrap --output-dir /tmp/lfguard-pypi-policy", workflow)
        self.assertIn("lfguard generate /tmp/lfguard-pypi-policy/policy.py", workflow)
        self.assertIn("--output-file /tmp/lfguard-pypi-policy/policy/desired.json --check", workflow)
        self.assertIn("lfguard sample --output-dir /tmp/lfguard-pypi-demo", workflow)
        self.assertIn("lfguard review", workflow)
        self.assertIn("lfguard explain", workflow)
        self.assertIn("lfguard explain-batch", workflow)
        self.assertIn("LakePolicy", workflow)
        self.assertIn("CurrentStateProvider", workflow)
        self.assertIn("callable(explain)", workflow)
        self.assertIn("table_creator", workflow)
        self.assertNotIn("aws-lakeformation-guard --version", workflow)
