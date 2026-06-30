# Report Formats

`lfguard` reports are designed for both humans and CI systems. Commands that
support reports accept `--output text`, `--output json`, `--output markdown`,
or `--output sarif` where appropriate, and `--output-file PATH` writes the same
report without printing to stdout.

## Review Bundles

Use review bundles when a service, LLM agent, pull request, Jira ticket, or audit
log needs one durable evidence directory.

```bash
lfguard review \
  --desired desired.json \
  --current-snapshot current.json \
  --output-dir review/
```

The command writes:

```text
review/
  manifest.json
  summary.md
  summary.json
  lint.json
  audit.json
  plan.json
  explain.json
```

`manifest.json` is the bundle index:

```json
{
  "schema_version": "lfguard.review.manifest.v1",
  "lfguard_version": "0.7.0",
  "status": "review_required",
  "inputs": {
    "desired": {
      "source": "desired_state",
      "path": "desired.json",
      "sha256": "..."
    },
    "current": {
      "source": "current_snapshot",
      "path": "current.json",
      "sha256": "..."
    }
  },
  "outputs": ["summary.md", "summary.json", "lint.json", "audit.json", "plan.json", "explain.json"]
}
```

`summary.json` uses `schema_version: "lfguard.review.summary.v1"` and reports
`passed`, `review_required`, or `blocked`. A bundle is blocked when lint errors
or destructive planned changes are present. Audit findings and safe planned
changes require review without blocking by default.

`explain.json` in a review bundle uses
`schema_version: "lfguard.review.explain.v1"` and contains planned grant-change
evidence, not full effective-access decisions:

```json
{
  "schema_version": "lfguard.review.explain.v1",
  "description": "Planned grant-change evidence for review bundles. Use lfguard explain-batch for effective-access decisions.",
  "summary": {
    "planned_grant_changes": 1
  },
  "grant_changes": [
    {
      "change_id": "change_002",
      "action": "grant.add_permissions",
      "risk": "safe",
      "principal": "arn:aws:iam::111122223333:role/Analyst",
      "resource": {
        "kind": "lf_tag_policy",
        "resource_type": "TABLE",
        "expression": {"domain": ["sales"]}
      },
      "requested_permissions": ["SELECT"],
      "grantable_permissions": [],
      "before": null,
      "after": {
        "principal": "arn:aws:iam::111122223333:role/Analyst",
        "permissions": ["SELECT"]
      },
      "reason": "Principal is missing desired Lake Formation permissions"
    }
  ]
}
```

Use `lfguard explain-batch` when the question is whether specific principals can
currently access specific resources.

## Audit Reports

Use audit reports when you want to detect drift without proposing or applying
changes.

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output json
```

JSON audit reports contain a severity summary and an ordered list of findings:

```json
{
  "schema_version": "lfguard.audit.v1",
  "summary": {
    "total": 3,
    "errors": 3,
    "warnings": 0
  },
  "findings": [
    {
      "id": "finding_001",
      "code": "LF_TAG_VALUES_MISSING",
      "severity": "error",
      "target": "lf_tag:sensitivity",
      "principal": null,
      "resource": null,
      "message": "Desired LF-Tag values are missing",
      "details": {
        "tag_key": "sensitivity",
        "catalog_id": null,
        "missing_values": ["internal", "restricted"]
      }
    }
  ]
}
```

LF-Tag audit findings include `catalog_id` in their details. Completely
unmanaged current LF-Tag definitions are reported as `LF_TAG_UNMANAGED` and
respect the configured ownership and ignore rules.

Current LF-Tag assignments on resources that are absent from desired state are
reported as `RESOURCE_TAG_UNMANAGED`. These findings include the resource
identity and current tag values, and also respect ownership and ignore rules.

Finding severities have these meanings:

- `error`: desired state is missing from current state and should usually block
  CI when `--fail-on-findings` is used.
- `warning`: current state contains unmanaged extras. Use
  `--fail-on-severity error` when warnings should remain visible but should not
  fail CI.

Markdown audit reports use the same finding order and include summary counts,
which makes them suitable for GitHub Actions job summaries:

```markdown
### lfguard audit

- Total findings: 3
- Error findings: 3
- Warning findings: 0

| Severity | Code | Target | Message |
| --- | --- | --- | --- |
| error | LF_TAG_VALUES_MISSING | lf_tag:sensitivity | Desired LF-Tag values are missing |
```

SARIF audit reports use SARIF 2.1.0 for systems that already ingest static
analysis or security scan results:

```bash
lfguard audit \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output sarif \
  --output-file artifacts/lfguard-audit.sarif
