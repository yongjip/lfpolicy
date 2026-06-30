# CLI Reference

`lfguard` installs one console command: `lfguard`.

Use `lfguard --help` or `lfguard <command> --help` for argparse-generated help.

## Command Tiers

Start with the core workflow:

1. `review` writes the approval bundle: lint, audit, plan, planned grant
   evidence, and summaries.
2. `explain-batch` answers operational access questions from a snapshot.
3. `check`, `audit`, and `plan` run focused validation, drift, or change checks.
4. `apply` dry-runs by default and executes only with `--execute`.

Everything else is supporting workflow. Use `sample`, `init`, `generate`,
`bootstrap`, `schema`, `doctor`, `permissions`, `completion`, `validate`,
`lint`, `summary`, `explain`, `snapshot`, and `import` when they remove real
setup or review friction. They are not the reason to adopt the package.

## Command Overview

| Command | Purpose | AWS calls |
| --- | --- | --- |
| `check` | Validate and lint local policy files in one CI-friendly command. | No |
| `audit` | Report drift between desired and current state. | Only when `--current-snapshot` is omitted |
| `plan` | Produce a conservative change plan. | Only when `--current-snapshot` is omitted |
| `review` | Write lint, audit, plan, planned grant evidence, and summaries to one directory. | Only when `--current-snapshot` is omitted |
| `apply` | Dry-run or execute a Lake Formation change plan. | Yes when live state is loaded or `--execute` is used |
| `explain` | Explain current access for one principal and resource. | Only when `--current-snapshot` is omitted |
| `explain-batch` | Explain multiple access requests from one current-state snapshot. | Only when `--current-snapshot` is omitted |
| `init` | Generate a starter desired-state policy file. | No |
| `generate` | Generate desired state from a Python policy file. | No |
| `bootstrap` | Create a starter policy repository layout with CI and pre-commit files. | No |
| `sample` | Generate offline demo desired/current state files. | No |
| `schema` | Emit the JSON Schema for desired/current state files. | No |
| `doctor` | Check the local install and optional extras. | No |
| `permissions` | Emit starter IAM policies for live AWS workflows. | No |
| `completion` | Emit shell completion scripts for bash, zsh, or fish. | No |
| `validate` | Parse and validate local desired/current state files. | No |
| `lint` | Check desired policy semantics, such as undefined LF-Tag references. | No |
| `summary` | Summarize desired and optional current state for review. | No |
| `snapshot` | Export live AWS state for a desired policy scope. | Yes |
| `import` | Import live AWS state into a starter desired-state file for review. | Yes |

## Common Options

State-aware commands use these options:

- `--desired PATH`: desired state JSON/YAML file.
- `--current-snapshot PATH`: current state JSON/YAML file. When omitted,
  `audit`, `plan`, `review`, `explain`, `explain-batch`, and `apply` load live
  AWS state through `boto3`.
- `--current-cache PATH`: read or write a JSON current-state cache when live AWS
  state would otherwise be loaded. Cache hits avoid constructing the AWS
  adapter; cache misses, stale entries, desired-state scope mismatches, and AWS
  provider context mismatches refresh from AWS. The CLI cache context includes
  provider type, AWS profile, AWS region, and catalog ID.
- `--refresh-current-cache`: force `--current-cache` to refresh from AWS.
- `--current-cache-max-age SECONDS`: refresh `--current-cache` when its entry is
  older than the given age.
- `--profile NAME`: AWS profile for live operations.
- `--region NAME`: AWS region for live operations.
- `--catalog-id ID`: Glue Data Catalog ID.
- `--output text|json|markdown|sarif`: output format where supported. `audit`
  and `lint` support SARIF; `permissions`, `lint`, `summary`, `audit`,
  `explain`, `explain-batch`, `plan`, and `apply` support Markdown.
- `--output-file PATH`: write the command report to a file instead of stdout
  where supported. `doctor`, `permissions`, `completion`, `check`, `validate`,
  `lint`, `summary`, `audit`, `explain`, `explain-batch`, `plan`, and `apply`
  support this for reports; `init`, `schema`, and `snapshot` use it for generated files.
  `import` uses `--output` for the generated desired-state path and `--format`
  for JSON/YAML.
