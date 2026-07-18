import unittest

from lfpolicy.aws_permissions import (
    AWSIAMPermissionChecker,
    iam_policy_actions,
    iam_policy_template,
    policy_source_arn_from_caller,
)

try:
    import botocore.session
    from botocore.stub import Stubber
except ImportError:  # pragma: no cover - exercised only without test extras.
    botocore = None
    Stubber = None  # type: ignore[assignment]


ACCOUNT_ID = "111122223333"


class AwsPermissionTemplateTests(unittest.TestCase):
    def test_template_actions_are_stable_and_unique(self):
        policy = iam_policy_template("read-only", include_glue_read=True)

        self.assertEqual(
            iam_policy_actions(policy),
            (
                "lakeformation:GetLFTag",
                "lakeformation:ListLFTags",
                "lakeformation:GetLFTagExpression",
                "lakeformation:ListLFTagExpressions",
                "lakeformation:GetResourceLFTags",
                "lakeformation:ListPermissions",
                "lakeformation:GetDataCellsFilter",
                "lakeformation:ListDataCellsFilter",
                "glue:GetDatabase",
                "glue:GetDatabases",
                "glue:GetTable",
                "glue:GetTables",
            ),
        )

    def test_removed_apply_templates_are_rejected(self):
        for template in ("additive-apply", "destructive-apply"):
            with self.subTest(template=template):
                with self.assertRaisesRegex(ValueError, "Unsupported IAM permission template"):
                    iam_policy_template(template)

    def test_policy_source_arn_normalizes_assumed_role(self):
        self.assertEqual(
            policy_source_arn_from_caller(
                "arn:aws:sts::111122223333:assumed-role/LfpolicyApply/github-actions"
            ),
            "arn:aws:iam::111122223333:role/LfpolicyApply",
        )

    def test_policy_source_arn_keeps_iam_role_or_user_arn(self):
        for arn in (
            "arn:aws:iam::111122223333:role/LfpolicyApply",
            "arn:aws:iam::111122223333:user/platform-bot",
        ):
            self.assertEqual(policy_source_arn_from_caller(arn), arn)

    def test_policy_source_arn_rejects_unusable_sts_identity(self):
        with self.assertRaisesRegex(RuntimeError, "pass --principal-arn"):
            policy_source_arn_from_caller("arn:aws:sts::111122223333:federated-user/platform")


@unittest.skipIf(Stubber is None, "botocore is required for AWS permission tests")
class AwsPermissionCheckerStubberTests(unittest.TestCase):
    def setUp(self):
        session = botocore.session.get_session()
        self.iam = session.create_client(
            "iam",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            aws_session_token="testing",
        )
        self.sts = session.create_client(
            "sts",
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
            aws_session_token="testing",
        )
        self.iam_stubber = Stubber(self.iam)
        self.sts_stubber = Stubber(self.sts)
        self.iam_stubber.activate()
        self.sts_stubber.activate()
        self.addCleanup(self.iam_stubber.deactivate)
        self.addCleanup(self.sts_stubber.deactivate)

    def test_check_uses_current_assumed_role_and_reports_denied_actions(self):
        checker = AWSIAMPermissionChecker(self.iam, self.sts)
        actions = ("lakeformation:ListPermissions", "lakeformation:GetDataCellsFilter")

        self.sts_stubber.add_response(
            "get_caller_identity",
            {
                "UserId": "testing",
                "Account": ACCOUNT_ID,
                "Arn": "arn:aws:sts::111122223333:assumed-role/LfpolicyApply/session",
            },
            {},
        )
        self.iam_stubber.add_response(
            "simulate_principal_policy",
            {
                "EvaluationResults": [
                    {
                        "EvalActionName": "lakeformation:ListPermissions",
                        "EvalResourceName": "*",
                        "EvalDecision": "allowed",
                    },
                    {
                        "EvalActionName": "lakeformation:GetDataCellsFilter",
                        "EvalResourceName": "*",
                        "EvalDecision": "implicitDeny",
                    },
                ],
                "IsTruncated": False,
            },
            {
                "PolicySourceArn": "arn:aws:iam::111122223333:role/LfpolicyApply",
                "ActionNames": list(actions),
                "ResourceArns": ["*"],
            },
        )

        report = checker.check(actions, template="read-only")

        self.assertFalse(report.allowed)
        self.assertEqual(report.principal_arn, "arn:aws:iam::111122223333:role/LfpolicyApply")
        self.assertEqual(report.caller_arn, "arn:aws:sts::111122223333:assumed-role/LfpolicyApply/session")
        self.assertEqual(report.denied_actions, ("lakeformation:GetDataCellsFilter",))
        self.assertEqual(report.to_dict()["summary"], {"total": 2, "allowed": 1, "denied": 1})
        self.iam_stubber.assert_no_pending_responses()
        self.sts_stubber.assert_no_pending_responses()

    def test_check_accepts_explicit_principal_and_handles_pagination(self):
        checker = AWSIAMPermissionChecker(self.iam, self.sts)
        actions = ("lakeformation:GetLFTag", "lakeformation:ListPermissions")

        self.iam_stubber.add_response(
            "simulate_principal_policy",
            {
                "EvaluationResults": [
                    {
                        "EvalActionName": "lakeformation:GetLFTag",
                        "EvalResourceName": "*",
                        "EvalDecision": "allowed",
                    }
                ],
                "IsTruncated": True,
                "Marker": "next",
            },
            {
                "PolicySourceArn": "arn:aws:iam::111122223333:role/LfpolicyReadOnly",
                "ActionNames": list(actions),
                "ResourceArns": ["*"],
            },
        )
        self.iam_stubber.add_response(
            "simulate_principal_policy",
            {
                "EvaluationResults": [
                    {
                        "EvalActionName": "lakeformation:ListPermissions",
                        "EvalResourceName": "*",
                        "EvalDecision": "allowed",
                    }
                ],
                "IsTruncated": False,
            },
            {
                "PolicySourceArn": "arn:aws:iam::111122223333:role/LfpolicyReadOnly",
                "ActionNames": list(actions),
                "ResourceArns": ["*"],
                "Marker": "next",
            },
        )

        report = checker.check(
            actions,
            template="read-only",
            principal_arn="arn:aws:iam::111122223333:role/LfpolicyReadOnly",
        )

        self.assertTrue(report.allowed)
        self.assertIsNone(report.caller_arn)
        self.assertEqual(report.denied_actions, ())
        self.iam_stubber.assert_no_pending_responses()
        self.sts_stubber.assert_no_pending_responses()


if __name__ == "__main__":
    unittest.main()
