# Changelog

## 0.4.4

- Rejects duplicate named LF-Tag expressions with the same exact
  `(catalog_id, name)` identity instead of allowing shared indexes to collapse
  them.
- Adds a `LF_TAG_EXPRESSION_DUPLICATE_IDENTITY` lint finding for duplicate
  desired-state LF-Tag expression identities.
- Reuses the same unscoped named-expression resolution rule in `lint` and
  `explain`, so unscoped grants consistently resolve to one unambiguous scoped
  named expression.
- Adds regression coverage for duplicate expression identity linting, planning
  rejection, and explain resolution of unscoped grants.

## 0.4.3

- Preserves same-name LF-Tag expressions across catalogs when serializing
  desired/current state by emitting list form for duplicate expression names.
- Validates named LF-Tag expression grant references by `(catalog_id, name)`,
  with an explicit unscoped-grant fallback only when the match is unambiguous.
- Centralizes normalized state indexing helpers so plan, audit, lint, explain,
  and AWS loading paths share the same catalog-aware expression keys.
- Makes summary/profile output catalog-aware by adding `lf_tag_expression_ids`
  while retaining the existing `lf_tag_expression_names` field.
- Adds regression coverage for duplicate expression serialization,
  catalog-scoped lint references, ambiguous unscoped references, and
  catalog-aware summary output.

## 0.4.2

- Fixes catalog ID precedence for live apply request building. A change payload
  `catalog_id` now overrides the adapter default catalog ID.
- Keys named LF-Tag expression drift detection by `(catalog_id, name)` in plan
  and audit paths, preventing same-name expressions in different catalogs from
  being treated as equivalent.
- Loads named LF-Tag expressions by catalog-scoped keys for live current-state
  inventory.
- Resolves named LF-Tag expressions by catalog-scoped keys in `explain()`.
- Adds regression coverage for payload catalog precedence and catalog-scoped
  named LF-Tag expression planning, audit, loading, and explanation.

## 0.4.1

- Fixes live apply for named LF-Tag expression create, update, and delete
  changes when no catalog ID is configured. Lower-case internal `catalog_id`
  payload keys are now stripped before boto3 calls even when the value is empty.
- Adds botocore `Stubber` coverage for named LF-Tag expression apply requests
  with and without `CatalogId`.

## 0.4.0

- Adds a `CurrentStateProvider` protocol plus snapshot-backed provider helpers
  so integrations can supply current Lake Formation state without boto3.
- Adds `lfguard explain` and the importable `explain()` API for offline-first
  access explanations across direct grants, LF-Tag policy grants, named
  LF-Tag expressions, effective LF-Tags, data-location context, and missing
  desired grants.

## 0.3.0

- Adds configurable lint severities through desired-state `lint` overrides.
- Adds ownership boundaries and ignore rules for unmanaged current-state drift.
- Adds named LF-Tag expression state, drift detection, planning, and AWS
  adapter support.
- Adds `lfguard import` for live AWS starter desired-state scaffolds.

## 0.2.2

- Adds stable plan JSON metadata with `schema_version`, deterministic change IDs,
  risk, before/after snapshots, required destructive flags, and boto3 API names.
- Adds saved-plan apply support with `lfguard apply --plan plan.json`.
- Adds selective apply by change ID or action type.
- Adds apply safety budgets with `--max-changes` and `--max-destructive`.
- Enforces exact destructive allow flags for saved plans before execution.
- Makes the release workflow skip PyPI upload when the tagged version already
  exists while still verifying the published package.

## 0.2.1

- Adds botocore `Stubber` contract tests for the Lake Formation adapter so AWS
  request shapes are validated against the botocore service model in the
  default test suite.
- Adds an optional Moto-backed emulator suite for small Lake Formation adapter
  round trips.
- Adds opt-in live AWS contract tests for Lake Formation behaviors local
  emulators cannot prove, including LF-Tag column overrides and invalid
  permission-combination enforcement.
- Adds testing documentation and a dedicated Moto CI job.

## 0.2.0

- Adds the Python-native `lakeformation_guard.policy` authoring layer for
  defining LF-Tag keys, resource tag assignments, permission groups, and IAM
  role bindings.
- Adds safe permission templates: `reader()`, `editor()`, `table_creator()`,
  and `database_creator()`.
- Adds explicit `tag_database()`, `tag_table()`, and `tag_columns()` helpers so
  generated desired state can cover both LF-Tag assignments and grants.
- Adds `lfguard generate` for compiling `policy.py` into JSON or YAML desired
  state, including `--check` for CI drift between source and generated files.
- Adds optional `lf_tag_key_metadata` to generated desired state so the linter
  can distinguish whole-table edit/create grants from column-narrowed read
  grants.
- Updates bootstrap, examples, README, and docs around the cleaner permission
  group model.
- Removes the long `aws-lakeformation-guard` console alias; the installed CLI
  command is now only `lfguard`.

## 0.1.1

- Blocks LF-Tag `TABLE` policies that combine `SELECT` with table mutation
  permissions, preventing Lake Formation partial-column `SELECT` illegal
  permission combinations before apply.

## 0.1.0

- Initial release of `lfguard`.
- Adds the `lfguard` CLI with `init`, `schema`, `check`, `validate`, `lint`,
  `audit`, `plan`, `sample`, `bootstrap`, `doctor`, `permissions`,
  `completion`, `snapshot`, and conservative `apply` commands.
