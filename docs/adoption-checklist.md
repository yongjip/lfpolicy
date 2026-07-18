# Adoption Checklist

Use this checklist when introducing `lfpolicy` to a Lake Formation environment.
Start offline, then add CI, then decide how consuming services will use review
evidence in their own approval and execution workflows.

## 1. Run the Offline Demo

Install the base package and generate sample files:

```bash
python -m pip install lfpolicy
lfpolicy sample --output-dir lfpolicy-demo
lfpolicy check \
  --desired lfpolicy-demo/desired.json \
  --current-snapshot lfpolicy-demo/current-snapshot.json
lfpolicy plan \
  --desired lfpolicy-demo/desired.json \
  --current-snapshot lfpolicy-demo/current-snapshot.json
```

This proves the CLI works without AWS credentials.

When adopting an existing account, use `import` to create a reviewed starter
file instead of treating live state as automatically owned:

```bash
lfpolicy import \
  --catalog-id 123456789012 \
  --include lf-tags,lf-tag-expressions,resource-tags,grants \
  --output policy/imported-desired.json
```

Review the output, add `ownership` and `ignore` rules for unmanaged legacy
surface area, then move the curated result into `policy/desired.json`.
See [`import-adoption-recipes.md`](import-adoption-recipes.md) for concrete
import review, gradual ownership, data cells filter, and environment promotion
recipes.

Before mapping real access policy, read
[`lake-formation-guide.md`](lake-formation-guide.md) and confirm the team
understands the Lake Formation/IAM split, LF-Tag inheritance, `IAMAllowedPrincipals`,
hybrid access mode, and the difference between routine additive changes and
destructive maintenance.

For YAML policy repositories, generate a YAML demo after installing the YAML
extra:

```bash
python -m pip install "lfpolicy[yaml]"
lfpolicy sample --output-dir lfpolicy-demo-yaml --format yaml
```

## 2. Draft Policy

Create a starter policy repository and replace the example names in `policy.py`
with sanitized values from your environment:

```bash
lfpolicy bootstrap --output-dir lfpolicy-policy
cd lfpolicy-policy
lfpolicy generate policy.py --output-file policy/desired.json --force
```

Use JSON first unless your repository already standardizes on YAML. Add the YAML
extra when needed and generate `policy/desired.yaml` instead:

```bash
python -m pip install "lfpolicy[yaml]"
lfpolicy generate policy.py --output-file policy/desired.yaml --force
```

## 3. Check Policy Locally

Run the offline check before connecting to AWS:

```bash
lfpolicy check --desired policy/desired.json --fail-on-findings
```

Commit `policy.py` and generated desired state only after principal names,
database names, table names, and LF-Tag values have passed parser, lint, and
review rules.

Generate a compact summary for reviewers:

```bash
lfpolicy summary --desired policy/desired.json --output markdown
```

## 4. Capture Current State

Install the AWS extra and capture a scoped snapshot from a non-production
environment first:

```bash
python -m pip install "lfpolicy[aws]"
lfpolicy snapshot \
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
lfpolicy bootstrap --output-dir lfpolicy-policy
```

Add optional scaffolds only when they have an owner and a clear use:

- `--include-live-drift`: scheduled GitHub OIDC drift checks with a read-only
  AWS role.
- `--include-code-scanning`: SARIF upload when your repository already uses
  GitHub Code Scanning dashboards.
- `--include-review-template --policy-owner @your-org/data-platform`:
  CODEOWNERS and a Lake Formation policy pull request checklist.
- `--include-editor-config`: VS Code schema validation from
  `policy/lfpolicy.schema.json`.

Use check when a workflow should validate local state files and lint desired
policy before enforcing drift:

```bash
lfpolicy check \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-findings \
  --output markdown \
  --output-file artifacts/lfpolicy-check.md
```

Use audit when drift should be visible as findings:

```bash
lfpolicy audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-findings \
  --output markdown \
  --output-file artifacts/lfpolicy-audit.md
```

Use plan when a non-empty change plan should block a merge:

```bash
lfpolicy plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-changes
```

## 6. Review Execution Boundary

Write a review bundle before any consuming service executes Lake Formation
changes:

```bash
lfpolicy review \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --output-dir artifacts/review \
  --force
```

If a service executes grants or revokes after review, keep its AWS write
credentials, approval checks, audit persistence, and rollback behavior outside
the lfpolicy package contract. Use lfpolicy's read-only IAM template only for live
inventory evidence:

```bash
lfpolicy permissions --template read-only --output-file iam/lfpolicy-read-only.json
```

## 7. Separate Destructive Changes

Keep revokes and removals on a separate approval path. They are omitted unless
explicitly allowed:

```bash
lfpolicy plan \
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
- CI stores audit, plan, review, or explain reports as artifacts.
- The AWS principal used by lfpolicy automation has only the needed read
  permissions.
- External execution uses only reviewed plan evidence and selected change IDs.
- Destructive flags are not enabled in routine additive workflows.

For operational examples, see [`recipes.md`](recipes.md),
[`safety-model.md`](safety-model.md),
[`ci-evidence-workflows.md`](ci-evidence-workflows.md),
[`exception-lifecycle.md`](exception-lifecycle.md), and
[`github-actions.md`](github-actions.md).
