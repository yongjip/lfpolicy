# Service Integration

Use `lfguard` as an advisory evidence layer for Lake Formation permission
review and access diagnosis. Services should keep ownership of approval,
customer-facing language, audit storage, and actual grant or revoke execution.
`lfguard` does not decide the service's IAM role layout, approval identity
model, or runtime credential separation.

## Contract Boundary

Call the public CLI module from the service runtime:

```python
[sys.executable, "-m", "lakeformation_guard", "..."]
```

Do not import private `lakeformation_guard.cli` helpers or other implementation
details from application code. Treat JSON files written by `review` and
`explain-batch` as the integration contract.

The consuming service owns runtime AWS credentials. `lfguard` does not bypass
AWS authorization and should not be treated as the component that designs or
enforces service IAM role separation.

Run subprocesses with:

- a timeout;
- temporary desired/request JSON files;
- captured stdout/stderr;
- structured handling for non-zero exits;
- compact audit persistence instead of storing oversized full bundles by
  default.

## Review Flow

Use `review` before granting or changing permissions:

```bash
python -m lakeformation_guard review \
  --desired desired.json \
  --current-cache /tmp/lfguard-current-cache.json \
  --output-dir review/ \
  --force
```

Read `review/summary.json` first. Workflow decisions should use:

- `status`
- `recommended_action`
- `hard_block`
- `blocking_reasons`
- `action_summary`

Do not treat every `severity: "error"` from `lint.json` or `audit.json` as a
workflow block. Severity is the technical governance signal. Workflow action is
expressed by `recommended_action` and `hard_block`.

Use `code`, `action`, and `docs_anchor` for stable service mappings and stored
audit evidence. `docs_url` is a convenience link to live documentation and may
show newer explanatory text than the lfguard version that generated an older
report.

Suggested service labels:

| `recommended_action` | Meaning |
| --- | --- |
| `inform` | Reference only |
| `review_required` | Human review needed |
| `approval_required` | Explicit approval or exception evidence needed |
| `block` | Stop until the request or policy changes |

`review/explain.json` is planned grant-change evidence. It is not an
effective-access answer and should not be used to explain why a principal can or
cannot currently access a resource.

## Access Diagnosis

Use `explain-batch` for operational access questions:

```bash
python -m lakeformation_guard explain-batch \
  --requests access-requests.json \
  --current-snapshot current.json \
  --output json
```

Treat access as allowed only when a result has `decision: "allowed"`. A
principal/resource match without the requested permissions remains `denied`.
Use `diagnosis` for compact UI or ticket summaries, and use the nested
`explain` object for detailed Lake Formation snapshot/desired-state evidence.
`explain-batch` does not diagnose IAM, S3, KMS, or application-layer
authorization.

Prefer `--current-snapshot` when the diagnosis must be reproducible evidence.
Use `--current-cache` for repeated live inventory reads when freshness and AWS
provider context are acceptable for the workflow.

## Apply Boundary

Do not run `lfguard apply` automatically from service approval flows. `apply`
is an explicit operator-controlled execution path after review and approval. If
a service already owns grant/revoke execution, keep that execution path separate
from the lfguard advisory wrapper.

## Fixtures

The repository includes service-facing contract fixtures:

- `examples/artifacts/review-bundle/summary.json`
- `examples/artifacts/review-bundle/explain.json`
- `examples/artifacts/lfguard-explain-batch.json`
- `examples/artifacts/review-cases/`
- `examples/artifacts/explain-batch-cases/`

The matching JSON Schemas live under `docs/schemas/`, and stable finding/action
metadata lives in `docs/finding-catalog.md`. Use the schemas, catalog, and
fixtures to test adapters before wiring live AWS inventory.
