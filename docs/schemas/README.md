# Report Contract Schemas

These JSON Schemas describe the stable report fields that services, CI jobs,
ticket workflows, and LLM agents should rely on.

They intentionally validate the public contract surface, not every nested Lake
Formation payload detail. Fields such as `resource`, `details`, `before`,
`after`, and `payload` remain extensible so new Lake Formation shapes can be
added without breaking consumers that only need the governance contract.

Recommended use:

- validate `schema_version` before reading a report;
- use `recommended_action`, `hard_block`, and review `status` for workflow
  decisions;
- use `explain-batch` result `decision` for access diagnosis;
- use `code`, `action`, and `docs_anchor` for stable service mappings and
  stored evidence;
- avoid treating every `severity: "error"` as a hard block.

Compatibility policy:

- minor releases may add optional fields, finding codes, plan actions, and
  nested Lake Formation payload details;
- minor releases must not remove stable required fields or change the meaning of
  existing `recommended_action`, `hard_block`, `status`, or `decision` fields
  without explicit release-note documentation;
- schemas intentionally avoid closed enums for finding `code` and plan `action`;
- `docs_url` is a convenience link to live documentation and may show newer
  explanatory text than the lfpolicy version that generated historical evidence;
- services should use [`../finding-catalog.md`](../finding-catalog.md) for
  stable finding and plan action metadata.

Available schemas:

- `lfpolicy.audit.v1.schema.json`
- `lfpolicy.lint.v1.schema.json`
- `lfpolicy.plan.v1.schema.json`
- `lfpolicy.review.manifest.v1.schema.json`
- `lfpolicy.review.summary.v1.schema.json`
- `lfpolicy.review.explain.v1.schema.json`
- `lfpolicy.explain_batch.v1.schema.json`
