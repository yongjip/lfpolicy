# Contributing

Thanks for improving `lfpolicy`.

## Development Setup

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev,aws,yaml]"
python -m unittest discover -s tests
```

## Reporting Issues

Use the GitHub bug report template for reproducible behavior and include
sanitized desired/current state when possible. Run `lfpolicy doctor --output json`
and remove any sensitive account, principal, catalog, or path details before
posting output.

Use the feature request template for new resource shapes, report formats,
workflow integrations, or safety-model changes.

## Feature Request Screening

Before filing a feature request, check these boundary docs:

- [`docs/library-embedding-boundary.md`](docs/library-embedding-boundary.md)
- [`docs/service-integration.md`](docs/service-integration.md)
- [`docs/architecture.md`](docs/architecture.md)

Feature requests are a good fit when they improve review, lint, audit, explain,
plan, review bundles, or narrow Lake Formation modeling without moving service
or workflow ownership into `lfpolicy`.

If a request mixes in-scope and out-of-scope behavior, split it into smaller
issues before filing. Maintainers: triage every request with
[`docs/request-screening.md`](docs/request-screening.md) and apply one
`triage:*` label.

## Design Constraints

- Keep audit and plan logic deterministic and AWS-free.
- Keep boto3 calls in the adapter layer.
- Default plans must remain conservative: no revokes or removals unless the user explicitly enables them.
- Add tests for every planner, audit, review, explain, or adapter behavior change.
- Prefer JSON-compatible public payloads so CLI output can be consumed by CI systems.

## Release Checks

```bash
python -m unittest discover -s tests
python -m build
python -m twine check dist/*
```
