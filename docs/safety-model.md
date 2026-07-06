# Safety Model

`lfguard` is intentionally conservative. It is built for teams that want Lake
Formation policy changes to be visible, reviewable, and easy to stop before
they affect production access.

## Default Behavior

By default, `lfguard plan` and `lfguard review` propose additive changes only:

- create missing LF-Tag definitions;
- add missing LF-Tag values;
- create missing named LF-Tag expressions;
- add missing LF-Tag assignments to resources;
- add missing Lake Formation permissions.

The default plan omits revokes and removals. This keeps routine automation from
silently reducing access or deleting tag values that another process may still
depend on.

## Explicit Destructive Flags

Destructive changes are included only when the matching flag is supplied:

- `--allow-lf-tag-deletes`: plan LF-Tag deletes.
- `--allow-lf-tag-value-removals`: plan LF-Tag value removals.
- `--allow-lf-tag-expression-updates`: plan named LF-Tag expression
  body or description updates.
- `--allow-lf-tag-expression-deletes`: plan named LF-Tag expression
  deletes.
- `--allow-resource-tag-removals`: plan LF-Tag assignment removals.
- `--allow-permission-revokes`: plan Lake Formation permission revokes.

Use these flags in a separate review workflow from routine additive changes. For
production environments, require human review of the generated plan before a
consuming service executes destructive changes.

## Audit Severity

`lfguard audit` reports drift without producing a change plan:

- `error` findings mean desired state is missing from current state.
- `warning` findings mean current state contains unmanaged extras.

`--fail-on-findings` fails on both errors and warnings by default. Use
`--fail-on-severity error` when unmanaged extras should remain visible in the
report but should not block a merge.

## Execution Boundary

`lfguard` has no AWS mutation command in 0.9.0 and later. It emits advisory
evidence: lint findings, audit findings, plan changes, review summaries,
recommended actions, and `hard_block` markers. The consuming service or operator
workflow owns approval, AWS write credentials, grant/revoke execution, and audit
storage.

Plan evidence does not bypass AWS authorization. If an external workflow chooses
to execute a reviewed change, its IAM principal must already have the required
Lake Formation write permissions. See [`aws-permissions.md`](aws-permissions.md)
for lfguard's read-only IAM policy shape and [`aws-api-coverage.md`](aws-api-coverage.md)
for the exact read-only AWS calls lfguard makes.

## Snapshot Scope

`lfguard snapshot` uses the desired-state file as its scope. It reads the
LF-Tags, resources, and grants needed for comparison instead of trying to
inventory an entire AWS account.

This keeps drift checks focused and repeatable, but it also means `lfguard`
should not be treated as a full account discovery tool. Keep separate discovery
or inventory processes if your governance program needs account-wide coverage.

## Recommended Production Pattern

Use separate roles and workflows:

- Read-only CI role: validate desired state, capture live snapshots, audit
  drift, and publish reports.
- Service execution role: owned outside lfguard, executes approved grants or
  revokes according to the consuming service's workflow.
- Destructive maintenance workflow: owned outside lfguard, executes revokes and
  removals only during scheduled governance maintenance with explicit approval.

For authoring, keep column-filtered reader intent separate from edit and create
intent. Reader permission groups may use column-narrowing filters such as
`contains_pii=false` when they grant only `SELECT` and `DESCRIBE`. Editor,
producer, and table-creator groups must use tag filters that cannot be assigned
to columns, so their effective access remains whole-table. `producer()` and
`table_creator()` add database-level `CREATE_TABLE`; `database_creator()` and
`admin()` are separate because catalog-level create authority is broader than
table creation inside an approved database. AWS database creators also receive
follow-on metadata authority on databases they create, so these templates belong
in narrow onboarding or catalog administration roles.

Store desired state in source control. Store generated snapshots and reports
according to your organization's data classification rules because they may
contain principal ARNs, database names, table names, and tag values.

## Non-Goals

`lfguard` does not:

- grant itself Lake Formation administrator privileges;
- discover and govern every catalog resource unless those resources are in the
  desired-state scope;
- infer business intent for unmanaged permissions or tags;
- make destructive operations implicit.

When in doubt, run `audit` and `plan` first, save JSON or Markdown reports, and
review the result before executing.
