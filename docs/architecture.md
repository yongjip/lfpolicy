# Architecture

`lfguard` keeps policy comparison separate from live AWS execution. The core
package is small enough to audit and is structured around deterministic models,
pure audit and planning functions, and an optional boto3 adapter.

## Module Boundaries

- `lakeformation_guard.models` defines desired and current state objects,
  resource references, LF-Tag definitions, named LF-Tag expressions, tag
  assignments, grants, and optional guardrail config. These classes normalize
  input and expose JSON-compatible dictionaries.
- `lakeformation_guard.config` contains the matching helpers for lint severity
  overrides, ownership boundaries, ignore rules, and scoped policy exceptions.
- `lakeformation_guard.audit` compares desired and current state and returns
  findings. It does not create a change plan and does not call AWS.
- `lakeformation_guard.lint` checks desired-state semantic consistency, such as
  undefined LF-Tag keys or values, without current state or AWS access.
- `lakeformation_guard.planner` compares desired and current state and returns a
  conservative ordered plan. Destructive changes are included only when the
  matching `PlanOptions` flag is set.
- `lakeformation_guard.explain` explains one principal/resource access question
  from desired and current state. It is read-only and does not call AWS.
- `lakeformation_guard.provider` defines the narrow `CurrentStateProvider`
  protocol used by the CLI and integrations to supply current state.
- `lakeformation_guard.io` reads JSON or optional YAML state files.
- `lakeformation_guard.cli` handles command parsing, report rendering, file
  output, and exit codes.
- `lakeformation_guard.aws` is the optional boto3 integration for live
  inventory and apply operations.
- `lakeformation_guard.schema` provides the JSON Schema used by the `schema`
  command and editor or CI validation.

The `lakeformation_guard.policy` module sits above these boundaries rather than
replacing them. It compiles Python-native tag keys, resource tag assignments,
permission groups, safe permission templates, and IAM role bindings into the
existing `DesiredState` model. The generated desired state still passes the same
schema, lint, audit, plan, and apply workflow as hand-authored JSON or YAML.

## Data Flow

Most workflows follow the same path:

1. Read desired state from JSON or YAML.
2. Load current state from a local snapshot or the AWS adapter.
3. Normalize both inputs into `DesiredState` and `CurrentState`.
4. Optionally run `lint_desired()` for desired-policy authoring issues.
5. Run `audit()` for drift findings, `plan()` for reviewable changes, or
   `explain()` for one effective-access question.
6. Render text, JSON, Markdown, or SARIF output.
7. Optionally pass the plan to the AWS adapter for dry-run or execution.

The audit, planner, and explain layers do not know whether current state came
from a file, AWS, or another provider. This keeps CI snapshot workflows and
live workflows aligned.

## Safety Invariants

The safety model is enforced in several places:

- `lint_desired()` is read-only and only inspects local desired state.
- `audit()` is read-only and reports drift without planning remediation.
- `plan()` is additive by default. It plans missing LF-Tags, missing tag values,
  missing named LF-Tag expressions, missing resource tag assignments, and
  missing permissions.
- Permission revokes, named LF-Tag expression updates/deletes, resource tag
  removals, and LF-Tag value removals require explicit planner options and CLI
  flags.
- `Plan.executable_changes()` excludes destructive changes unless explicitly
  allowed.
- `lfguard apply` is a dry run unless `--execute` is provided.
- Saved-plan apply can be limited by change ID, action type, and safety budgets
  before any AWS call is made.
- Risky desired grants can be allowed only through scoped exceptions with reason,
  expiry, and owner or approval metadata.
- The boto3 adapter applies only actions represented by planner `Change`
  objects.

See [`safety-model.md`](safety-model.md) for production usage patterns and
destructive-change review guidance.

## AWS Boundary

The base package does not import boto3. Live AWS usage starts only when
`AWSLakeFormationAdapter.from_boto3()` is called or a CLI command needs live
state. Users who only run offline lint, audit, plan, sample, schema, or
validation workflows do not need the `aws` extra.

The adapter scopes live inventory from desired state. It reads only the LF-Tags,
named LF-Tag expressions, data cells filters, resources, and grants needed for
the requested comparison, then returns a normal `CurrentState` object to the
same audit and planner code used by offline workflows. The separate import path
can scaffold a starter desired-state file from live LF-Tags, named LF-Tag
expressions, data cells filters discovered through imported grants, grants, and
resource tags discovered through imported grants.

The `CurrentStateProvider` protocol is intentionally small:

```python
class CurrentStateProvider:
    def load_current_state_for(self, desired: DesiredState) -> CurrentState: ...
```

The boto3 adapter implements that protocol. Snapshot-backed providers let tests
and CI provide reviewed current state without importing boto3. The cached
provider wraps any other provider and stores a desired-scope fingerprint plus
current state in a JSON cache envelope, so caches remain an implementation of
the provider boundary rather than planner or audit behavior.

## Public API

The intended import surface is exposed from `lakeformation_guard`:

```python
from lakeformation_guard import CurrentState, DesiredState, PlanOptions, audit, explain, lint_desired, plan
```

Use `lakeformation_guard.aws.AWSLakeFormationAdapter` only for live inventory or
apply workflows. Internal helper functions and CLI rendering helpers are not
part of the stable public API.

Use `CurrentStateProvider` when a downstream system already has current state in
files, APIs, caches, or databases and wants to reuse `audit()`, `plan()`, or
`explain()` without the default AWS adapter. Use
`CachedCurrentStateProvider` when the upstream source is expensive but still
should be refreshed through the same provider interface. Cached entries are
keyed by desired-state fingerprint and a provider-context fingerprint so live
AWS cache reuse can distinguish profile, region, catalog, and provider
identity.

The public API includes a narrow authoring layer under
`lakeformation_guard.policy` for teams that want rigid permission groups and
generic bundles such as `reader()`, `producer()`, `steward()`,
`data_location_access()`, and `admin()` instead of raw grants. See
[`policy-authoring-direction.md`](policy-authoring-direction.md) for the
direction and constraints.

## Extension Points

The most common changes should stay within the existing boundaries:

- Add new state shapes in `models.py` and update `schema.py`.
- Add drift reporting in `audit.py`.
- Add desired-policy semantic checks in `lint.py`.
- Add planned changes in `planner.py`.
- Add access explanation behavior in `explain.py`.
- Add current-state source integrations behind `provider.py`.
- Add boto3 translation or execution in `aws.py`.
- Add CLI flags and report rendering in `cli.py`.
- Add docs and tests for any public behavior or output shape change.

Keep new AWS calls out of audit and planning code so offline CI workflows remain
deterministic and dependency-light.
