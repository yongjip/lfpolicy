# Examples

These files let you try `lfguard` without AWS credentials:

- `desired.json`: a desired Lake Formation LF-Tag and grant policy.
- `desired.yaml`: the same desired policy in YAML.
- `policy-exceptions.json`: a narrow example of exception-controlled risky
  access with reason, expiry, and approval metadata.
- `policy.py`: a Python-native permission group policy that can generate
  desired state.
- `policy-from-import.py`: a migration example that keeps an imported desired
  state reference beside the equivalent Python policy model.
- `policy-bundles.py`: a Python-native policy using generic permission bundles
  such as `reader()`, `producer()`, `steward()`, `data_location_access()`, and
  `admin()`.
- `permission-requests.py`: a Python-native policy that models approved access
  requests as data and compiles them to ordinary desired state.
- `current-snapshot.json`: a deliberately incomplete current-state snapshot.
- `artifacts/`: checked-in report fixtures for audit, plan, explain, and apply
  dry-run evidence.
- `github-actions/lakeformation-drift.yml`: a copyable GitHub Actions workflow
  for scheduled or manually dispatched drift checks against live AWS state. It
  expects `policy.py` and generated `policy/desired.json` in the policy
  repository.
- `github-actions/lakeformation-code-scanning.yml`: a copyable GitHub Actions
  workflow that checks generated desired state and uploads lint and audit SARIF
  reports to GitHub Code Scanning.
- `pre-commit/pre-commit-config.yaml`: a copyable local pre-commit hook that
  regenerates and checks a desired-state policy before commit.

YAML examples require installing `lfguard[yaml]`; JSON examples work with the
base package.

The snapshot is missing two desired LF-Tag values, one table tag assignment, and
one LF-Tag policy grant. That makes it useful for seeing audit findings and
conservative plans.

The `artifacts/` directory contains pre-generated examples of the JSON and
Markdown evidence a pull request or scheduled governance job would attach:

- `artifacts/lfguard-audit.json`
- `artifacts/lfguard-plan.json`
- `artifacts/lfguard-explain.json`
- `artifacts/lfguard-apply-dry-run.md`

If you installed `lfguard` from PyPI and do not have this repository checked
out, generate the same kind of local demo files with:

```bash
lfguard sample --output-dir lfguard-demo
```

## Check the Policy

```bash
lfguard check \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

This command only reads local files. It validates the desired policy and current
snapshot, then catches undefined LF-Tag keys and values in resource tag
assignments and LF-Tag policy expressions.

## Generate From Python

Use `policy.py` when you want permission groups to be the source of truth:

```bash
lfguard generate examples/policy.py --output-file /tmp/lfguard-desired.json --force
lfguard check --desired /tmp/lfguard-desired.json --fail-on-findings
```

The example assigns LF-Tags to neutral databases, tables, and a sensitive
column. It uses user-defined groups such as `dataconsumer`, `dataengineer`,
`operations`, and `catalog_admin`, while the package supplies the safer
`reader()`, `editor()`, `producer()`, `table_creator()`,
`database_creator()`, `steward()`, `data_location_access()`, and `admin()`
templates.

To see the newer generic bundle names:

```bash
lfguard generate examples/policy-bundles.py --output-file /tmp/lfguard-bundles.json --force
lfguard check --desired /tmp/lfguard-bundles.json --fail-on-findings
```

To see how a reviewed import scaffold can become `policy.py`:

```bash
lfguard generate examples/policy-from-import.py --output-file /tmp/lfguard-migrated.json --force
lfguard check --desired /tmp/lfguard-migrated.json --fail-on-findings
```

To see access requests represented as policy data, without adding an approval UI
to `lfguard` core:

```bash
lfguard generate examples/permission-requests.py --output-file /tmp/lfguard-requests.json --force
lfguard check --desired /tmp/lfguard-requests.json --fail-on-findings
```

The request records include ticket, requester, owner, approver, review date,
target table, requested permissions, and evidence path metadata. After
generating desired state, use [`../docs/permission-request-bundles.md`](../docs/permission-request-bundles.md)
for the review workflow: write request-specific `explain` and `plan` artifacts,
approve exact plan-local change IDs, and apply only those IDs with
`lfguard apply --plan ... --only change_003 --max-changes 1 --max-destructive 0 --execute`.

## Review Exceptions

Use `policy-exceptions.json` to see how intentional risky grants are scoped
without globally weakening lint rules:

```bash
lfguard lint --desired examples/policy-exceptions.json
```

The example suppresses `ALL` and named database grant lint findings only for the
matching principal, resource, permissions, and non-expired exception rules.

## Summarize the Policy

```bash
lfguard summary \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

This produces a compact inventory of LF-Tag keys, resource kinds, grant
principals, grant resource kinds, and permissions for reviewers.

## Audit Drift

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

Expected summary:

```text
Findings: 3 total, 3 error(s), 0 warning(s).
```

To use the audit in CI and save evidence for review:

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output json \
  --output-file artifacts/lfguard-audit.json \
  --fail-on-findings
```

The command writes `artifacts/lfguard-audit.json` before exiting with status `1`.

Use `--fail-on-severity error` when warnings should be reported but should not
fail the job:

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --fail-on-findings \
  --fail-on-severity error
```

## Plan Safe Changes

```bash
lfguard plan \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json
```

Expected summary:

```text
Plan: 3 change(s), 3 safe, 0 destructive.
```

To save a Markdown plan for pull request review:

```bash
lfguard plan \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output markdown \
  --output-file artifacts/lfguard-plan.md
```

By default, the plan is additive only. It will add missing LF-Tag values,
resource tag assignments, and permissions, but it will not revoke permissions or
remove tag values unless a matching `--allow-*` flag is supplied.

## Try YAML

Install the YAML extra, then run the same plan against the YAML desired policy:

```bash
python -m pip install "lfguard[yaml]"
lfguard plan \
  --desired examples/desired.yaml \
  --current-snapshot examples/current-snapshot.json
```

## Copy a GitHub Actions Workflow

Use [`github-actions/lakeformation-drift.yml`](github-actions/lakeformation-drift.yml)
as a starting point when your policy repository already uses GitHub OIDC to
assume an AWS role. Replace the example role ARN, region, and policy paths
before enabling the workflow.

Use [`github-actions/lakeformation-code-scanning.yml`](github-actions/lakeformation-code-scanning.yml)
when your repository can upload SARIF to GitHub Code Scanning. It uploads
separate `lfguard-lint` and `lfguard-audit` categories before enforcing the
check and drift gates.

For the evidence model behind these workflows, see
[`../docs/ci-evidence-workflows.md`](../docs/ci-evidence-workflows.md).

## Copy a Pre-Commit Hook

Use [`pre-commit/pre-commit-config.yaml`](pre-commit/pre-commit-config.yaml) as
a starting point when developers should regenerate and check desired-state
policy before committing. Copy it to `.pre-commit-config.yaml`, update the
policy paths, and install the hook in an environment where `lfguard` is
available:

```bash
python -m pip install lfguard pre-commit
pre-commit install
pre-commit run --all-files
```