- `--github-summary`: append a Markdown report to `$GITHUB_STEP_SUMMARY` where
  supported.

See [`state-format.md`](state-format.md) for desired/current state examples for
each supported Lake Formation resource kind.

YAML files require the optional extra:

```bash
python -m pip install "lfguard[yaml]"
```

Live AWS commands require the AWS extra:

```bash
python -m pip install "lfguard[aws]"
```

Current-state cache files are JSON envelopes, not plain current snapshots. Use
`--current-snapshot` for reviewed immutable evidence, and `--current-cache` when
you want repeated live workflows to share a scoped current-state lookup. Pass
`--profile`, `--region`, and `--catalog-id` explicitly for cached live workflows
and keep separate cache paths per account, environment, region, and catalog.

For isolated CLI installs, use `pipx install lfguard` or
`uv tool install lfguard`. Add extras with pip when you need live AWS or YAML
support inside a project environment.

## Exit Codes

| Code | Meaning |
| --- | --- |
| `0` | Command completed successfully. |
| `1` | A CI gate failed, such as `check --fail-on-findings`, `audit --fail-on-findings`, or `plan --fail-on-changes`. |
| `2` | CLI usage, file format, validation, or runtime configuration error. |

Report files and GitHub summaries are written before `check --fail-on-findings`,
`lint --fail-on-findings`, `audit --fail-on-findings`, or
`plan --fail-on-changes` return exit code `1`.

See [`report-formats.md`](report-formats.md) for JSON and Markdown payload
examples for check, summary, audit, explain, plan, and apply reports.

## `review`

Write a complete approval bundle:

```bash
lfguard review \
  --desired desired.json \
  --current-snapshot current.json \
  --output-dir review/
```

The bundle contains:

- `manifest.json`: schema version, lfguard version, input hashes, status, and
  artifact list.
- `summary.md` and `summary.json`: human and machine summaries.
- `lint.json`, `audit.json`, `plan.json`, and `explain.json`: stable evidence
  files for services, LLM agents, pull requests, tickets, and audit logs.
  `explain.json` is review-specific planned grant-change evidence; use
  `explain-batch` for effective-access decisions.

Use `--fail-on-blocked` when CI should fail only on hard-block findings or
destructive planned changes. Non-blocking lint errors keep their `severity:
error` signal but are surfaced as `review_required` or `approval_required`
recommended actions. Audit findings and safe planned changes set the review
status to `review_required`. Existing bundle files are not overwritten unless
`--force` is passed.

Service-embedded LLM agents should follow
[`llm-agent-integration.md`](llm-agent-integration.md) when interpreting
`severity`, `recommended_action`, `hard_block`, and `blocking_reasons`.
Backend services that wrap lfguard should follow
[`service-integration.md`](service-integration.md) and consume CLI JSON
artifacts instead of private Python internals.

## `explain-batch`

Explain multiple access requests from one snapshot:

```bash
lfguard explain-batch \
  --requests access-requests.json \
  --current-snapshot current.json \
  --output json
```

The request file may contain either a top-level array or an object with a
`requests` array:

```json
{
  "requests": [
    {
      "id": "analyst-orders",
      "principal": "arn:aws:iam::111122223333:role/Analyst",
      "database": "analytics",
      "table": "orders",
      "permissions": ["SELECT"]
    }
  ]
}
```

Pass `--desired desired.json` when the output should also include desired-grant
gap evidence. Use `--fail-on-denied` when denied requests should fail CI.
For adapter tests, see `examples/access-requests.json`,
`examples/access-current-snapshot.json`, and
`examples/artifacts/lfguard-explain-batch.json`.

## `init`

Generate a starter desired policy:

```bash
lfguard init --output-file policy/desired.json
```

Useful options:

- `--output-file PATH`: write the starter policy to a file.
- `--format json|yaml`: force the output format.
- `--template data-domain|blank`: choose the starter policy. `data-domain`
  includes example LF-Tags, one table tag assignment, and one LF-Tag policy
  grant. `blank` writes an empty valid policy skeleton.
