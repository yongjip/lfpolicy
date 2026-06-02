# Import and Adoption Recipes

Use `lfguard import` to scaffold desired state from AWS, then review and edit
the result. Do not treat import as synchronization. The generated file becomes
policy only after a human or platform workflow decides what `lfguard` should
own.

## Recipe 1: Evaluation Snapshot

Use this when a team wants to evaluate `lfguard` without changing AWS:

```bash
python -m pip install "lfguard[aws]"

lfguard import \
  --catalog-id 111122223333 \
  --include lf-tags,lf-tag-expressions,data-cells-filters,resource-tags,grants \
  --output policy/imported-desired.json

lfguard check --desired policy/imported-desired.json --fail-on-findings
lfguard summary --desired policy/imported-desired.json --output markdown
```

Expected review questions:

- Which principals should this repository manage?
- Which legacy grants should stay unmanaged?
- Which LF-Tag keys and values need cleanup before strict gates are enabled?
- Which broad grants need scoped exceptions with owners and expiry?

## Recipe 2: Gradual Ownership

Start with ownership boundaries before failing on every unmanaged current grant:

```json
{
  "ownership": {
    "managed_principals": [
      "arn:aws:iam::111122223333:role/data-*",
      "arn:aws:iam::111122223333:role/analytics-*"
    ],
    "unmanaged_action": "warn"
  },
  "ignore": {
    "principals": ["IAM_ALLOWED_PRINCIPALS"],
    "resources": [{"database": "legacy_*"}]
  }
}
```

Then run audit from a scoped snapshot:

```bash
lfguard snapshot \
  --desired policy/desired.json \
  --profile sandbox \
  --region us-east-1 \
  --catalog-id 111122223333 \
  --output-file snapshots/sandbox-current.json

lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --fail-on-findings \
  --fail-on-severity error
```

This lets warnings stay visible while blocking real policy defects.

## Recipe 3: Convert Import to Python Policy

Imported JSON is useful evidence, but Python policy is easier to maintain when
requests repeat.

1. Keep `policy/imported-desired.json` as a temporary reference.
2. Create `policy.py` with tag keys, resource tags, groups, and role bindings.
3. Generate `policy/desired.json` from `policy.py`.
4. Compare generated desired state with the imported reference.
5. Delete the temporary import only after the generated policy covers the owned
   surface.

Use [`../examples/policy-from-import.py`](../examples/policy-from-import.py) as
a small conversion pattern. It keeps an imported desired-state reference in the
source file while the actual generated policy is modeled with `LakePolicy`
declarations.

Commands:

```bash
lfguard generate policy.py --output-file policy/desired.json --force
lfguard check --desired policy/desired.json --fail-on-findings
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/sandbox-current.json \
  --output markdown \
  --output-file artifacts/lfguard-plan.md
```

## Recipe 4: Data Cells Filter Adoption

Importing data cells filters is bounded to tables discovered from grants. That
keeps adoption scoped, but it also means import is not a full catalog crawler.

```bash
lfguard import \
  --catalog-id 111122223333 \
  --include data-cells-filters,grants \
  --output policy/imported-filters.json
```

After review, keep only filters that should be managed. Use `explain` to attach
evidence for the filtered access:

```bash
lfguard explain \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --principal arn:aws:iam::111122223333:role/FinanceAnalyst \
  --database finance_curated \
  --table invoices \
  --data-cells-filter invoices_public \
  --permissions SELECT \
  --output json \
  --output-file artifacts/explain-invoices-public.json
```

## Recipe 5: Promotion Between Environments

Use the same policy logic and different environment constants:

```bash
lfguard generate policy.py --output-file policy/desired-sandbox.json --force
lfguard check --desired policy/desired-sandbox.json --fail-on-findings

lfguard snapshot \
  --desired policy/desired-sandbox.json \
  --profile sandbox \
  --region us-east-1 \
  --catalog-id 111122223333 \
  --output-file snapshots/sandbox-current.json
```

For production, regenerate with production constants and capture a production
snapshot. Do not reuse a sandbox current-state cache or snapshot as production
evidence.

See [`adoption-checklist.md`](adoption-checklist.md) for the end-to-end rollout
sequence.
