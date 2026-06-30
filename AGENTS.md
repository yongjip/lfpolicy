# AGENTS.md

## Project Purpose

`lfguard` is a Python CLI and library for AWS Lake Formation permission review.
Its product direction is advisory governance evidence for services, DMS flows,
LLM agents, pull requests, tickets, and audit logs. Do not reposition it as an
automatic approval workflow or a Terraform/CDK replacement.

## Setup And Tests

- Use `PYTHONPATH=src` when running from a checkout.
- Run focused tests after scoped changes:
  `PYTHONPATH=src python3 -m unittest tests.test_audit_cli tests.test_provider_explain tests.test_models`
- Run the full suite before release or broad contract changes:
  `PYTHONPATH=src python3 -m unittest discover -s tests`
- Smoke review bundles after review contract changes:
  `PYTHONPATH=src python3 -m lakeformation_guard review --desired examples/desired.json --current-snapshot examples/current-snapshot.json --output-dir /tmp/lfguard-review-smoke --force`

## Contract Rules

- Preserve stable JSON fields unless intentionally making a documented release
  contract change.
- For LLM and DMS integration behavior, read
  [`docs/llm-agent-integration.md`](docs/llm-agent-integration.md) first.
- Do not treat `severity: "error"` as an automatic workflow block. Workflow
  decisions must use `recommended_action`, `hard_block`, and review `status`.
- `review/explain.json` is planned grant-change evidence. It is not an
  effective-access explanation. Use `explain-batch` for access decisions.
- `apply` must stay explicit and conservative. Do not add automatic apply or
  approval workflow behavior without a direct product decision.

## Version And Release

- Keep `setup.cfg`, `src/lakeformation_guard/_version.py`, `CHANGELOG.md`, and
  release notes aligned when bumping versions.
- The release workflow is triggered by `v*` tags and publishes to PyPI through
  GitHub Actions.
- Before tagging, run full tests, review smoke, package build, and `twine check`.

## Boundaries

- Do not commit local `.DS_Store`, build artifacts, virtual environments, or
  temporary review bundle output.
- Keep docs and examples aligned with the advisory posture: explain risk and
  recommended action; reserve "blocked" language for hard blocks.
