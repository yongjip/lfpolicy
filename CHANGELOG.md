# Changelog

## Unreleased

- Adds `lfguard permissions --check` for live IAM preflight checks using STS
  caller identity and IAM policy simulation against the existing read-only,
  additive-apply, and destructive-apply templates.
- Exposes reusable IAM permission template and permission-check helpers for
  direct library integrations.
- Adds structured Python policy validation findings with stable codes, field
  paths, suggestions, and `PolicyValidationError` for clearer `lfguard generate`
  failures.
- Adds `examples/policy-from-import.py` plus authoring and adoption docs for
  converting reviewed import scaffolds into maintainable `policy.py` sources.
- Adds checked-in example evidence artifacts for audit JSON, plan JSON, explain
  JSON, and apply dry-run Markdown reports.
- Adds `lfguard import --review-notes` to write a Markdown adoption checklist,
  imported-surface summary, suggested commands, and bounded-discovery warnings
  beside imported desired-state scaffolds.
- Fixes `lfguard explain` effective LF-Tag evidence for column-level same-key
  overrides and adds real-world explain coverage for mixed direct/LF-Tag grants
  and data-location context.

## 0.6.3

- Adds governance workflow documentation for CI evidence, Terraform/CDK
  coexistence, import adoption, exception lifecycle, and permission request
  bundles.
- Adds a runnable `examples/permission-requests.py` policy that models approved
  access requests as policy data without adding approval workflow UI to core.
- Links the new operating-model docs from README, examples, adoption,
  positioning, framework, GitHub Actions, and roadmap pages.

## 0.6.2

- Adds `CachedCurrentStateProvider.for_aws(...)` and
  `aws_current_state_provider_context(...)` so direct library users can scope
  live AWS current-state caches consistently with the CLI.
- Writes current-state caches through unique temporary files before atomic
  replace, avoiding fixed temporary-path collisions when jobs share a cache
  directory.

## 0.6.1

- Scopes current-state cache hits by provider context as well as desired-state
  scope, including the CLI AWS provider, profile, region, and catalog ID.
- Keeps safe `SELECT` grants on Lake Formation data cells filters lint-clean by
  default while retaining the mutating-permission guardrail.
- Updates the generated sample and customer-facing docs to demonstrate data
  cells filter explain workflows and scoped live cache usage.

## 0.6.0

- Adds `CachedCurrentStateProvider`, a read-through JSON cache wrapper for any
  `CurrentStateProvider`.
- Adds `--current-cache`, `--refresh-current-cache`, and
  `--current-cache-max-age` to live current-state CLI paths so `audit`, `plan`,
  `explain`, and desired-driven `apply` can reuse cached current state without
  constructing the AWS adapter on cache hits.
- Adds managed `data_cells_filters` definitions for Lake Formation
  `DataCellsFilter` bodies, including create/update/delete planning, audit
  drift, lint duplicate-identity checks, explain evidence, live inventory, and
  bounded import.
- Adds `--allow-data-cells-filter-updates` and
  `--allow-data-cells-filter-deletes` destructive planning/apply gates.

## 0.5.2

- Adds catalog-scoped LF-Tag definitions so same-name tag keys in different
  catalogs are planned, audited, linted, and applied independently.
- Adds Stubber coverage for catalog-scoped LF-Tag definition inventory plus
  LF-Tag definition, resource tag, and table grant apply request shapes.
- Adds catalog-aware Python policy authoring for tag keys, resource tag
  assignments, LF-Tag policy bundles, and catalog creator bundles.
- Rejects duplicate exact LF-Tag and LF-Tag key metadata identities so
  catalog-scoped list-form state cannot be silently collapsed by shared
  indexes.
- Preserves the requested catalog ID in live import and scoped current-state
  loading when Lake Formation responses omit `CatalogId`.
- Adds catalog-specific effective LF-Tag evidence to `explain` reports and uses
  scoped grant catalogs when evaluating LF-Tag policy matches for unscoped
  targets.
- Reports wholly unmanaged current LF-Tag definitions in audit evidence, with
  catalog-aware ownership and ignore handling.
