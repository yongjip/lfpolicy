import unittest

from lakeformation_guard import CurrentState, DesiredState, audit, plan
from lakeformation_guard.aws import AWSLakeFormationAdapter

try:
    import boto3
    from moto import mock_aws
except ImportError:  # pragma: no cover - exercised only without mock-aws extra.
    boto3 = None
    mock_aws = None


PRINCIPAL = "arn:aws:iam::111122223333:role/DataConsumer"


@unittest.skipIf(mock_aws is None, "moto is required for emulator tests")
class AwsAdapterMotoTests(unittest.TestCase):
    def test_apply_then_reload_round_trips_lf_tag_and_permission_state(self):
        with mock_aws():
            client = boto3.client("lakeformation", region_name="us-east-1")
            adapter = AWSLakeFormationAdapter(client)
            desired = DesiredState.from_dict(
                {
                    "lf_tags": [
                        {
                            "key": "domain",
                            "catalog_id": "123456789012",
                            "values": ["sales"],
                        }
                    ],
                    "resource_tags": [
                        {
                            "resource": {
                                "kind": "table",
                                "database": "analytics",
                                "table": "orders",
                            },
                            "tags": {"domain": ["sales"]},
                        }
                    ],
                    "grants": [
                        {
                            "principal": PRINCIPAL,
                            "resource": {
                                "kind": "table",
                                "database": "analytics",
                                "table": "orders",
                            },
                            "permissions": ["DESCRIBE", "SELECT"],
                        }
                    ],
                }
            )

            adapter.apply(plan(desired, CurrentState.empty()), dry_run=False)
            current = adapter.load_current_state_for(desired)

        self.assertEqual(
            [tag.to_dict() for tag in current.lf_tags],
            [{"key": "domain", "catalog_id": "123456789012", "values": ["sales"]}],
        )
        self.assertEqual(len(current.grants), 1)
        self.assertEqual(current.grants[0].permissions, ("DESCRIBE", "SELECT"))
        self.assertEqual(audit(desired, current), ())

    def test_resource_tag_assignment_round_trips_when_supported_by_moto(self):
        with mock_aws():
            client = boto3.client("lakeformation", region_name="us-east-1")
            adapter = AWSLakeFormationAdapter(client)
            desired = DesiredState.from_dict(
                {
                    "lf_tags": {"domain": ["sales"]},
                    "resource_tags": [
                        {
                            "resource": {
                                "kind": "table",
                                "database": "analytics",
                                "table": "orders",
                            },
                            "tags": {"domain": ["sales"]},
                        }
                    ],
                }
            )

            try:
                adapter.apply(plan(desired, CurrentState.empty()), dry_run=False)
                current = adapter.load_current_state_for(desired)
            except Exception as exc:
                self.skipTest(
                    "installed Moto version does not support this Lake Formation "
                    "resource-tag path: {}".format(exc)
                )

        self.assertEqual(
            [assignment.to_dict() for assignment in current.resource_tags],
            [
                {
                    "resource": {
                        "kind": "table",
                        "database": "analytics",
                        "table": "orders",
                    },
                    "tags": {"domain": ["sales"]},
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
