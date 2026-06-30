# Permission Framework Concepts

`lfguard` is a strict framework for defining, validating, explaining, planning,
and safely applying AWS Lake Formation data permissions. It is not a
consumer-specific integration layer; approval systems, CI jobs, internal consoles, Jira,
Slack, and cache-backed inventory systems should integrate through state files,
providers, and stable JSON reports.

## Permission Lifecycle

Use the same lifecycle for every Lake Formation permission change:

1. Define desired state in JSON, YAML, or generated Python policy output.
2. Validate and lint policy quality before AWS access.
3. Explain effective access for sensitive principals and resources.
4. Audit current state against desired state.
5. Plan reviewable changes with deterministic change IDs.
6. Export audit, explain, or plan JSON as approval evidence.
7. Apply only reviewed changes, with destructive flags and safety budgets.

## Rigid Invariants

Some issues are treated as hard policy defects rather than workflow preferences:

- Duplicate LF-Tag, LF-Tag key metadata, and LF-Tag expression identities are
  rejected by catalog-scoped identity.
- Undefined LF-Tag keys, values, and named expressions are lint errors.
- Dangerous grants such as broad principals, `ALL`/`SUPER`, mutating
  permissions, grant option, and named database/table grants require explicit
  exceptions or lint configuration.
- Destructive apply operations require exact CLI flags and can be capped with
  `--max-destructive`.
- Expired exceptions do not suppress lint findings.

## Exceptions

Use top-level `exceptions` when a risky grant is intentional and should remain
reviewable:

```json
{
  "exceptions": [
    {
      "principal": "arn:aws:iam::111122223333:role/DataAdmin",
      "resource": {"kind": "database", "database": "analytics"},
      "permissions": ["ALL"],
      "rules": ["allow_broad_permissions", "allow_named_resource_grants"],
      "reason": "break-glass database administration",
      "ticket": "SEC-123",
      "owner": "data-platform",
      "expires_at": "2099-12-31",
      "approved_by": "data-governance"
    }
  ]
}
```

Prefer exceptions over global lint ignores when the access is narrow, temporary,
and owned. Prefer `lint` severity overrides only for staged adoption across a
legacy environment.

## Policy Bundles

The Python policy builder exposes generic bundles that compile to ordinary
desired-state grants:

| Bundle | Expansion |
| --- | --- |
| `reader()` | LF-Tag policy database `DESCRIBE` plus table `DESCRIBE`/`SELECT`. |
| `editor()` | Reader-style access plus table `INSERT`/`DELETE` for whole-table filters. |
| `producer()` | `CREATE_TABLE` on matching databases plus editor-style table access. |
| `steward("expression")` | `DESCRIBE` and `GRANT_WITH_LF_TAG_EXPRESSION` on one named LF-Tag expression. |
| `data_location_access("arn")` | `DATA_LOCATION_ACCESS` on one registered data location. |
| `admin()` | Catalog-level `CREATE_DATABASE`, `CREATE_LF_TAG`, `CREATE_LF_TAG_EXPRESSION`, and `DESCRIBE`. |

Bundles are conveniences over the same state model; review still happens against
generated grants, plans, audits, and explanations. No bundle grants `ALL`,
`SUPER`, grant option, or broad-principal access.

## Provider Boundary

The core framework consumes `DesiredState` and `CurrentState`. Current state can
come from:

- the AWS adapter;
- a JSON/YAML snapshot file;
- a custom `CurrentStateProvider`;
- an internal API, database, or cache that emits the same model.

This boundary keeps integrations outside the core while preserving the same
lint, audit, explain, plan, and apply semantics.

## Stable Evidence

JSON reports are intended as API-friendly evidence:

- `plan` uses `schema_version: "lfguard.plan.v1"` and deterministic
  `change_001` IDs.
- `audit` uses `schema_version: "lfguard.audit.v1"` and deterministic
  `finding_001` IDs.
- `explain` uses `schema_version: "lfguard.explain.v1"` and deterministic
  `finding_001` IDs.

Store these reports as CI artifacts or feed them into approval systems. Treat
schema-version changes as integration events.

## Operating Guides

- [`ci-evidence-workflows.md`](ci-evidence-workflows.md): CI artifact sets,
  drift gates, plan review, access explanation, and apply dry-run evidence.
- [`terraform-cdk-coexistence.md`](terraform-cdk-coexistence.md): ownership
  boundaries between infrastructure tools and `lfguard`.
- [`import-adoption-recipes.md`](import-adoption-recipes.md): practical import,
  ownership, data cells filter, and promotion recipes.
- [`exception-lifecycle.md`](exception-lifecycle.md): request, approval, expiry,
  and removal lifecycle for scoped exceptions.
- [`permission-request-bundles.md`](permission-request-bundles.md): request data
  patterns that compile to normal desired state without adding workflow UI to
  core.