```

Each SARIF result includes the finding code as `ruleId`, the finding severity
as the SARIF level, the target resource as a logical location, and the finding
details under `properties.details`.

## Lint Reports

Use lint reports when you want to catch desired-policy authoring mistakes before
capturing AWS state or planning changes.

```bash
lfguard lint \
  --desired examples/desired.json \
  --output json
```

JSON lint reports contain the same severity summary shape as audit reports:

```json
{
  "schema_version": "lfguard.lint.v1",
  "summary": {
    "total": 1,
    "errors": 1,
    "warnings": 0
  },
  "findings": [
    {
      "code": "RESOURCE_TAG_VALUE_UNDEFINED",
      "severity": "error",
      "target": "table:database=analytics:table=orders",
      "message": "Resource tag assignment uses LF-Tag values that are not defined",
      "details": {
        "tag_key": "sensitivity",
        "undefined_values": ["restricted"]
      }
    }
  ]
}
```

Markdown lint reports use a table format suitable for pull request comments and
job summaries. `lint --fail-on-findings` writes any configured `--output-file`
before returning exit code `1`.

SARIF lint reports use the same SARIF 2.1.0 shape as audit reports, with
desired-policy lint codes as `ruleId` values:

```bash
lfguard lint \
  --desired examples/desired.json \
  --output sarif \
  --output-file artifacts/lfguard-lint.sarif
```

## Check Reports

Use check reports when CI should validate local files and lint desired policy in
one offline command:

```bash
lfguard check \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output json
```

JSON check reports combine validation counts and lint findings:

```json
{
  "valid": true,
  "desired": {
    "valid": true,
    "lf_tags": 2,
    "lf_tag_expressions": 0,
    "resource_tags": 1,
    "grants": 1
  },
  "current_snapshot": {
    "valid": true,
    "lf_tags": 2,
    "lf_tag_expressions": 0,
    "resource_tags": 1,
    "grants": 0
  },
  "lint": {
    "summary": {
      "total": 0,
      "errors": 0,
      "warnings": 0
    },
    "findings": []
  }
}
```

Markdown check reports include validation counts plus the same lint finding
table used by `lfguard lint`.

## Summary Reports

Use summary reports when reviewers need a compact inventory before reading the
full desired/current state files:

```bash
lfguard summary \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output json
```

JSON summary reports include one object for desired state and, when provided,
one object for current snapshot:

```json
{
  "desired": {
    "lf_tags": 2,
    "lf_tag_keys": ["domain", "sensitivity"],
    "resource_tags": 1,
    "lf_tag_expressions": 1,
    "lf_tag_expression_names": ["sales_tables"],
    "resource_kinds": {"table": 1},
    "resource_tag_keys": ["domain", "sensitivity"],
    "grants": 1,
    "grant_principals": ["arn:aws:iam::111122223333:role/Analyst"],
    "grant_resource_kinds": {"lf_tag_policy": 1},
    "permissions": ["DESCRIBE", "SELECT"],
    "grantable_permissions": []
  }
}
```

Markdown summary reports use a compact table for pull request comments and
GitHub Actions artifacts.

## Explain Reports

Use explain reports when reviewers need to understand why access exists or why
a desired grant is still missing:

```bash
lfguard explain \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --principal arn:aws:iam::111122223333:role/Analyst \
  --database analytics \
  --table orders \
  --permissions SELECT \
  --output json
