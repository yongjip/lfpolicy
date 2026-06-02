# AWS Permissions

`lfguard` uses AWS Lake Formation APIs through boto3 only when live AWS state or
execution is requested. Offline `audit` and `plan` commands do not need AWS
credentials.

Exact permissions vary by resource type and by your Lake Formation
administration model. Start with a read-only role for audit and plan workflows,
then use a separate apply role for execution.

Generate starter IAM policy JSON with:

```bash
lfguard permissions --template read-only --include-glue-read \
  --output-file iam/lfguard-read-only.json

lfguard permissions --template additive-apply \
  --output-file iam/lfguard-additive-apply.json

lfguard permissions --template destructive-apply \
  --output-file iam/lfguard-destructive-apply.json
```

Before using a live role, check it against the same templates:

```bash
lfguard permissions --check --template read-only --profile prod --output json

lfguard permissions --check --template additive-apply \
  --principal-arn arn:aws:iam::111122223333:role/LfguardApply \
  --include-glue-read
```

The check uses `sts:GetCallerIdentity` when `--principal-arn` is omitted, then
calls IAM `SimulatePrincipalPolicy` for each required action in the selected
template. It exits `0` only when every action is allowed. If the current caller
is an assumed role, `lfguard` normalizes the STS assumed-role ARN to the
underlying IAM role ARN for simulation. The caller running the check must be
allowed to call `iam:SimulatePrincipalPolicy` for the simulated principal; that
permission is for preflight evidence and is not required by ordinary live
`audit`, `plan`, `snapshot`, or `apply` workflows.

## Read-Only Inventory Role

Use this for `lfguard snapshot`, or for `lfguard audit` and `lfguard plan` when
`--current-snapshot` is not provided and live AWS inventory is loaded.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lakeformation:GetLFTag",
        "lakeformation:ListLFTags",
        "lakeformation:GetLFTagExpression",
        "lakeformation:ListLFTagExpressions",
        "lakeformation:GetResourceLFTags",
        "lakeformation:ListPermissions",
        "lakeformation:GetDataCellsFilter",
        "lakeformation:ListDataCellsFilter"
      ],
      "Resource": "*"
    }
  ]
}
```

Depending on your environment, you may also need Glue read permissions for
catalog discovery handled outside `lfguard`, such as:

```json
{
  "Effect": "Allow",
  "Action": [
    "glue:GetDatabase",
    "glue:GetDatabases",
    "glue:GetTable",
    "glue:GetTables"
  ],
  "Resource": "*"
}
```

## Additive Apply Role

Use this for reviewed apply workflows that only create LF-Tags, add LF-Tag
values, create named LF-Tag expressions, create data cells filters, add
resource tags, or grant permissions.

The `lfguard permissions` apply templates include the read-only inventory
statement too, so live `plan` and `apply` can load current state when
`--current-snapshot` is omitted. The snippets below show the write statements
that separate additive and destructive workflows.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lakeformation:CreateLFTag",
        "lakeformation:CreateDataCellsFilter",
        "lakeformation:CreateLFTagExpression",
        "lakeformation:UpdateLFTag",
        "lakeformation:AddLFTagsToResource",
        "lakeformation:GrantPermissions"
      ],
      "Resource": "*"
    }
  ]
}
```

## Destructive Apply Role

Use this only for separately reviewed workflows that intentionally update or
delete named LF-Tag expressions or data cells filters, remove LF-Tag
assignments, or revoke Lake Formation permissions.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "lakeformation:DeleteLFTagExpression",
        "lakeformation:DeleteDataCellsFilter",
        "lakeformation:RemoveLFTagsFromResource",
        "lakeformation:UpdateDataCellsFilter",
        "lakeformation:UpdateLFTagExpression",
        "lakeformation:RevokePermissions"
      ],
      "Resource": "*"
    }
  ]
}
```

For production use, scope the role with your existing AWS account boundaries,
Lake Formation administrator model, permission boundaries, and deployment
process. Keep revoke and tag removal permissions out of routine automation if
your governance process requires separate approval for destructive changes.

See [`aws-api-coverage.md`](aws-api-coverage.md) for the exact boto3 Lake
Formation methods behind each live inventory and apply operation.
