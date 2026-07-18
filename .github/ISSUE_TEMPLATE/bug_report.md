---
name: Bug report
about: Report reproducible lfpolicy behavior that looks incorrect
title: ""
labels: bug
assignees: ""
---

## What happened?

Describe the behavior you saw and what you expected instead.

## Command or API call

```bash
lfpolicy ...
```

## Minimal desired/current state

Paste the smallest sanitized JSON or YAML example that reproduces the issue.
Remove account IDs, principal names, locations, and table names that should not
be public.

## Environment

- `lfpolicy` version:
- Python version:
- Operating system:
- Install extras used, such as `aws` or `yaml`:
- For live AWS workflows: AWS region and credential source, without secrets:

## Diagnostics

Run this if possible and paste the sanitized output:

```bash
lfpolicy doctor --output json
```

## Notes

Do not include AWS credentials, session tokens, private account IDs, or
sensitive data lake paths.
