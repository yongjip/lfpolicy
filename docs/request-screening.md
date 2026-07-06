# Request Screening

Use this document when maintainers triage feature requests. The goal is to keep
`lfguard` aligned with its advisory review boundary and to leave a clear record
when a request is accepted, narrowed, or declined.

## Required Triage Outcome

- Apply exactly one `triage:*` label to every feature request.
- Split mixed requests before accepting implementation work.
- If a request is declined, close it with the matching canned reply so the same
  request can be redirected consistently later.

## Decision Table

| If the request mainly does this... | Label | Maintainer action |
| --- | --- | --- |
| Improves review, lint, audit, explain, plan, explicit apply, or narrow Lake Formation modeling inside the existing product boundary | `triage:fits-core` | Keep the issue open, refine scope if needed, and implement or queue it normally |
| Targets a valid `lfguard` goal, but the current shape is too broad, mixed, or not reviewable yet | `triage:needs-reframe` | Ask for a narrower follow-up or split issues before implementation |
| Pushes `lfguard` into request-time mutation helpers, approval workflow ownership, dynamic desired-state expansion, broad discovery SDK behavior, or service-owned orchestration | `triage:out-of-scope` | Reply with the boundary rationale and close as not planned |

## Boundary Questions

Answer these before accepting a request:

- Does this preserve `lfguard` as advisory evidence first, not a service runtime?
- Can desired state, lint, audit, explain, review, and plan stay deterministic
  and reviewable?
- If live AWS behavior is involved, is this a narrow adapter addition rather
  than broad browse or discovery coverage?
- Does destructive behavior stay explicit behind planner options and CLI flags?
- Does the request avoid taking ownership of service IAM layout, approval
  identity, workflow state, or request-time execution semantics?

If the answer to any of these is "no", the request usually needs reframing or
should be declined.

## Primary References

Use these docs together when triaging:

- [`library-embedding-boundary.md`](library-embedding-boundary.md)
- [`service-integration.md`](service-integration.md)
- [`architecture.md`](architecture.md)

## Canned Replies

### `triage:fits-core`

This request fits `lfguard` core. It stays inside the advisory review boundary,
keeps plan and audit behavior deterministic, and does not turn `lfguard` into a
service-specific mutation runtime.

### `triage:needs-reframe`

The goal may fit `lfguard`, but the current issue is too broad or mixes
different kinds of behavior. Please narrow this to one reviewable change or
split it into separate issues so we can evaluate the in-scope part cleanly.

### `triage:out-of-scope`

This request is outside the `lfguard` product boundary. We are keeping
`lfguard` focused on advisory evidence, deterministic review and planning, and
explicit apply. Request-time orchestration, broad service SDK behavior, and
service-owned workflow semantics belong in the consuming service or a raw boto3
wrapper.
