# Architecture

`lfpolicy` keeps policy comparison separate from consuming-service execution. The core
package is small enough to audit and is structured around deterministic models,
pure audit and planning functions, and an optional boto3 adapter.

## Module Boundaries

- `lfpolicy.models` defines desired and current state objects,
  resource references, LF-Tag definitions, named LF-Tag expressions, tag
  assignments, grants, and optional guardrail config. These classes normalize
  input and expose JSON-compatible dictionaries.
- `lfpolicy.config` contains the matching helpers for lint severity
  overrides, ownership boundaries, ignore rules, and scoped policy exceptions.
- `lfpolicy.audit` compares desired and current state and returns
  findings. It does not create a change plan and does not call AWS.
- `lfpolicy.lint` checks desired-state semantic consistency, such as
  undefined LF-Tag keys or values, without current state or AWS access.
- `lfpolicy.planner` compares desired and current state and returns a
  conservative ordered plan. Destructive changes are included only when the
  matching `PlanOptions` flag is set.
- `lfpolicy.explain` explains one principal/resource access question
  from desired and current state. It is read-only and does not call AWS.
- `lfpolicy.provider` defines the narrow `CurrentStateProvider`
  protocol used by the CLI and integrations to supply current state.
- `lfpolicy.io` reads JSON or optional YAML state files.
- `lfpolicy.cli` handles command parsing, report rendering, file
  output, and exit codes.
- `lfpolicy.aws` is the optional boto3 integration for read-only live
  inventory and import operations.
- `lfpolicy.schema` provides the JSON Schema used by the `schema`
  command and editor or CI validation.

The `lfpolicy.policy` module sits above these boundaries rather than
replacing them. It compiles Python-native tag keys, resource tag assignments,
permission groups, safe permission templates, and IAM role bindings into the
existing `DesiredState` model. The generated desired state still passes the same
schema, lint, audit, plan, review, and explain workflows as hand-authored JSON
or YAML.

For requests that want to stretch `lfpolicy` into a broader service SDK, see
[`library-embedding-boundary.md`](library-embedding-boundary.md).

## Data Flow

Most workflows follow the same path:

1. Read desired state from JSON or YAML.
2. Load current state from a local snapshot or the AWS adapter.
3. Normalize both inputs into `DesiredState` and `CurrentState`.
4. Optionally run `lint_desired()` for desired-policy authoring issues.
5. Run `audit()` for drift findings, `plan()` for reviewable changes, or
   `explain()` for one effective-access question.
6. Render text, JSON, Markdown, or SARIF output.
7. Optionally pass reviewed plan evidence to the consuming service that owns AWS
   write execution.

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
- Review summaries expose `recommended_action`, `hard_block`, and blocking
  reasons for consuming workflows.
- Risky desired grants can be allowed only through scoped exceptions with reason,
  ticket, owner, approver, and expiry metadata.
- The boto3 adapter is read-only; consuming services own grant/revoke execution.

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

The intended import surface is exposed from `lfpolicy`:

```python
from lfpolicy import CurrentState, DesiredState, PlanOptions, audit, explain, lint_desired, plan
```

Use `lfpolicy.aws.AWSLakeFormationAdapter` only for live inventory or
import workflows. Internal helper functions and CLI rendering helpers are not
part of the stable public API.

Use `CurrentStateProvider` when a downstream system already has current state in
files, APIs, caches, or databases and wants to reuse `audit()`, `plan()`, or
`explain()` without the default AWS adapter. Use
`CachedCurrentStateProvider` when the upstream source is expensive but still
should be refreshed through the same provider interface. Cached entries are
keyed by desired-state fingerprint and a provider-context fingerprint so live
AWS cache reuse can distinguish profile, region, catalog, and provider
identity. AWS library integrations should use
`CachedCurrentStateProvider.for_aws(...)` or
`aws_current_state_provider_context(...)`; custom providers should pass a
provider context that identifies their own source environment.

The public API includes a narrow authoring layer under
`lfpolicy.policy` for teams that want rigid permission groups and
generic bundles such as `reader()`, `producer()`, `steward()`,
`data_location_access()`, and `admin()` instead of raw grants. See
[`policy-authoring-direction.md`](policy-authoring-direction.md) for the
direction and constraints.

See [`library-embedding-boundary.md`](library-embedding-boundary.md) for what
embedding requests are intentionally kept out of this public API.

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
