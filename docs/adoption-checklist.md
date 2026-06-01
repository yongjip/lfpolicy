# Adoption Checklist

Use this checklist when introducing `lfguard` to a Lake Formation environment.
Start offline, then add CI, then decide whether controlled apply belongs in your
workflow.

## 1. Run the Offline Demo

Install the base package and generate sample files:

```bash
python -m pip install lfguard
lfguard sample --output-dir lfguard-demo
lfguard check \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
lfguard plan \
  --desired lfguard-demo/desired.json \
  --current-snapshot lfguard-demo/current-snapshot.json
```

This proves the CLI works without AWS credentials.

When adopting an existing account, use `import` to create a reviewed starter
file instead of treating live state as automatically owned:

```bash
lfguard import \
  --catalog-id 123456789012 \
  --include lf-tags,lf-tag-expressions,resource-tags,grants \
  --output policy/imported-desired.json
```

Review the output, add `ownership` and `ignore` rules for unmanaged legacy
surface area, then move the curated result into `policy/desired.json`.

Before mapping real access policy, read
[`lake-formation-guide.md`](lake-formation-guide.md) and confirm the team
understands the Lake Formation/IAM split, LF-Tag inheritance, `IAMAllowedPrincipals`,
hybrid access mode, and the difference between routine additive changes and
destructive maintenance.

For YAML policy repositories, generate a YAML demo after installing the YAML
extra:

```bash
python -m pip install "lfguard[yaml]"
lfguard sample --output-dir lfguard-demo-yaml --format yaml
```

## 2. Draft Policy

Create a starter policy repository and replace the example names in `policy.py`
with sanitized values from your environment:

```bash
lfguard bootstrap --output-dir lfguard-policy
cd lfguard-policy
lfguard generate policy.py --output-file policy/desired.json --force
```

Use JSON first unless your repository already standardizes on YAML. Add the YAML
extra when needed and generate `policy/desired.yaml` instead:

```bash
python -m pip install "lfguard[yaml]"
lfguard generate policy.py --output-file policy/desired.yaml --force
```

## 3. Check Policy Locally

Run the offline check before connecting to AWS:

```bash
lfguard check --desired policy/desired.json --fail-on-findings
```

Commit `policy.py` and generated desired state only after principal names,
database names, table names, and LF-Tag values have passed parser, lint, and
review rules.

Generate a compact summary for reviewers:

```bash
lfguard summary --desired policy/desired.json --output markdown
```

## 4. Capture Current State

Install the AWS extra and capture a scoped snapshot from a non-production
environment first:

```bash
python -m pip install "lfguard[aws]"
lfguard snapshot \
  --desired policy/desired.json \
  --profile sandbox \
  --region us-east-1 \
  --output-file snapshots/sandbox-current.json
```

The snapshot scope comes from generated desired state, so review `policy.py` and
`policy/desired.json` before using them to read live AWS state.

## 5. Add CI Drift Checks

Start with the smallest workflow that gives reviewers useful signal. To generate
a starter repository layout with an offline policy workflow, run:

```bash
lfguard bootstrap --output-dir lfguard-policy
```

Add optional scaffolds only when they have an owner and a clear use:

- `--include-live-drift`: scheduled GitHub OIDC drift checks with a read-only
  AWS role.
- `--include-code-scanning`: SARIF upload when your repository already uses
  GitHub Code Scanning dashboards.
- `--include-review-template --policy-owner @your-org/data-platform`:
  CODEOWNERS and a Lake Formation policy pull request checklist.
- `--include-editor-config`: VS Code schema validation from
  `policy/lfguard.schema.json`.

Use check when a workflow should validate local state files and lint desired
policy before enforcing drift:

```bash
lfguard check \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-findings \
  --output markdown \
  --output-file artifacts/lfguard-check.md
```

Use audit when drift should be visible as findings:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-findings \
  --output markdown \
  --output-file artifacts/lfguard-audit.md
```

Use plan when a non-empty change plan should block a merge:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-changes
```

## 6. Review Apply Behavior

Run live apply without `--execute` first. This is a dry run:

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile sandbox \
  --region us-east-1 \
  --output markdown \
  --output-file artifacts/lfguard-apply-dry-run.md
```

Execute only after reviewing the plan and confirming the IAM/Lake Formation
permissions are intentionally scoped:

```bash
lfguard permissions --template additive-apply --output-file iam/lfguard-additive-apply.json
```

```bash
lfguard apply \
  --desired policy/desired.json \
  --profile sandbox \
  --region us-east-1 \
  --execute
```

## 7. Separate Destructive Changes

Keep revokes and removals on a separate approval path. They are omitted unless
explicitly allowed:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --allow-permission-revokes \
  --allow-resource-tag-removals \
  --allow-lf-tag-value-removals
```

## 8. Move to Production Carefully

Before production use, confirm:

- `policy.py` and generated desired state are reviewed and owned by the right
  platform or data governance team.
- CI stores audit, plan, or apply reports as artifacts.
- The AWS principal used by automation has only the needed read or apply
  permissions.
- Dry-run output is reviewed before any `--execute` run.
- Destructive flags are not enabled in routine additive workflows.

For operational examples, see [`recipes.md`](recipes.md),
[`safety-model.md`](safety-model.md), and
[`github-actions.md`](github-actions.md).
