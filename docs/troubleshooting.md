# Troubleshooting

Use `lfpolicy doctor` first. It checks the installed version, Python runtime,
optional extras, and AWS-related environment variables without making AWS calls.

```bash
lfpolicy doctor --output json
```

When a workflow requires optional integrations, make the check fail early:

```bash
lfpolicy doctor --require aws --require yaml
```

## `No module named boto3`

Live AWS commands need the AWS extra:

```bash
python -m pip install "lfpolicy[aws]"
```

Offline commands such as `sample`, `validate`, `audit`, and `plan` with
`--current-snapshot` do not require boto3.

## YAML files fail to load

YAML support is optional. Install the YAML extra:

```bash
python -m pip install "lfpolicy[yaml]"
```

JSON files work with the base package.

## `AccessDeniedException` from AWS

`lfpolicy` uses the caller's normal boto3 credentials and does not bypass AWS
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
lfpolicy validate \
  --desired policy/desired.json \
  --current-snapshot snapshots/prod-current.json
```

## Destructive changes are missing from the plan

This is expected by default. `lfpolicy` omits permission revokes, resource tag
removals, and LF-Tag value removals unless explicitly allowed:

```bash
lfpolicy plan \
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
should use `--output markdown --output-file artifacts/lfpolicy-report.md`
instead.

## PyPI install finds an old or missing package

Confirm the exact distribution name:

```bash
python -m pip install lfpolicy
pipx install lfpolicy
uv tool install lfpolicy
```

The import package is `lfpolicy`, and the CLI is `lfpolicy`.