- `--force`: overwrite an existing output file.

When `--format` is omitted, `.yaml` and `.yml` output paths produce YAML;
stdout defaults to JSON.

```bash
lfguard init --template blank --output-file policy/desired.json
```

## `generate`

Generate desired state from a Python policy file:

```bash
lfguard generate policy.py --output-file policy/desired.json
lfguard generate policy.py --output-file policy/desired.json --check
lfguard check --desired policy/desired.json --fail-on-findings
```

The policy file should define a `LakePolicy` named `policy`:

```python
from lakeformation_guard.policy import LakePolicy, TagAssignmentScope, reader, table_creator

policy = LakePolicy()
policy.tag_key(
    "domain",
    values=["sales", "finance"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
)
policy.tag_database("sales_curated", domain="sales")
policy.tag_table("sales_curated", "customers", domain="sales")
policy.group("dataconsumer", reader().where(domain="sales"))
policy.group("dataengineer", table_creator().where(domain="sales"))
```

Use mapping form for LF-Tag keys that cannot be Python keyword arguments:

```python
policy.group("dataconsumer", reader().where({"data-domain": "sales"}))
policy.tag_table("sales_curated", "customers", tags={"data-domain": "sales"})
```

Useful options:

- `policy.py`: Python file to load.
- `--object NAME`: load a different object or zero-argument factory. Defaults
  to `policy`.
- `--output-file PATH`: write generated desired state to a file.
- `--format json|yaml`: force the generated output format.
- `--check`: fail if the output file does not match the generated desired
  state. Use this in CI to keep `policy.py` and `policy/desired.*` in sync.
- `--force`: overwrite an existing output file.

## `bootstrap`

Create a starter policy repository layout:

```bash
lfguard bootstrap --output-dir lfguard-policy
```

The generated layout includes:

- `policy.py`: Python source of truth for permission groups.
- `policy/desired.json`: generated desired LF-Tag and grant policy.
- `policy/lfguard.schema.json`: JSON Schema for editor integration.
- `.github/workflows/lfguard-policy.yml`: offline check, summary, and artifact
  workflow. It runs `lfguard generate` before `lfguard check`.
- `.pre-commit-config.yaml`: local generate-and-check hook.
- `README.md`: rollout steps and first commands.

Useful options:

- `--format json|yaml`: choose the desired policy file format. YAML workflows
  install `lfguard[yaml]`.
- `--template data-domain|blank`: choose the starter policy. `data-domain`
  writes a Python permission-group policy; `blank` writes an empty `LakePolicy`.
- `--include-live-drift`: also write `.github/workflows/lfguard-live-drift.yml`
  and `iam/lfguard-read-only.json` for scheduled live AWS drift checks through
  GitHub OIDC.
- `--include-code-scanning`: also write
  `.github/workflows/lfguard-code-scanning.yml` for GitHub Code Scanning SARIF
  upload. This also writes `iam/lfguard-read-only.json`.
- `--include-review-template`: also write `.github/CODEOWNERS` and
  `.github/pull_request_template.md` for Lake Formation policy review.
- `--include-editor-config`: also write `.vscode/settings.json` so VS Code
  validates the desired policy against `policy/lfguard.schema.json`. YAML
  bootstraps also get `.vscode/extensions.json` recommending YAML support.
- `--policy-owner OWNER`: CODEOWNERS owner for generated policy review files.
- `--aws-role-arn ARN`: role ARN to place in generated live AWS workflows.
- `--aws-region REGION`: AWS region to place in generated live AWS workflows.
- `--force`: overwrite existing bootstrap files.

Optional scaffold examples:

```bash
lfguard bootstrap --output-dir lfguard-policy --include-live-drift
lfguard bootstrap --output-dir lfguard-policy --include-code-scanning
lfguard bootstrap --output-dir lfguard-policy --include-review-template
lfguard bootstrap --output-dir lfguard-policy --include-editor-config
```

## `sample`

Generate paired offline demo files that work immediately after `pip install`:

