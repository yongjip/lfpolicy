# Permission Request Bundles

`lfguard` should not become an approval UI, but a policy repository can still
model repeatable permission requests as small Python data structures that
compile to reviewed Lake Formation grants.

Use this pattern when requests arrive from Jira, Slack, ServiceNow, or an
internal portal and the final source of truth is still a pull request.

## Pattern

1. Define reusable groups such as `finance_reader`, `finance_producer`, or
   `sales_steward`.
2. Represent each approved request as data: ticket, principal, groups, owner,
   reviewer, requested table, requested permissions, evidence path, and expiry
   or review date.
3. Bind each request to groups in `policy.py`.
4. Generate desired state and run normal `check`, `audit`, `explain`, and
   `plan` workflows.

The request metadata can live next to the policy even when only the principal
and groups compile to desired state.

## Example

See [`../examples/permission-requests.py`](../examples/permission-requests.py)
for a runnable example. It keeps approved request records in Python and binds
roles to generic bundles:

```bash
lfguard generate examples/permission-requests.py --output-file /tmp/lfguard-requests.json --force
lfguard check --desired /tmp/lfguard-requests.json --fail-on-findings
```

The source record intentionally keeps review metadata near the grant binding:

```python
AccessRequest(
    ticket="DATA-1042",
    summary="Finance analyst read access to curated invoice data",
    requested_by="finance-analytics",
    principal="arn:aws:iam::111122223333:role/FinanceAnalyst",
    groups=("finance_reader",),
    database="finance_curated",
    table="invoices",
    permissions=("SELECT",),
    owner="finance-analytics",
    approved_by="data-governance",
    review_by="2026-12-31",
    evidence_prefix="artifacts/requests/DATA-1042",
)
```

`groups` is the compiled access outcome. The other fields are review evidence
for humans and automation that creates pull requests, Jira comments, Slack
summaries, or internal approval records.

## Request Review Evidence

For a request that grants access to a sensitive table, attach:

```bash
mkdir -p artifacts/requests

lfguard explain \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --principal arn:aws:iam::111122223333:role/FinanceAnalyst \
  --database finance_curated \
  --table invoices \
  --permissions SELECT \
  --output json \
  --output-file artifacts/requests/DATA-1042-explain.json

lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output json \
  --output-file artifacts/requests/DATA-1042-plan.json
```

Reviewers should approve exact plan-local change IDs from the saved plan:

```json
{
  "id": "change_003",
  "action": "grant.add_permissions",
  "principal": "arn:aws:iam::111122223333:role/FinanceAnalyst",
  "resource": {
    "kind": "lf_tag_policy",
    "resource_type": "TABLE",
    "expression": {
      "domain": ["finance"],
      "sensitivity": ["internal"]
    }
  },
  "risk": "safe",
  "destructive": false
}
```

If the plan contains unrelated changes, do not hand the full plan to an
executor. Pass only the reviewed IDs from the saved plan to the consuming
service:

```json
{
  "reviewed_plan": "artifacts/requests/DATA-1042-plan.json",
  "approved_change_ids": ["change_003"]
}
```

For a batch of approved request changes, keep the reviewed IDs explicit:

```json
{
  "reviewed_plan": "artifacts/requests/request-batch-plan.json",
  "approved_change_ids": ["change_003", "change_007", "change_011"]
}
```

## Boundaries

- Keep approval state in the system that owns approvals.
- Keep `lfguard` desired state as the reviewed permission outcome.
- Do not add organization-specific request statuses or workflow engines to core.
- Use examples or integration packages for Jira, Slack, or portal-specific
  request ingestion.
- Treat plan IDs as stable only inside the saved plan artifact. Regenerate
  review evidence when desired or current state changes.

This keeps the package focused on policy correctness while leaving workflow
ownership to the customer.
