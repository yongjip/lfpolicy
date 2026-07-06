# Contributing

Thanks for improving `lfguard`.

## Development Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev,aws,yaml]"
python -m unittest discover -s tests
```

## Reporting Issues

Use the GitHub bug report template for reproducible behavior and include
sanitized desired/current state when possible. Run `lfguard doctor --output json`
and remove any sensitive account, principal, catalog, or path details before
posting output.

Use the feature request template for new resource shapes, report formats,
workflow integrations, or safety-model changes.

## Feature Request Screening

Before filing a feature request, check these boundary docs:

- `docs/library-embedding-boundary.md`
- `docs/service-integration.md`
- `docs/architecture.md`

Requests are a better fit for `lfguard` core when they:

- improve review, lint, audit, explain, plan, or explicit apply behavior;
- add narrow support for already modeled Lake Formation resources;
- keep audit and plan deterministic and reviewable;
- keep service orchestration, approval state, and request-time execution logic
  outside `lfguard`.

Requests are usually not planned when they:

- turn `lfguard` into a request-time mutation SDK for one HTTP handler;
- add automatic apply, rollback orchestration, or portal-specific execution
  semantics;
- broaden the AWS adapter into full browse, discovery, or control-plane service
  abstractions;
- require dynamic desired-state expansion from live AWS at plan time;
- promote internal helper modules to public API only to stabilize downstream
  imports.

If a request mixes in-scope and out-of-scope behavior, split it into smaller
issues before filing.

## Design Constraints

- Keep audit and plan logic deterministic and AWS-free.
- Keep boto3 calls in the adapter layer.
- Default plans must remain conservative: no revokes or removals unless the user explicitly enables them.
- Add tests for every planner, audit, or apply behavior change.
- Prefer JSON-compatible public payloads so CLI output can be consumed by CI systems.

## Release Checks

```bash
python -m unittest discover -s tests
python -m build
python -m twine check dist/*
```