```bash
lfguard sample --output-dir lfguard-demo --include-ci
lfguard plan \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

The generated policy includes an LF-Tag policy grant, a Lake Formation data
cells filter definition, a missing `SELECT` grant on that filter, an explain
example for the filtered grant, and a live cache example that scopes the cache
by profile, region, catalog, and desired state.

Useful options:

- `--output-dir PATH`: directory to write `desired.json` and
  `current-snapshot.json`, plus a local `README.md` with demo commands.
- `--format json|yaml|both`: choose JSON sample files, YAML sample files, or
  both. YAML files require `lfguard[yaml]` when read by later commands.
- `--include-ci`: also write `.github/workflows/lfguard-demo.yml`, an offline
  GitHub Actions workflow that validates, lints, audits, plans, and uploads
  report artifacts for the generated sample files.
- `--force`: overwrite existing sample files.

## `schema`

Write the JSON Schema for editor integration or CI validation:

```bash
lfguard schema --output-file policy/lfguard.schema.json
```

## `doctor`

Check the install, Python runtime, optional dependencies, and AWS-related
environment variables without making AWS calls:

```bash
lfguard doctor
lfguard doctor --output json
lfguard doctor --require aws --require yaml
lfguard doctor --output json --output-file artifacts/lfguard-doctor.json
```

Use `--require aws` or `--require yaml` to return exit code `1` when a needed
optional extra is missing. Repeat `--require` to check multiple extras.

## `permissions`

Generate starter IAM policies, or check whether the role about to run a live
workflow has the selected permissions:

```bash
lfguard permissions --template read-only --output-file iam/lfguard-read-only.json
lfguard permissions --template additive-apply --include-glue-read
lfguard permissions --template destructive-apply --output markdown
lfguard permissions --check --template read-only --profile prod --output json
lfguard permissions --check --template additive-apply \
  --principal-arn arn:aws:iam::111122223333:role/LfguardApply
```

Useful options:

- `--template read-only|additive-apply|destructive-apply`: choose the IAM
  policy template. `additive-apply` omits revoke and tag-removal actions;
  `destructive-apply` includes them for separately reviewed workflows.
- `--include-glue-read`: add common Glue Data Catalog read actions.
- `--check`: call AWS STS and IAM policy simulation to verify the selected
  template against the current caller or `--principal-arn`.
- `--principal-arn ARN`: IAM role/user ARN to simulate. When omitted, `lfguard`
  uses `sts:GetCallerIdentity` and normalizes an assumed-role ARN to the
  underlying IAM role ARN.
- `--profile PROFILE`, `--region REGION`: AWS profile and region for
  `--check`.
- `--output text|json|markdown`: choose raw JSON or a Markdown report. Text and
  JSON both emit copyable IAM policy JSON unless `--check` is set, in which
  case they emit permission-check evidence.
- `--output-file PATH`: write the policy to a file instead of stdout.

`--check` exits `0` when every required action is allowed and `1` when any
required action is denied or missing. The JSON report uses
`schema_version: "lfguard.permissions-check.v1"` and includes the simulated
principal, caller ARN when discovered, per-action IAM decisions, and denied
actions. The caller running `--check` must be allowed to call
`iam:SimulatePrincipalPolicy` for the simulated principal.

## `completion`

Emit shell completion scripts:

```bash
lfguard completion --shell bash
lfguard completion --shell zsh --output-file ~/.zsh/completions/_lfguard
lfguard completion --shell fish --output-file ~/.config/fish/completions/lfguard.fish
```

For the current bash session:

```bash
source <(lfguard completion --shell bash)
```

Useful options:

- `--shell bash|zsh|fish`: choose the shell format. Defaults to `bash`.
- `--output-file PATH`: write the completion script to a file instead of
  stdout.

## `check`

Validate and lint local policy files in one offline command:

```bash
lfguard check --desired policy/desired.json --fail-on-findings
lfguard check \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output markdown \
  --output-file artifacts/lfguard-check.md \
  --github-summary \
  --fail-on-findings