```

JSON explain reports contain the target, effective LF-Tags, a summary by
explanation status, and ordered findings:

```json
{
  "schema_version": "lfguard.explain.v1",
  "principal": "arn:aws:iam::111122223333:role/Analyst",
  "resource": {
    "kind": "table",
    "database": "analytics",
    "table": "orders"
  },
  "requested_permissions": ["SELECT"],
  "effective_lf_tags": {
    "domain": ["sales"],
    "sensitivity": ["internal"]
  },
  "effective_lf_tags_by_catalog": [
    {
      "catalog_id": null,
      "lf_tags": {
        "domain": ["sales"],
        "sensitivity": ["internal"]
      }
    }
  ],
  "summary": {
    "matched": 1,
    "not_matched": 0,
    "missing": 0,
    "context": 0
  },
  "findings": [
    {
      "id": "finding_001",
      "source": "named_lf_tag_policy",
      "status": "matched",
      "message": "Named LF-Tag expression 'sales_tables' matches the target's effective LF-Tags.",
      "permissions": ["SELECT"],
      "grantable_permissions": [],
      "resource": {
        "kind": "lf_tag_policy",
        "resource_type": "TABLE",
        "expression_name": "sales_tables"
      },
      "details": {
        "expression_name": "sales_tables",
        "matched": true
      }
    }
  ],
  "notes": []
}
```

Finding statuses have these meanings:

- `matched`: a current grant applies to the target and covers requested
  permissions when `--permissions` is set.
- `not_matched`: a current grant was relevant to the principal but its LF-Tag
  expression, columns, or permissions did not cover the request.
- `missing`: a desired grant matches the target but is absent from current
  state.
- `context`: related current state exists, such as a data-location grant, but
  `lfguard` cannot prove it grants the requested catalog access by itself.

When the target omits `catalog_id`, explain reports also expose
`effective_lf_tags_by_catalog` so reviewers can see whether the answer was
derived from one catalog or from multiple same-name resources. Scoped LF-Tag
policy grants use the grant catalog's effective tags for matching.

Markdown explain reports include the same summary, effective LF-Tag tables, and
finding table for pull request comments or GitHub Actions summaries.

## Plan Reports

Use plan reports when you want a reviewable change list before touching AWS.

```bash
lfguard plan \
  --desired examples/desired.json \
  --current-snapshot examples/current-snapshot.json \
  --output json
```

JSON plan reports contain a safety summary and an ordered list of proposed
changes:

```json
{
  "schema_version": "lfguard.plan.v1",
  "summary": {
    "total": 3,
    "safe": 3,
    "destructive": 0
  },
  "changes": [
    {
      "id": "change_001",
      "action": "lf_tag.add_values",
      "target": "lf_tag:sensitivity",
      "reason": "LF-Tag is missing allowed values",
      "destructive": false,
      "risk": "safe",
      "principal": null,
      "resource": null,
      "before": {
        "tag_key": "sensitivity",
        "tag_values": ["public"]
      },
      "after": {
        "tag_key": "sensitivity",
        "tag_values": ["internal", "public", "restricted"]
      },
      "requires_flag": null,
      "aws_api": "update_lf_tag",
      "payload": {
        "tag_key": "sensitivity",
        "tag_values": ["internal", "restricted"]
      }
    }
  ]
}
```

Plan safety has these meanings:

- `safe`: additive changes, such as creating missing LF-Tags, adding missing tag
  values, adding resource tag assignments, or adding permissions.
- `destructive`: removals or revokes. These are omitted by default and appear
  only when a matching `--allow-*` planning flag is supplied.

Change IDs are stable within a saved plan file and are intended for selective
apply:

```bash
lfguard apply --plan plan.json --only change_001 --execute
lfguard apply --plan plan.json --only-action grant.add_permissions --max-changes 10 --execute
```

Markdown plan reports include the same safety summary and change list for pull
request review.

## Apply Reports

`lfguard apply` defaults to dry-run mode and renders the computed plan. With
`--execute --output json`, the report includes the plan plus per-change execution
results:

```json
{
  "plan": {
    "schema_version": "lfguard.plan.v1",
    "summary": {
      "total": 1,
      "safe": 1,
      "destructive": 0
    },
    "changes": [
      {
        "id": "change_001",
        "action": "lf_tag.create",
        "target": "lf_tag:sensitivity",
        "reason": "LF-Tag is missing",
        "destructive": false,
        "risk": "safe",
        "principal": null,
        "resource": null,
        "before": null,
        "after": {
          "tag_key": "sensitivity",
          "tag_values": ["internal"]
        },
        "requires_flag": null,
        "aws_api": "create_lf_tag",
        "payload": {
          "tag_key": "sensitivity",
          "tag_values": ["internal"]
        }
      }
    ]
  },
  "results": [
    {
      "action": "lf_tag.create",
      "target": "lf_tag:sensitivity",
      "applied": true,
      "response": {}
    }
  ]
}
```

Even with `--execute`, destructive changes are applied only when the matching
allow flag is present.

## GitHub Actions

For pull requests, combine machine-readable artifacts with a readable job
summary:

```bash
lfguard audit \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --output json \
  --output-file artifacts/lfguard-audit.json \
  --fail-on-findings \
  --github-summary
```

The report file is written before CI gate flags return exit code `1`, so failed
jobs still leave evidence for review.
