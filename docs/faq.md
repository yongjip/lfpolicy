# FAQ

## What problem does lfpolicy solve?

`lfpolicy` gives platform and data governance teams a reviewable way to manage
Lake Formation LF-Tag policy as code. It compares desired LF-Tags, resource tag
assignments, and grants against current state, then reports drift or produces a
conservative change plan.

It is most useful when Lake Formation access should move through pull requests,
CI checks, service approvals, and reviewed execution paths instead of one-off
console changes or bespoke boto3 scripts.

## Is it safe to run against production?

The audit, check, validate, lint, plan, sample, bootstrap, schema, permissions,
completion, review, explain, explain-batch, snapshot, import, and doctor
commands do not mutate AWS state. `lfpolicy` has no apply command in 0.9.0 and
later.

By default, plans are additive only. Permission revokes, resource tag removals,
and LF-Tag value removals require explicit allow flags, so destructive changes
can use a separate review path.

## Do I need AWS credentials to try it?

No. Install the base package and run:

```bash
lfpolicy sample --output-dir lfpolicy-demo
lfpolicy plan \
  --desired lfpolicy-demo/desired.json \
  --current-snapshot lfpolicy-demo/current-snapshot.json
```

Live AWS inventory workflows require the optional AWS extra:

```bash
python -m pip install "lfpolicy[aws]"
```

## Does it replace IAM or Lake Formation administration?

No. `lfpolicy` does not bypass AWS authorization, create IAM principals, register
data lake locations, or configure cross-account sharing. It works inside the
permissions granted to the caller and focuses on LF-Tags, tag assignments, and
Lake Formation permissions.

## Does it manage every Lake Formation feature?

No. `lfpolicy` focuses on a deliberately small guardrail surface:

- LF-Tag definitions and allowed values.
- LF-Tag assignments on catalog resources.
- Lake Formation grants on catalog, database, table, table-with-columns, data
  location, and LF-Tag policy resources.

See [`aws-api-coverage.md`](aws-api-coverage.md) for the exact boto3 calls used
for live inventory and import.

## How should teams adopt it?

Start offline with `lfpolicy sample`. For a real policy repository, define
permission groups and tag assignments in `policy.py`, generate desired state
with `lfpolicy generate`, then add a CI job that runs
`lfpolicy check --fail-on-findings`, `lfpolicy audit`, or
`lfpolicy plan --fail-on-changes` against a current-state snapshot.

Use `lfpolicy review` and `plan` as advisory evidence. If a consuming service
executes grants or revokes, it owns approval checks, AWS write credentials, and
audit persistence.