```

Useful options:

- `--current-snapshot PATH`: also validate a current-state snapshot file.
- `--fail-on-findings`: return exit code `1` when any lint finding exists.
- `--fail-on-severity any|error`: severity that triggers `--fail-on-findings`.
- `--github-summary`: append the Markdown check report to GitHub Actions.

## `validate`

Validate local policy files:

```bash
lfguard validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

`validate` does not call AWS. Use it in pre-commit hooks or CI before comparing
against live state. It also enforces model invariants such as unique
`(catalog_id, name)` identities for named LF-Tag expressions and unique
`(catalog_id, database, table, name)` identities for data cells filters.

```bash
lfguard validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output-file artifacts/lfguard-validate.txt
```

## `lint`

Lint desired policy for semantic issues that parse-time validation cannot catch:

```bash
lfguard lint --desired policy/desired.json
```

`lint` does not call AWS. It catches undefined LF-Tag keys and values used in
resource tag assignments and LF-Tag policy expressions. It also warns when a
desired policy is empty.

CI-friendly lint gate:

```bash
lfguard lint \
  --desired policy/desired.json \
  --output json \
  --output-file artifacts/lfguard-lint.json \
  --fail-on-findings \
  --github-summary
```

Useful options:

- `--fail-on-findings`: return exit code `1` when any lint finding exists.
- `--fail-on-severity any|error`: severity that triggers `--fail-on-findings`.
  Use `error` when warnings should stay visible but should not fail CI.
- `--output sarif`: write lint findings as SARIF 2.1.0 for code scanning,
  governance dashboards, or artifact ingestion.

## `summary`

Summarize policy inventory without calling AWS:

```bash
lfguard summary \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

Use it in pull requests when reviewers need a compact view of LF-Tag keys,
resource kinds, grant principals, grant resource kinds, and permissions:

```bash
lfguard summary \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output markdown \
  --output-file artifacts/lfguard-summary.md \
  --github-summary
```

## `audit`

Report drift between desired and current state:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

CI-friendly audit:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output json \
  --output-file artifacts/lfguard-audit.json \
  --fail-on-findings
```

Useful options:

- Audit text, JSON, and Markdown output include a severity summary. JSON reports
  expose `summary.total`, `summary.errors`, and `summary.warnings`.
- `--output sarif`: write audit findings as SARIF 2.1.0 for code scanning,
  governance dashboards, or artifact ingestion.
- `--fail-on-findings`: return exit code `1` when any finding exists.
- `--fail-on-severity any|error`: severity that triggers `--fail-on-findings`.
  The default is `any`, which preserves strict drift gates. Use `error` when
  unmanaged extras should remain visible warnings but not fail CI.
- `--github-summary`: append a Markdown audit report to the GitHub Actions job
  summary.

## `plan`

Produce a conservative change plan:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

For repeated live planning against the same desired scope, cache current state
behind the provider boundary:

```bash
lfguard plan \
  --desired policy/desired.json \
  --profile prod \
  --region us-east-1 \
  --catalog-id 111122223333 \
  --current-cache .lfguard/prod-us-east-1-111122223333-current.json \
  --current-cache-max-age 900
```

Pass `--refresh-current-cache` when you want to force a new live read before
planning.

By default, the plan includes additive changes only. Destructive changes are
omitted unless the matching allow flag is set.

CI-friendly plan gate:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output markdown \
  --output-file artifacts/lfguard-plan.md \
  --fail-on-changes
```

Save a reviewed JSON plan for later selective apply:

```bash
lfguard plan --desired desired.json --output json --output-file plan.json
```

Destructive planning flags:

- `--allow-lf-tag-value-removals`
- `--allow-lf-tag-expression-updates`
- `--allow-lf-tag-expression-deletes`
- `--allow-data-cells-filter-updates`
- `--allow-data-cells-filter-deletes`
- `--allow-resource-tag-removals`
- `--allow-permission-revokes`

## `explain`

Explain current access for one principal and resource:

```bash
lfguard explain \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --principal arn:aws:iam::111122223333:role/Analyst \
  --database analytics \
  --table orders \
  --permissions SELECT