- Adds desired-policy lint checks for undefined LF-Tag keys and values.
- Adds a `check` command for one-step offline validation and lint gates.
- Uses `check` in generated policy/demo workflows and release smoke tests.
- Emphasizes `check` in first-run quickstarts before planning changes.
- Adds policy summary reports for compact review of desired and current state.
- Adds text, JSON, and Markdown output for reviewable audit and plan workflows.
- Adds SARIF output for audit and lint findings.
- Adds an offline install check for optional AWS and YAML integrations.
- Adds `doctor --require` checks for failing CI when required optional extras
  are missing.
- Adds a `permissions` command for generating starter IAM policies for
  read-only, additive apply, and destructive apply workflows.
- Adds a `completion` command for bash, zsh, and fish shell completions.
- Adds a `--github-summary` option for GitHub Actions job summaries across
  lint, summary, audit, plan, and apply workflows.
- Adds a copyable GitHub Code Scanning workflow for lint and audit SARIF
  uploads.
- Adds a `--fail-on-changes` option for CI plan gates.
- Adds a `--fail-on-severity` option for error-only audit gates.
- Adds severity summaries to audit text, JSON, and Markdown reports.
- Adds `--output-file` report capture for audit, plan, and apply workflows.
- Adds `--output-file` diagnostics capture for doctor and validate workflows.
- Documents GitHub Actions report artifact uploads and preserves CI build artifacts.
- Adds a CLI reference with command semantics, common options, and exit codes.
- Adds YAML starter policy generation and a YAML example policy.
- Adds `init --template` starter policies for a data-domain example or blank
  policy skeleton.
- Ships a JSON Schema for desired/current state files.
- Adds importable planning and audit APIs under `lakeformation_guard`.
- Supports LF-Tag definitions, resource tag assignments, and Lake Formation grants.
- Includes an optional boto3 adapter for live AWS inventory and execution.
- Ships offline JSON/YAML desired-state workflows and example policy files.
- Adds an examples guide and PyPI metadata links for first-run discoverability.
- Adds PyPI discovery keywords for policy-as-code, drift detection, data lake,
  and data governance searches.
- Adds an adoption checklist for moving from offline demo to CI and controlled
  apply workflows.
- Adds a report-format guide for audit, plan, apply, and CI artifacts.
- Adds a safety model guide for conservative defaults and destructive changes.
- Adds a Lake Formation operating guide covering IAM/Lake Formation interaction,
  LF-Tag best practices, hybrid access mode, `IAMAllowedPrincipals`, and
  antipatterns.
- Tightens README and CLI guidance around the core `check`, `audit`, `plan`,
  and conservative `apply` workflow while keeping scaffolds secondary.
- Adds lint coverage and docs for AWS LF-Tag behavior: lower-case storage,
  one resource value per key, expression AND/OR semantics, and `*` value
  wildcards in LF-Tag policy grants.
- Adds a tag and permission matrix for LF-Tag inheritance, column overrides,
  grant shape interactions, expression matching, permission behavior, and
  `lfguard` support boundaries.
- Adds opinionated governance lint for broad principals, `ALL`/`SUPER`,
  mutating permissions, grant option, wildcard LF-Tag policies, and named
  database/table grant exceptions.
- Adds a positioning guide for how `lfguard` fits with infrastructure tools,
  raw boto3, and console workflows.
- Calls out README scope limits early so new users can evaluate fit quickly.
- Adds a README capability matrix for quick PyPI-page evaluation.
- Adds a troubleshooting guide for common install, AWS, planning, and CI issues.
- Adds GitHub issue and pull request templates for safer community reports.
- Adds a copyable GitHub Actions drift-check workflow under `examples/`.
- Adds a copyable pre-commit validation hook example under `examples/`.
- Adds an architecture guide for package boundaries, data flow, and AWS adapter
  responsibilities.
- Adds a roadmap with near-term priorities, evaluation questions, and non-goals.
- Adds publish-ready release notes for the first public PyPI release.
- Documents `pipx` and `uv tool` install paths for CLI users.
- Adds a `sample` command for generating a runnable offline demo after install,
  including a local README with copy-paste commands.
- Adds `sample --include-ci` for generating an offline GitHub Actions demo
  workflow alongside the sample files.
- Adds a `bootstrap` command for generating a starter policy repository layout
  with schema, CI, pre-commit, and rollout README files.
- Adds JSON, YAML, and combined output formats for generated sample demos.
- Adds a state-format guide with examples for each supported resource kind.
- Adds an AWS API coverage guide for live inventory and apply calls.
- Adds an FAQ for safety, scope, credentials, and adoption questions.
- Adds CI and release workflow smoke tests for the built wheel.
- Adds a release workflow gate that installs and smoke-tests the package from
  PyPI after publishing.
- Retries the post-publish PyPI install briefly to tolerate index propagation.
- Verifies the exact PyPI version matching the GitHub release tag.
- Fails the release workflow early when the GitHub release tag does not match
  package metadata.
- Verifies release artifact filenames and embedded wheel/sdist metadata before
  upload.
- Adds an optional `bootstrap --include-live-drift` scaffold for scheduled
  GitHub OIDC drift checks and starter read-only IAM policy JSON.
- Adds an optional `bootstrap --include-code-scanning` scaffold for uploading
  `lfguard` lint and drift SARIF findings to GitHub Code Scanning.
- Adds an optional `bootstrap --include-review-template` scaffold for CODEOWNERS
  and Lake Formation policy pull request checklists.
- Adds an optional `bootstrap --include-editor-config` scaffold for VS Code
  schema validation against generated desired policy files.
- Adds docs tests for internal Markdown links.
- Adds package metadata tests for version, console scripts, and project URLs.
- Modernizes the build backend requirement for current setuptools releases.
- Uses SPDX license metadata without deprecated license classifiers.
