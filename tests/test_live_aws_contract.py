import os
import time
import unittest
from uuid import uuid4

from lfpolicy import DesiredState
from lfpolicy.aws import AWSLakeFormationAdapter

try:
    import boto3
    from botocore.exceptions import ClientError
except ImportError:  # pragma: no cover - exercised only without aws extra.
    boto3 = None
    ClientError = None


LIVE_AWS_ENABLED = os.environ.get("LFPOLICY_LIVE_AWS") == "1"
LIVE_TEST_PRINCIPAL = os.environ.get("LFPOLICY_LIVE_AWS_TEST_PRINCIPAL_ARN", "")


@unittest.skipUnless(LIVE_AWS_ENABLED, "set LFPOLICY_LIVE_AWS=1 to run live AWS tests")
@unittest.skipIf(boto3 is None, "boto3 is required for live AWS tests")
class LiveAwsLakeFormationContractTests(unittest.TestCase):
    """Live tests for Lake Formation behavior that local emulators cannot prove.

    These tests create temporary LF-Tags and Glue catalog metadata in the target
    account. They are intentionally opt-in and should run only against a sandbox
    account with a disposable test principal.
    """

    @classmethod
    def setUpClass(cls):
        profile_name = os.environ.get("LFPOLICY_LIVE_AWS_PROFILE") or None
        region_name = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
        cls.session = boto3.Session(profile_name=profile_name, region_name=region_name)
        cls.lakeformation = cls.session.client("lakeformation")
        cls.glue = cls.session.client("glue")
        cls.sts = cls.session.client("sts")
        cls.catalog_id = os.environ.get("LFPOLICY_LIVE_AWS_CATALOG_ID")
        if not cls.catalog_id:
            cls.catalog_id = cls.sts.get_caller_identity()["Account"]

    def setUp(self):
        suffix = uuid4().hex[:10]
        self.tag_key = "lfpolicy_contract_{}".format(suffix)
        self.database_name = "lfpolicy_contract_{}".format(suffix)
        self.table_name = "orders_{}".format(suffix)
        self.created_lf_tags = []
        self.created_tables = []
        self.created_databases = []

    def tearDown(self):
        for principal, resource, permissions in getattr(self, "created_grants", []):
            try:
                self.lakeformation.revoke_permissions(
                    Principal={"DataLakePrincipalIdentifier": principal},
                    Resource=resource,
                    Permissions=permissions,
                    CatalogId=self.catalog_id,
                )
            except Exception:
                pass
        for database_name, table_name in reversed(self.created_tables):
            try:
                self.glue.delete_table(
                    CatalogId=self.catalog_id,
                    DatabaseName=database_name,
                    Name=table_name,
                )
            except Exception:
                pass
        for database_name in reversed(self.created_databases):
            try:
                self.glue.delete_database(CatalogId=self.catalog_id, Name=database_name)
            except Exception:
                pass
        for tag_key in reversed(self.created_lf_tags):
            try:
                self.lakeformation.delete_lf_tag(CatalogId=self.catalog_id, TagKey=tag_key)
            except Exception:
                pass

    def test_real_aws_accepts_table_tag_with_column_override_for_same_lf_tag_key(self):
        self._create_lf_tag(self.tag_key, ["false", "true"])
        self._create_glue_table()

        self.lakeformation.add_lf_tags_to_resource(
            CatalogId=self.catalog_id,
            Resource={
                "Table": {
                    "CatalogId": self.catalog_id,
                    "DatabaseName": self.database_name,
                    "Name": self.table_name,
                }
            },
            LFTags=[{"TagKey": self.tag_key, "TagValues": ["false"]}],
        )
        self.lakeformation.add_lf_tags_to_resource(
            CatalogId=self.catalog_id,
            Resource={
                "TableWithColumns": {
                    "CatalogId": self.catalog_id,
                    "DatabaseName": self.database_name,
                    "Name": self.table_name,
                    "ColumnNames": ["phone_number"],
                }
            },
            LFTags=[{"TagKey": self.tag_key, "TagValues": ["true"]}],
        )

        response = self.lakeformation.get_resource_lf_tags(
            CatalogId=self.catalog_id,
            Resource={
                "TableWithColumns": {
                    "CatalogId": self.catalog_id,
                    "DatabaseName": self.database_name,
                    "Name": self.table_name,
                    "ColumnNames": ["phone_number"],
                }
            },
        )

        column_tags = response.get("LFTagsOnColumns", [])
        self.assertTrue(
            any(
                column.get("Name") == "phone_number"
                and {"TagKey": self.tag_key, "TagValues": ["true"]} in column.get("LFTags", [])
                for column in column_tags
            ),
            response,
        )

    @unittest.skipUnless(
        LIVE_TEST_PRINCIPAL,
        "set LFPOLICY_LIVE_AWS_TEST_PRINCIPAL_ARN for live grant validation",
    )
    def test_real_aws_rejects_lf_tag_policy_select_plus_mutating_permissions(self):
        self.created_grants = []
        self._create_lf_tag(self.tag_key, ["false", "true"])
        resource = {
            "LFTagPolicy": {
                "ResourceType": "TABLE",
                "Expression": [{"TagKey": self.tag_key, "TagValues": ["false"]}],
            }
        }

        try:
            self.lakeformation.grant_permissions(
                CatalogId=self.catalog_id,
                Principal={"DataLakePrincipalIdentifier": LIVE_TEST_PRINCIPAL},
                Resource=resource,
                Permissions=["SELECT", "INSERT"],
            )
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code")
            self.assertIn(code, {"InvalidInputException", "InvalidOperationException"})
            return

        self.created_grants.append((LIVE_TEST_PRINCIPAL, resource, ["SELECT", "INSERT"]))
        self.fail("AWS accepted SELECT plus INSERT on one LF-Tag table policy grant")

    def test_adapter_parses_real_lf_tag_response_shape(self):
        self._create_lf_tag(self.tag_key, ["false", "true"])
        adapter = AWSLakeFormationAdapter(self.lakeformation, catalog_id=self.catalog_id)
        desired = DesiredState.from_dict({"lf_tags": {self.tag_key: ["false", "true"]}})

        current = adapter.load_current_state_for(desired)

        self.assertEqual(current.lf_tags[0].key, self.tag_key)
        self.assertEqual(current.lf_tags[0].values, ("false", "true"))

    def _create_lf_tag(self, tag_key, tag_values):
        self.lakeformation.create_lf_tag(
            CatalogId=self.catalog_id,
            TagKey=tag_key,
            TagValues=tag_values,
        )
        self.created_lf_tags.append(tag_key)

    def _create_glue_table(self):
        self.glue.create_database(
            CatalogId=self.catalog_id,
            DatabaseInput={"Name": self.database_name},
        )
        self.created_databases.append(self.database_name)
        self.glue.create_table(
            CatalogId=self.catalog_id,
            DatabaseName=self.database_name,
            TableInput={
                "Name": self.table_name,
                "TableType": "EXTERNAL_TABLE",
                "StorageDescriptor": {
                    "Columns": [
                        {"Name": "login_id", "Type": "string"},
                        {"Name": "phone_number", "Type": "string"},
                    ],
                    "Location": "s3://lfpolicy-contract-placeholder/{}/".format(
                        int(time.time())
                    ),
                    "InputFormat": "org.apache.hadoop.mapred.TextInputFormat",
                    "OutputFormat": "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat",
                    "SerdeInfo": {
                        "SerializationLibrary": "org.apache.hadoop.hive.serde2.lazy.LazySimpleSerDe",
                    },
                },
            },
        )
        self.created_tables.append((self.database_name, self.table_name))


if __name__ == "__main__":
    unittest.main()
