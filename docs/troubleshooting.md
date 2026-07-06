# Troubleshooting

Use `lfguard doctor` first. It checks the installed version, Python runtime,
optional extras, and AWS-related environment variables without making AWS calls.

```bash
lfguard doctor --output json
```

When a workflow requires optional integrations, make the check fail early:

```bash
lfguard doctor --require aws --require yaml
```

## `No module named boto3`

Live AWS commands need the AWS extra:

```bash
python -m pip install "lfguard[aws]"
```

Offline commands such as `sample`, `validate`, `audit`, and `plan` with
`--current-snapshot` do not require boto3.

## YAML files fail to load

YAML support is optional. Install the YAML extra:

```bash
python -m pip install "lfguard[yaml]"
```

JSON files work with the base package.

## `AccessDeniedException` from AWS

`lfguard` uses the caller's normal boto3 credentials and does not bypass AWS
authorization. Check the active profile, region, and IAM or Lake Formation
permissions for the command you are running.

Read-only inventory commands need permissions such as `lakeformation:GetLFTag`,
`lakeformation:GetResourceLFTags`, and `lakeformation:ListPermissions`.
If a consuming service executes grants or revokes after review, that service
owns the matching AWS write permissions. See [`aws-permissions.md`](aws-permissions.md).

## A plan shows no changes

Check that the desired-state file includes the LF-Tags, resources, and grants
you expect to manage. Live inventory is scoped from desired state, and offline
plans compare only the files you pass to `--desired` and `--current-snapshot`.

Run validation to confirm the object counts:

```bash
lfguard validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

## Destructive changes are missing from the plan

This is expected by default. `lfguard` omits permission revokes, resource tag
removals, and LF-Tag value removals unless explicitly allowed:

```bash
lfguard plan \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json \
  --allow-permission-revokes \
  --allow-resource-tag-removals \
  --allow-lf-tag-value-removals
```

Use a separate review path for those plans.

## `--github-summary` fails in CI

`--github-summary` writes to the file path in the `GITHUB_STEP_SUMMARY`
environment variable. GitHub Actions sets it automatically. Other CI systems
should use `--output markdown --output-file artifacts/lfguard-report.md`
instead.

## PyPI install finds an old or missing package

Confirm the exact distribution name:

```bash
python -m pip install lfguard
pipx install lfguard
uv tool install lfguard
```

The import package is `lakeformation_guard`, and the CLI is `lfguard`.
