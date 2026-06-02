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
   and expiry or review date.
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

## Request Review Evidence

For a request that grants access to a sensitive table, attach:

```bash
lfguard explain \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --principal arn:aws:iam::111122223333:role/FinanceAnalyst \
  --database finance_curated \
  --table invoices \
  --permissions SELECT \
  --output json \
  --output-file artifacts/requests/REQ-1042-explain.json

lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output json \
  --output-file artifacts/requests/REQ-1042-plan.json
```

If the plan contains unrelated changes, do not apply the full plan. Use
`lfguard apply --plan ... --only change_001` after reviewers approve the exact
change ID.

## Boundaries

- Keep approval state in the system that owns approvals.
- Keep `lfguard` desired state as the reviewed permission outcome.
- Do not add organization-specific request statuses or workflow engines to core.
- Use examples or integration packages for Jira, Slack, or portal-specific
  request ingestion.

This keeps the package focused on policy correctness while leaving workflow
ownership to the customer.
