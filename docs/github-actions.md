# GitHub Actions

This workflow checks that `policy.py` still matches the checked-in generated
desired policy, then runs `lfguard` against that desired policy and a generated
current-state snapshot. It is intended for platform repositories that already
use GitHub OIDC to assume an AWS role.

The same workflow is available as a copyable file at
[`examples/github-actions/lakeformation-drift.yml`](../examples/github-actions/lakeformation-drift.yml).
An optional Code Scanning variant is available at
[`examples/github-actions/lakeformation-code-scanning.yml`](../examples/github-actions/lakeformation-code-scanning.yml).
You can also generate repository-specific starter workflows with:

```bash
lfguard bootstrap \
  --output-dir lfguard-policy \
  --include-live-drift \
  --include-code-scanning \
  --include-review-template \
  --include-editor-config \
  --policy-owner @your-org/data-platform \
  --aws-role-arn arn:aws:iam::111122223333:role/LakeFormationReadOnly \
  --aws-region ap-northeast-2
```

```yaml
name: Lake Formation drift

on:
  workflow_dispatch:
  schedule:
    - cron: "17 * * * *"

permissions:
  contents: read
  id-token: write

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::111122223333:role/LakeFormationReadOnly
          aws-region: ap-northeast-2

      - name: Install lfguard
        run: python -m pip install "lfguard[aws]"

      - name: Check lfguard install
        run: lfguard doctor --require aws

      - name: Check generated desired state
        run: lfguard generate policy.py --output-file policy/desired.json --check

      - name: Export policy schema
        run: lfguard schema --output-file policy/lfguard.schema.json

      - name: Summarize policy
        run: |
          lfguard summary \
            --desired policy/desired.json \
            --output markdown \
            --output-file artifacts/lfguard-summary.md \
            --github-summary

      - name: Capture current state
        run: |
          lfguard snapshot \
            --desired policy/desired.json \
            --region ap-northeast-2 \
            --output-file snapshots/prod-current.json

      - name: Check policy files
        run: |
          lfguard lint \
            --desired policy/desired.json \
            --output sarif \
            --output-file artifacts/lfguard-lint.sarif

          lfguard check \
            --desired policy/desired.json \
            --current-snapshot snapshots/prod-current.json \
            --output markdown \
            --output-file artifacts/lfguard-check.md \
            --fail-on-findings \
            --github-summary

      - name: Audit drift
        run: |
          lfguard audit \
            --desired policy/desired.json \
            --current-snapshot snapshots/prod-current.json \
            --output sarif \
            --output-file artifacts/lfguard-audit.sarif

          lfguard audit \
            --desired policy/desired.json \
            --current-snapshot snapshots/prod-current.json \
            --output markdown \
            --output-file artifacts/lfguard-audit.md \
            --fail-on-findings \
            --github-summary

      - name: Upload lfguard reports
        if: always()
        uses: actions/upload-artifact@v6
        with:
          name: lfguard-reports
          path: artifacts/
          if-no-files-found: ignore
          retention-days: 14
```

For pull requests from forks, avoid granting AWS credentials directly to the PR
workflow. A safer pattern is to run drift checks on a schedule, on manual
dispatch, or after changes are merged to a protected branch.

`lfguard check`, `lfguard lint`, and `lfguard audit` write report files before
returning a non-zero status for `--fail-on-findings`, so the artifact upload
step still has evidence to attach when policy lint or drift checks break the
job. The SARIF artifacts can also be uploaded to systems that ingest
static-analysis or governance findings.

## GitHub Code Scanning

When a repository can upload SARIF to GitHub Code Scanning, use the copyable
[`lakeformation-code-scanning.yml`](../examples/github-actions/lakeformation-code-scanning.yml)
workflow. It:

- grants `security-events: write` for SARIF upload;
- writes separate `lfguard-lint` and `lfguard-audit` SARIF categories;
- uploads both SARIF files before enforcing the final check and drift gates.

This keeps findings visible in the Security tab even when the final gate fails.

For a fuller evidence model, including plan JSON, explain JSON, review bundles,
and artifact retention guidance, see
[`ci-evidence-workflows.md`](ci-evidence-workflows.md).