```

`explain` reports direct grants, LF-Tag policy grants, named LF-Tag expression
matches, effective LF-Tags on the target, data-location grant context, data
cells filter definitions for matching filtered grants, and desired grants that
are missing from current state. It does not apply changes.

Target options:

- `--database NAME`: explain a database resource.
- `--database NAME --table NAME`: explain a table resource.
- `--database NAME --table NAME --columns c1,c2`: explain a column subset.
- `--database NAME --table NAME --data-cells-filter FILTER`: explain a Lake
  Formation data cells filter grant.
- `--location S3_ARN_OR_PATH`: explain a data-location resource instead of a
  catalog resource.

Useful options:

- `--principal ARN_OR_ID`: required Lake Formation principal.
- `--permissions LIST`: optional comma-separated permissions that must be
  covered by matching grants.
- `--output text|json|markdown`: choose report format.
- `--github-summary`: append the Markdown explain report to the GitHub Actions
  job summary.

When `--current-snapshot` is omitted, live loading is still scoped. The desired
file should include the LF-Tag policy grants or named LF-Tag expressions you
want explained; otherwise use `lfguard import` or `lfguard snapshot` first for
a broader reviewed snapshot.

## `snapshot`

Export live AWS state for the resources and principals referenced by the desired
policy:

```bash
lfguard snapshot \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2 \
  --output-file snapshots/prod-current.json
```

`snapshot` uses the desired policy as the scope so it does not attempt to
inventory an entire account.

## `import`

Import live AWS state into a starter desired-state file:

```bash
lfguard import \
  --catalog-id 123456789012 \
  --include lf-tags,lf-tag-expressions,data-cells-filters,resource-tags,grants \
  --output policy/imported-desired.json \
  --review-notes policy/import-review.md
```

`import` is for adoption scaffolding, not automatic synchronization. Review the
generated file, remove unmanaged legacy access that should stay outside
`lfguard`, then commit the desired state you intend to own. Use
`--review-notes` to write a Markdown checklist and bounded-discovery warnings
beside the scaffold.

Useful options:

- `--include`: comma-separated sections to import. Supported values are
  `lf-tags`, `lf-tag-expressions`, `data-cells-filters`, `resource-tags`, and
  `grants`.
- `--output PATH`: write the starter desired-state file. This is required.
- `--format json|yaml`: force the output format. When omitted, `.yaml` and
  `.yml` paths produce YAML; other paths produce JSON.
- `--review-notes PATH`: write Markdown import review notes with imported
  surface counts, review checklist items, suggested next commands, and warnings
  about bounded resource-tag and data-cells-filter discovery.
- `--force`: overwrite an existing output file.

Resource-tag import is intentionally bounded. `lfguard` reads LF-Tag
assignments for resources discovered through Lake Formation grants, even when
`resource-tags` is requested without including `grants` in the generated file.
It does not crawl the whole Glue Data Catalog.

Data-cells-filter import is also bounded. `lfguard` lists filters only for
tables discovered through imported grants, even when `data-cells-filters` is
requested without including `grants` in the generated file.

## `apply`

Dry-run by default:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2
```

Save the dry-run report:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2 \
  --output markdown \
  --output-file artifacts/lfguard-apply-dry-run.md
```

Execute additive changes:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2 \
  --execute
```

Save executed results:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2 \
  --execute \
  --output json \
  --output-file artifacts/lfguard-apply.json
```

Apply a reviewed saved plan without recomputing current state:

```bash
lfguard apply --plan plan.json --only change_001 --execute
lfguard apply --plan plan.json --only-action grant.add_permissions --max-changes 10 --execute
```

Saved plans must be JSON reports from `lfguard plan --output json`. Use
`--only` for comma-separated change IDs or `--only-action` for comma-separated
action names; the two selectors cannot be combined. `--max-changes` and
`--max-destructive` fail before AWS calls if the selected plan exceeds the
budget.

Even during execution, destructive changes require the same explicit allow flags
used by `plan`. For saved plans, each destructive change requires its exact
matching flag, such as `--allow-permission-revokes` for
`grant.revoke_permissions`.
