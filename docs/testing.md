# Testing

`lfpolicy` uses layered tests because Lake Formation behavior is split between
pure policy logic, read-only boto3 request shapes, and real AWS service
semantics.

## Default Test Suite

Run the default suite with the test extra:

```bash
python -m pip install -e ".[test]"
python -m unittest discover -s tests
```

The default suite includes pure model, policy, planner, CLI, and botocore
`Stubber` tests. Stubber validates that the adapter sends request parameters
that match the Lake Formation botocore service model without contacting AWS.

## Live AWS Contract Tests

Live tests are disabled by default. Run them only in a sandbox account:

```bash
python -m pip install -e ".[test,aws]"
LFPOLICY_LIVE_AWS=1 \
AWS_REGION=us-east-1 \
python -m unittest tests.test_live_aws_contract
```

For the grant-validation test, also provide a disposable principal:

```bash
LFPOLICY_LIVE_AWS=1 \
LFPOLICY_LIVE_AWS_TEST_PRINCIPAL_ARN=arn:aws:iam::111122223333:role/LfpolicyContractPrincipal \
python -m unittest tests.test_live_aws_contract
```

Optional environment variables:

| Variable | Purpose |
| --- | --- |
| `LFPOLICY_LIVE_AWS` | Must be `1` to enable live tests. |
| `LFPOLICY_LIVE_AWS_PROFILE` | boto3 profile name. |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | AWS region for Glue and Lake Formation clients. |
| `LFPOLICY_LIVE_AWS_CATALOG_ID` | Data Catalog account ID; defaults to STS caller account. |
| `LFPOLICY_LIVE_AWS_TEST_PRINCIPAL_ARN` | Disposable role ARN used for grant validation. |

Live tests cover only behavior local emulators cannot faithfully prove:

- AWS accepts a table LF-Tag value and a column override for the same LF-Tag key.
- AWS rejects a single LF-Tag table-policy grant combining partial-column
  `SELECT` behavior with mutating permissions such as `INSERT`.
- The adapter parses real Lake Formation response shapes for created LF-Tags.

The tests create temporary LF-Tags and Glue Data Catalog metadata and attempt
best-effort cleanup. Do not run them against production accounts.
