# CI Evidence Workflows

Use `lfguard` CI output as evidence that a Lake Formation policy change was
reviewed, compared with current state, and ready for a consuming service's
approval and execution path. The goal is not only to fail a job. The goal is to
leave artifacts that another reviewer or approval system can inspect without
opening the AWS console.

## Evidence Bundle

For a normal permission pull request, keep these artifacts:

| Artifact | Command | Why it matters |
| --- | --- | --- |
| Generated desired state | `lfguard generate policy.py --output-file policy/desired.json --check` | Proves reviewed Python policy and committed desired JSON are in sync. |
| Review bundle | `lfguard review --desired policy/desired.json --current-snapshot snapshots/prod-current.json --output-dir artifacts/review` | Stable lint, audit, plan, planned grant evidence, input hashes, and summary status for approval systems. |
| Batch explain JSON | `lfguard explain-batch --requests access-requests.json --current-snapshot snapshots/prod-current.json --output json` | Answers operational access questions without opening the AWS console. |

Store JSON for machines and Markdown for reviewers. SARIF is useful when the
repository already uses GitHub Code Scanning.

For concrete report shapes without running commands first, inspect the checked
in fixtures under [`../examples/artifacts/`](../examples/artifacts/).

## Pull Request Gate

Use the pull request gate for local policy quality. Avoid AWS credentials on
untrusted pull requests.

```bash
mkdir -p artifacts

lfguard generate policy.py --output-file policy/desired.json --check

lfguard summary \
  --desired policy/desired.json \
  --output markdown \
  --output-file artifacts/lfguard-summary.md \
  --github-summary

lfguard check \
  --desired policy/desired.json \
  --fail-on-findings \
  --output markdown \
  --output-file artifacts/lfguard-check.md \
  --github-summary
```

This gate proves the desired policy is internally valid. It does not prove AWS
state matches.

## Protected Drift Gate

Run live drift checks on a schedule, on manual dispatch, or after merge to a
protected branch where GitHub OIDC or another CI identity can assume a read-only
AWS role.

```bash
mkdir -p artifacts snapshots

lfguard snapshot \
  --desired policy/desired.json \
  --profile prod \
  --region us-east-1 \
  --catalog-id 111122223333 \
  --output-file snapshots/prod-current.json

lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output json \
  --output-file artifacts/lfguard-audit.json \
  --fail-on-findings
```

Use `--current-snapshot` for evidence. A snapshot is immutable and reviewable;
`--current-cache` is an optimization for repeated live reads, not an approval
artifact.

## Plan Review Gate

Use plan output when the reviewer needs to approve exact changes:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output json \
  --output-file artifacts/lfguard-plan.json \
  --fail-on-changes
```

For controlled rollout, save the plan and pass reviewed change IDs to the
consuming service that owns AWS write execution:

```json
{
  "reviewed_plan": "artifacts/lfguard-plan.json",
  "approved_change_ids": ["change_001", "change_002"],
  "executor": "consuming-service"
}
```

This keeps external execution tied to the reviewed plan instead of recomputing a
different change set later. `lfguard` itself does not execute the changes.

## Explain Evidence

For sensitive tables, filters, or break-glass roles, attach an explain report to
the change:

```bash
lfguard explain \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --principal arn:aws:iam::111122223333:role/FinanceAnalyst \
  --database finance_curated \
  --table invoices \
  --permissions SELECT \
  --output json \
  --output-file artifacts/explain-finance-analyst-invoices.json
```

Use `--data-cells-filter FILTER` when the reviewed access is row or column
filtered.

## Artifact Handling

- Upload artifacts with `if: always()` so failed gates still leave evidence.
- Keep retention long enough for the approval and incident-review window.
- Do not store broad full-account inventory when a scoped snapshot answers the
  review question.
- Keep destructive plans separate from routine additive plans.

See [`github-actions.md`](github-actions.md) and
[`report-formats.md`](report-formats.md) for copyable GitHub workflows and JSON
report shapes.