- Reports wholly unmanaged current resource tag assignments in audit evidence,
  with catalog-aware ownership and ignore handling.
- Plans destructive removal of unmanaged current resource tag assignments and
  unmanaged tag keys on desired resources when `--allow-resource-tag-removals`
  is enabled, preserving scoped catalog IDs for live apply.
- Keeps column-level LF-Tag assignments from `get_resource_lf_tags` as separate
  `table_with_columns` resource tag evidence instead of flattening them onto the
  table.
- Includes scoped resource catalog IDs on Lake Formation `LFTagPair` entries
  when adding or removing resource tag assignments.
- Models Lake Formation `DataCellsFilter` grant resources so live permission
  inventory, apply, audit, and explain evidence do not drop row/cell-filtered
  access grants.
- Adds `lfguard explain --data-cells-filter FILTER` so CLI evidence can target
  Lake Formation data cells filter grants directly.
- Adds Stubber coverage for catalog-scoped `DataCellsFilter` grants and
  revokes so live apply preserves `TableCatalogId`.
- Tightens `explain --data-cells-filter` evidence so grants for other filters
  on the same table are reported as non-matches instead of effective access.
- Reports broader table/database grants as relevant evidence when explaining a
  specific data cells filter target.
- Uses Lake Formation grants internally to discover resource-tag import targets
  even when `lfguard import --include resource-tags` omits `grants` from the
  generated desired-state file.
- Requests assigned LF-Tags explicitly when loading resource-tag evidence from
  AWS so planned assignment drift is not based on inherited tag context.
- Adds Stubber coverage for catalog-scoped data-location grant apply, revoke,
  and live inventory request shapes.
- Makes `explain` missing-desired-grant evidence account for broader current
  database/table/column grants that already cover narrower desired resources,
  while keeping filtered grants from satisfying full table desired grants.
- Makes lint resolve catalog-scoped named LF-Tag expression bodies for
  column-narrowing safety checks, reducing false positives for table-only named
  expressions.
- Constrains `explain` named LF-Tag expression lookup by the target/effective
  catalog when a grant omits `catalog_id`, avoiding cross-catalog evidence
  matches.
- Makes resource-tag plan changes deterministic by resource identity and tag
  key so review IDs do not depend on input ordering.
- Adds Stubber coverage for catalog-scoped named LF-Tag expression grants and
  revokes used by stewardship bundles.
- Keeps `explain` from treating unscoped current grants as proof that a
  catalog-scoped desired grant is present, while still showing the current grant
  as relevant evidence.
- Makes catalog-scoped ownership boundaries include matching unscoped current
  grants, so broad unmanaged grants are not hidden outside the managed catalog.
- Treats current `ALL`/`SUPER_USER` grants as covering concrete desired
  permissions in audit, explain, and planning evidence while still reporting
  broad grants as unmanaged policy drift.
- When destructive permission revokes are enabled, adds desired concrete
  permissions before revoking broad current permissions such as `ALL` so the
  resulting plan still converges to desired access.

## 0.5.1

- Preserves catalog IDs for catalog resources in AWS grant apply and inventory
  conversion, including `Catalog.Id` and payload catalog precedence over the
  adapter default.
- Makes `explain` ignore catalog-scoped grants when the target resource is in a
  different catalog.

## 0.5.0

- Adds `lfguard.audit.v1` JSON schema metadata and deterministic audit
  `finding_001` identifiers.
- Adds deterministic `finding_001` identifiers to explain JSON and the
  importable `ExplainReport` findings.
- Adds scoped policy exceptions with required reason, expiry, and owner or
  approver metadata.
- Makes mutating, grantable, and named-resource governance lint findings errors
  by default unless covered by a matching non-expired exception or lint override.
- Extends `validate` to reject duplicate named LF-Tag expression identities in
  desired state and current snapshots.
- Adds generic policy bundle primitives: `producer()`, `steward()`, `admin()`,
  and `data_location_access()`, alongside the existing `reader()`, `editor()`,
  `table_creator()`, and `database_creator()`.
- Adds framework documentation and a policy-exception example.

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
