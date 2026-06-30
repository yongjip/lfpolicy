# LLM Agent Integration

Use this guide when an LLM agent, DMS workflow, approval assistant, or service
reads `lfguard` JSON output. This is runtime integration guidance, not coding
agent guidance for modifying this repository. Repository coding agents should
start with [`../AGENTS.md`](../AGENTS.md).

Backend services should invoke `lfguard` through the CLI module and consume JSON
artifacts. See [`service-integration.md`](service-integration.md) for the
subprocess contract boundary.

## Core Rule

Separate technical severity from workflow action.

- `severity` describes the governance signal produced by `lfguard`.
- `recommended_action` tells the consuming workflow what to do next.
- `hard_block` is a boolean shortcut for `recommended_action: "block"`.

Do not convert every `severity: "error"` into a user-facing block. In advisory
flows, many errors mean "policy risk found; get review or approval", not
"execution is impossible".

## Action Meanings

| `recommended_action` | Agent behavior | User-facing language |
| --- | --- | --- |
| `inform` | Show as context only. | 참고 |
| `review_required` | Summarize evidence and route to a reviewer. | 검토 필요 |
| `approval_required` | Ask for explicit approval, exception metadata, or ticket evidence. | 승인 필요 |
| `block` | Stop the workflow until the policy or request changes. | 차단 사유 |

Use `hard_block: true` only for "cannot proceed" language. Otherwise, prefer
"검토 필요", "승인 필요", or "정책상 위험 항목 발견".

## Review Bundle Decision Rules

Read `review/summary.json` first.

1. If `status` is `blocked`, stop. Explain `blocking_reasons`.
2. If any record has `hard_block: true`, stop even if the caller did not inspect
   `summary.json` first.
3. If `recommended_action` is `approval_required`, request approval evidence,
   exception metadata, or a linked ticket before continuing.
4. If `recommended_action` is `review_required`, summarize the plan, lint, and
   audit evidence for a human reviewer.
5. If `recommended_action` is `inform`, show the finding only as context.
6. Do not run `lfguard apply` from a review bundle alone. Apply requires a
   separate explicit approval decision and the normal lfguard apply flags.

Recommended review summary handling:

```json
{
  "status": "review_required",
  "recommended_action": "approval_required",
  "action_summary": {
    "inform": 0,
    "review_required": 1,
    "approval_required": 1,
    "block": 0
  },
  "blocking_reasons": []
}
```

The correct interpretation is: "This is not blocked, but it needs approval
before proceeding."

## Finding And Change Rules

For `lint.json`, `audit.json`, and `plan.json`, inspect each item:

```json
{
  "severity": "error",
  "recommended_action": "approval_required",
  "hard_block": false
}
```

The correct interpretation is: "This is a serious governance signal, but the
workflow should request approval rather than claim the request is impossible."

Examples:

- Broad principal, `SUPER`, mutating grant, grant option, or named grant:
  usually `approval_required`.
- Safe additive grant or drift evidence: usually `review_required`.
- Expired exception, duplicate identity, invalid LF-Tag reference, invalid
  permission combination, or destructive planned change: usually `block`.

## Explain Rules

`review/explain.json` is planned grant-change evidence. It answers:

- What grant changes are planned?
- Which principal/resource/permissions are involved?
- What was before and what would be after?
- Why is the grant change planned?

It does not answer arbitrary access questions. Do not use it to tell a user why
someone currently can or cannot access a table.

For operational access questions, use `explain-batch`:

```bash
lfguard explain-batch \
  --requests access-requests.json \
  --current-snapshot current.json \
  --output json
```

Only treat an access request as allowed when the result decision is `allowed`.
If a grant matches the principal and resource but lacks the requested
permission, the decision remains `denied`.

## Prompting Pattern

When an LLM agent summarizes a review bundle, use this order:

1. State the review `status` and `recommended_action`.
2. If blocked, list `blocking_reasons` and stop.
3. Summarize planned safe changes.
4. Summarize approval-required risks and their tickets or missing metadata.
5. Point to `explain-batch` for current access decisions.
6. Avoid saying "failed" unless `status` is `blocked`.

Good wording:

```text
검토 필요입니다. 차단 사유는 없습니다. 다만 broad permission grant가 있어
승인 필요 항목으로 표시됩니다. 티켓/승인자/만료일을 확인한 뒤 진행하세요.
```

Bad wording:

```text
오류가 있으므로 권한 부여가 불가능합니다.
```

That wording incorrectly treats `severity: "error"` as a hard block.

## Required Inputs For Exceptions

Exception records must include:

- `ticket`
- `owner`
- `approved_by`
- `reason`
- `expires_at`

Expired exceptions are hard-block candidates. Exceptions expiring soon and
exceptions where `owner` equals `approved_by` should be surfaced as review
warnings, not hidden.

## Do Not

- Do not infer approval from `passed`, `review_required`, or `approval_required`.
- Do not run apply automatically from any JSON report.
- Do not use severity alone for workflow decisions.
- Do not describe review planned-grant evidence as effective-access evidence.
- Do not hide `hard_block` findings behind a generic summary.
