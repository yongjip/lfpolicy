# AWS Permissions

`lfguard` uses AWS Lake Formation APIs through boto3 only for read-only live
inventory, snapshot, import, audit, plan, review, explain, and explain-batch
workflows. Offline commands do not need AWS credentials.

`lfguard` does not grant or revoke Lake Formation permissions in 0.9.0 and
later. Consuming services own AWS write IAM roles, approval identity checks,
grant/revoke execution, and audit storage.

## Read-Only Inventory Role

Generate starter IAM policy JSON with:

```bash
lfguard permissions --template read-only --include-glue-read \
  --output-file iam/lfguard-read-only.json
```

Before using a live role, check it against the read-only template:

```bash
lfguard permissions --check --template read-only --profile prod --output json

lfguard permissions --check --template read-only \
  --principal-arn arn:aws:iam::111122223333:role/LfguardReadOnly \
  --include-glue-read
```

The check uses `sts:GetCallerIdentity` when `--principal-arn` is omitted, then
calls IAM `SimulatePrincipalPolicy` for each required action in the selected
template. It exits `0` only when every action is allowed. If the current caller
is an assumed role, `lfguard` normalizes the STS assumed-role ARN to the
underlying IAM role ARN for simulation. The caller running the check must be
allowed to call `iam:SimulatePrincipalPolicy` for the simulated principal; that
permission is for preflight evidence and is not required by ordinary live
inventory workflows.

Use the read-only role for:

- `lfguard snapshot`
- `lfguard import`
- `lfguard audit` without `--current-snapshot`
- `lfguard plan` without `--current-snapshot`
- `lfguard review` without `--current-snapshot`
- `lfguard explain` and `lfguard explain-batch` without `--current-snapshot`

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
catalog metadata used around lfguard:

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

## Execution Boundary

If a service executes Lake Formation writes after reviewing lfguard evidence,
that service should define its own IAM role, approval policy, audit persistence,
and rollback procedure. Keep that write role outside the lfguard package
contract. `lfguard plan` and `review` provide change evidence; AWS authorization
and mutation execution remain with AWS and the consuming service.

See [`aws-api-coverage.md`](aws-api-coverage.md) for the exact boto3 Lake
Formation methods behind live inventory and import.
