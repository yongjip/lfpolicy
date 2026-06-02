# Exception Lifecycle

Use exceptions for intentional risky access that should stay visible, owned, and
time-bound. Do not use exceptions as a general lint bypass.

## When to Use an Exception

Use an exception when all of these are true:

- the grant is intentionally risky or broad;
- the grant is needed for a specific principal and resource;
- an owner or approver accepts the risk;
- there is an expiry date or a scheduled review date;
- the exception should appear in policy review evidence.

Use lint severity configuration instead when a legacy environment needs a
temporary global migration setting.

## Required Metadata

Each exception should answer four review questions:

| Field | Review question |
| --- | --- |
| `principal` | Who receives the exception? |
| `resource` | Where does the exception apply? |
| `rules` | Which guardrail is being bypassed? |
| `reason` | Why is this acceptable? |
| `expires_at` | When must it be reviewed or removed? |
| `approved_by` | Who accepted the risk? |

Example:

```json
{
  "exceptions": [
    {
      "principal": "arn:aws:iam::111122223333:role/BreakGlassAdmin",
      "resource": {"kind": "database", "database": "analytics"},
      "permissions": ["ALL"],
      "rules": ["allow_broad_permissions", "allow_named_resource_grants"],
      "reason": "temporary incident response access for analytics recovery",
      "expires_at": "2026-12-31",
      "approved_by": "data-governance"
    }
  ]
}
```

## Lifecycle

1. Request: capture the requester, business reason, target resource, requested
   permissions, and expiry.
2. Review: run `lfguard lint` and confirm only the intended finding is
   suppressed.
3. Evidence: attach `lint`, `explain`, `audit`, and `plan` reports to the
   approval record.
4. Apply: use additive apply for grants and keep destructive cleanup separate.
5. Monitor: run scheduled CI so expired exceptions start failing lint.
6. Remove: delete the exception and revoke or replace the grant through a
   reviewed destructive plan.

## CI Check

Run exceptions through the same gate as the rest of desired state:

```bash
lfguard lint \
  --desired policy/desired.json \
  --output json \
  --output-file artifacts/lfguard-lint.json \
  --fail-on-findings
```

Expired exceptions do not suppress findings. This makes expiry enforceable in
CI without a separate scheduler.

## Review Checklist

- The exception is scoped to the narrowest principal pattern.
- The resource is specific enough to avoid unrelated access.
- `permissions` matches the risky grant under review.
- `rules` does not include unrelated bypasses.
- `reason` is requester-facing and specific.
- `approved_by` names a team or person with authority.
- `expires_at` is not open-ended for operational convenience.

See [`state-format.md`](state-format.md#exceptions) for the exact state shape.
