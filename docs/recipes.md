# Recipes

These workflows are intended to keep Lake Formation changes reviewable and
conservative.

The core recipes are `check`, `audit`, `plan`, and dry-run `apply`. Setup
helpers such as `doctor`, `completion`, `bootstrap`, `schema`, and
`permissions` are included only when they remove real friction from that core
workflow.

## Start a Policy File

Confirm the installed CLI, Python runtime, optional extras, and AWS-related
environment variables without making AWS calls:

```bash
lfguard doctor
```

Save a JSON diagnostics artifact when debugging CI installs:

```bash
lfguard doctor --output json --output-file artifacts/lfguard-doctor.json
```

Fail early when a workflow needs optional AWS or YAML integrations:

```bash
lfguard doctor --require aws --require yaml
```

## Enable Shell Completion

Load completions into the current bash session:

```bash
source <(lfguard completion --shell bash)
```

Write persistent zsh or fish completion files:

```bash
lfguard completion --shell zsh --output-file ~/.zsh/completions/_lfguard
lfguard completion --shell fish --output-file ~/.config/fish/completions/lfguard.fish
```

## Bootstrap a Policy Repository

Generate a starter policy-as-code layout when you want schema, CI, and
pre-commit files in one step:

```bash
lfguard bootstrap --output-dir lfguard-policy
```

Use YAML when that matches the repository convention:

```bash
lfguard bootstrap --output-dir lfguard-policy --format yaml
```

The generated workflow is offline: it validates, lints, summarizes, and uploads
report artifacts for the desired policy without calling AWS.

## Generate IAM Policy Starters

Generate IAM policy JSON before wiring live AWS snapshot or apply jobs:

```bash
lfguard permissions --template read-only --include-glue-read \
  --output-file iam/lfguard-read-only.json

lfguard permissions --template additive-apply \
  --output-file iam/lfguard-additive-apply.json
```

Keep destructive permissions separate from routine automation:

```bash
lfguard permissions --template destructive-apply \
  --output-file iam/lfguard-destructive-apply.json
```

For day-to-day policy repositories, edit the generated `policy.py`, then
regenerate and check desired state:

```bash
cd lfguard-policy
lfguard generate policy.py --output-file policy/desired.json --force
lfguard check --desired policy/desired.json --fail-on-findings
```

Use `init` only when you intentionally want to hand-author raw desired-state
JSON or YAML instead of using the Python policy builder:

```bash
lfguard init --output-file policy/desired.json
```

## Try a Local Demo

Generate paired desired/current files when you want to see a plan before wiring
`lfguard` into AWS or CI:

```bash
lfguard sample --output-dir lfguard-demo
lfguard plan \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

The generated current snapshot is deliberately incomplete, so the plan contains
safe additive changes. The sample directory also includes a local `README.md`
with validate, audit, plan, and report commands.

Add `--include-ci` when you also want a starter GitHub Actions workflow for the
offline demo:

```bash
lfguard sample --output-dir lfguard-demo --include-ci
```

Generate a YAML demo when your policy repo uses YAML:

```bash
lfguard sample --output-dir lfguard-demo-yaml --format yaml
```

Reading the generated YAML files requires `python -m pip install "lfguard[yaml]"`.

## Use the JSON Schema

Write the schema to your policy directory and point your editor or CI validator
at it:

```bash
lfguard schema --output-file policy/lfguard.schema.json
```

## Validate Policy Files

Run this when you want a validation-only file check before comparing against
AWS state:

```bash
lfguard validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

The command does not call AWS. It parses the files, validates the supported
resource shapes, normalizes permission names, and reports object counts.

To preserve validation evidence in CI:

```bash
lfguard validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output-file artifacts/lfguard-validate.txt
```

## Check Local Policy

Use `check` when a workflow should validate files and lint desired policy in one
offline gate:

```bash
lfguard check \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output markdown \
  --output-file artifacts/lfguard-check.md \
  --fail-on-findings \
  --github-summary
```

## Lint Desired Policy

Run this before snapshot, audit, plan, or apply when you want to catch
undefined LF-Tag keys and values in the desired policy:

```bash
lfguard lint --desired policy/desired.json
```

Use it as a CI gate:

```bash
lfguard lint \
  --desired policy/desired.json \
  --output sarif \
  --output-file artifacts/lfguard-lint.sarif

lfguard lint \
  --desired policy/desired.json \
  --output json \
  --output-file artifacts/lfguard-lint.json \
  --fail-on-findings \
  --github-summary
```

## Summarize Policy Inventory

Generate a compact inventory for reviewers:

```bash
lfguard summary \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output markdown \
  --output-file artifacts/lfguard-summary.md \
  --github-summary
```

## Audit in CI

Store desired state in the repository and compare it with a current-state
snapshot generated by your platform automation.

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --fail-on-findings \
  --output json
```

Use this for pull requests when you want drift to block merge until the desired
policy or AWS state is reconciled.

Use error-only gating when unmanaged extras should stay visible but should not
block a merge:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --fail-on-findings \
  --fail-on-severity error
```

Write the audit report to a file when your CI system should upload it as an
artifact:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --fail-on-findings \
  --output json \
  --output-file artifacts/lfguard-audit.json
```

The JSON report includes `summary.total`, `summary.errors`, and
`summary.warnings` for compact CI annotations and dashboards.

## Write a GitHub Summary

Use `--github-summary` when a workflow should leave a readable summary in the
GitHub Actions run:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --fail-on-findings \
  --github-summary
```

## Capture a Live Snapshot

Generate the current-state snapshot from AWS using the desired-state file as the
scope. `lfguard` reads only the LF-Tags, resources, and grants needed for that
comparison.

```bash
lfguard snapshot \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2 \
  --output-file snapshots/prod-current.json
```

Commit sanitized desired state to source control. Treat generated snapshots as
environment evidence and store them according to your organization's data
classification rules.

## Plan Safe Changes

Create a plan without destructive operations:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

By default, `lfguard` plans additions only: missing LF-Tag definitions, missing
LF-Tag values, missing resource tag assignments, and missing permissions.

Use `--fail-on-changes` when a non-empty plan should fail a CI job:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --fail-on-changes
```

Save Markdown or JSON plans for review outside the job log:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output markdown \
  --output-file artifacts/lfguard-plan.md
```

## Apply Additive Changes

Run a dry run against live AWS first:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2
```

Save the dry-run as a review artifact:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2 \
  --output markdown \
  --output-file artifacts/lfguard-apply-dry-run.md
```

Execute only after reviewing the plan:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2 \
  --execute
```

For change records, write the executed plan and adapter responses as JSON:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile prod \
  --region ap-northeast-2 \
  --execute \
  --output json \
  --output-file artifacts/lfguard-apply.json
```

## Review Destructive Operations Separately

Revokes and removals are not planned unless explicitly allowed:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --allow-lf-tag-deletes \
  --allow-permission-revokes \
  --allow-resource-tag-removals \
  --allow-lf-tag-value-removals
```

Use a separate approval path for these plans. A good operational pattern is to
run additive changes continuously and destructive changes only during scheduled
governance maintenance.

## Suggested Repository Layout

```text
policy/
  desired.json
snapshots/
  prod-current.json
.github/workflows/
  lakeformation-drift.yml
```

Keep generated snapshots out of the release package unless they are sanitized.
Snapshots can include principal ARNs, catalog locations, and table names that may
be sensitive.
