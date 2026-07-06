import json
import tempfile
import unittest
from pathlib import Path

import lakeformation_guard
from lakeformation_guard.lint import lint_desired
from lakeformation_guard.models import DesiredState
from lakeformation_guard.policy import (
    LakePolicy,
    PermissionTemplate,
    PolicyValidationError,
    TagAssignmentScope,
    admin,
    data_location_access,
    database_creator,
    editor,
    load_policy,
    producer,
    reader,
    steward,
    table_creator,
)


class PolicyAuthoringTests(unittest.TestCase):
    def test_tag_key_accepts_descriptive_scope_enums_and_strings(self):
        policy = LakePolicy()

        tag_key = policy.tag_key(
            "domain",
            values=["sales", "finance"],
            assignable_to=[TagAssignmentScope.DATABASE, "table"],
        )

        self.assertEqual(
            tag_key.assignable_to,
            (TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE),
        )
        self.assertFalse(tag_key.can_narrow_columns)

    def test_tag_key_accepts_single_enum_and_single_string_values(self):
        policy = LakePolicy()

        tag_key = policy.tag_key(
            "domain",
            values="sales",
            assignable_to=TagAssignmentScope.TABLE,
        )

        self.assertEqual(tag_key.values, ("sales",))
        self.assertEqual(tag_key.assignable_to, (TagAssignmentScope.TABLE,))

    def test_tag_key_accepts_catalog_scoped_duplicate_names(self):
        policy = LakePolicy()

        first = policy.tag_key(
            "domain",
            catalog_id="111111111111",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        second = policy.tag_key(
            "domain",
            catalog_id="222222222222",
            values=["finance"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )

        self.assertEqual(first.identity, "111111111111:domain")
        self.assertEqual(second.identity, "222222222222:domain")

    def test_reader_group_can_use_column_narrowing_tag(self):
        policy = LakePolicy()
        _define_common_tags(policy)
        policy.group("dataconsumer", reader().where(domain="sales", contains_pii="false"))
        policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")

        policy.validate()

    def test_reader_group_can_use_database_assignable_column_narrowing_tag_alone(self):
        policy = LakePolicy()
        policy.tag_key(
            "contains_pii",
            values=["false", "true"],
            assignable_to=[
                TagAssignmentScope.DATABASE,
                TagAssignmentScope.TABLE,
                TagAssignmentScope.COLUMN,
            ],
        )
        policy.group("dataconsumer", reader().where(contains_pii="false"))
        policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")

        desired = policy.to_desired_state()

        self.assertEqual(
            desired.grants[0].resource.to_dict()["expression"],
            {"contains_pii": ["false"]},
        )
        self.assertEqual(
            desired.grants[1].resource.to_dict()["expression"],
            {"contains_pii": ["false"]},
        )

    def test_group_filters_accept_mapping_for_non_identifier_tag_keys(self):
        policy = LakePolicy()
        policy.tag_key(
            "data-domain",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.group("dataconsumer", reader().where({"data-domain": "sales"}))
        policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")

        desired = policy.to_desired_state()

        self.assertEqual(
            desired.grants[0].resource.to_dict()["expression"],
            {"data-domain": ["sales"]},
        )

    def test_where_tags_is_a_descriptive_mapping_alias(self):
        policy = LakePolicy()
        policy.tag_key(
            "data-domain",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.group("dataconsumer", reader().where_tags({"data-domain": "sales"}))
        policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")

        policy.validate()

    def test_editor_group_cannot_use_column_narrowing_tag(self):
        policy = LakePolicy()
        _define_common_tags(policy)
        policy.group("operations", editor().where(domain="sales", contains_pii="false"))

        with self.assertRaisesRegex(ValueError, "can be assigned to columns"):
            policy.validate()

    def test_table_creator_group_cannot_use_column_narrowing_tag(self):
        policy = LakePolicy()
        _define_common_tags(policy)
        policy.group(
            "dataengineer",
            table_creator().where(domain="sales", contains_pii="false"),
        )

        with self.assertRaisesRegex(ValueError, "can be assigned to columns"):
            policy.validate()

    def test_database_creator_cannot_use_tag_filters(self):
        policy = LakePolicy()
        policy.tag_key("domain", values=["sales"], assignable_to=[TagAssignmentScope.DATABASE])
        policy.group("catalog_admin", database_creator().where(domain="sales"))

        with self.assertRaisesRegex(ValueError, "cannot use LF-Tag filters"):
            policy.validate()

    def test_group_rejects_template_function_without_call(self):
        policy = LakePolicy()

        with self.assertRaisesRegex(ValueError, "must be created by reader"):
            policy.group("dataconsumer", reader)  # type: ignore[arg-type]

    def test_validate_rejects_undefined_group_in_binding(self):
        policy = LakePolicy()
        policy.bind_role("arn:aws:iam::111122223333:role/Analyst", "missing_group")

        with self.assertRaisesRegex(ValueError, "undefined permission group"):
            policy.validate()

    def test_validate_findings_include_codes_paths_and_suggestions(self):
        policy = LakePolicy()
        policy.tag_key("domain", values=["sales"], assignable_to=[TagAssignmentScope.DATABASE])
        policy.group("dataconsumer", reader().where(domain="finance", missing="sales"))
        policy.tag_table("sales_curated", "orders", domain="sales")
        policy.bind_role("arn:aws:iam::111122223333:role/Analyst", "missing_group")

        findings = policy.validate_findings()

        self.assertEqual(
            [finding.code for finding in findings],
            [
                "POLICY_GROUP_UNDEFINED_TAG_VALUE",
                "POLICY_GROUP_UNDEFINED_TAG_KEY",
                "POLICY_RESOURCE_TAG_SCOPE_UNSUPPORTED",
                "POLICY_UNDEFINED_PERMISSION_GROUP",
            ],
        )
        self.assertEqual(findings[0].path, "groups.dataconsumer.filters.domain")
        self.assertIn("policy.tag_key('domain'", findings[0].suggestion)
        self.assertEqual(findings[1].path, "groups.dataconsumer.filters.missing")
        self.assertEqual(findings[2].path, "resource_tags.table:database=sales_curated:table=orders.domain")
        self.assertEqual(findings[3].path, "bindings[1].groups.missing_group")

    def test_validate_raises_structured_policy_validation_error(self):
        policy = LakePolicy()
        policy.group("dataconsumer", reader())

        with self.assertRaises(PolicyValidationError) as context:
            policy.validate()

        self.assertEqual(context.exception.findings[0].code, "POLICY_GROUP_FILTER_REQUIRED")
        self.assertIn("groups.dataconsumer.filters", str(context.exception))
        self.assertIn("suggestion:", str(context.exception))

    def test_validate_rejects_undefined_tag_value(self):
        policy = LakePolicy()
        policy.tag_key("domain", values=["sales"], assignable_to=[TagAssignmentScope.DATABASE])
        policy.group("dataconsumer", reader().where(domain="finance"))

        with self.assertRaisesRegex(ValueError, "undefined values"):
            policy.validate()

    def test_to_desired_state_generates_reader_grants(self):
        policy = LakePolicy()
        _define_common_tags(policy)
        policy.group("dataconsumer", reader().where(domain="sales", contains_pii="false"))
        policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")

        desired = policy.to_desired_state()

        self.assertEqual(
            desired.lf_tag_key_metadata[0].to_dict(),
            {"key": "contains_pii", "assignable_to": ["database", "table", "column"]},
        )
        self.assertEqual(len(desired.grants), 2)
        self.assertEqual(desired.grants[0].resource.resource_type, "DATABASE")
        self.assertEqual(
            desired.grants[0].resource.to_dict()["expression"],
            {"contains_pii": ["false"], "domain": ["sales"]},
        )
        self.assertEqual(desired.grants[0].permissions, ("DESCRIBE",))
        self.assertEqual(desired.grants[1].resource.resource_type, "TABLE")
        self.assertEqual(
            desired.grants[1].resource.to_dict()["expression"],
            {"contains_pii": ["false"], "domain": ["sales"]},
        )
        self.assertEqual(desired.grants[1].permissions, ("DESCRIBE", "SELECT"))

    def test_group_can_compile_named_lf_tag_expression_grants(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            values=["sales", "finance"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.group("analytics", reader().where(domain="sales")).as_named_expression(
            name="AnalyticsReaders",
            description="Reusable analytics reader expression",
        )
        policy.bind_role("arn:aws:iam::111122223333:role/Analyst", "analytics")

        desired = policy.to_desired_state()

        self.assertEqual(len(desired.lf_tag_expressions), 1)
        self.assertEqual(
            desired.lf_tag_expressions[0].to_dict(),
            {
                "name": "AnalyticsReaders",
                "expression": {"domain": ["sales"]},
                "description": "Reusable analytics reader expression",
            },
        )
        self.assertEqual(
            [grant.resource.to_dict() for grant in desired.grants],
            [
                {
                    "kind": "lf_tag_policy",
                    "resource_type": "DATABASE",
                    "expression_name": "AnalyticsReaders",
                },
                {
                    "kind": "lf_tag_policy",
                    "resource_type": "TABLE",
                    "expression_name": "AnalyticsReaders",
                },
            ],
        )
        self.assertFalse(lint_desired(desired))

    def test_intent_can_compile_named_lf_tag_expression_grants(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            catalog_id="222222222222",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.group(
            "analytics",
            reader(catalog_id="222222222222")
            .where(domain="sales")
            .as_named_expression("AnalyticsReaders"),
        )
        policy.bind_role("arn:aws:iam::111122223333:role/Analyst", "analytics")

        desired = policy.to_desired_state()

        self.assertEqual(
            desired.lf_tag_expressions[0].to_dict(),
            {
                "name": "AnalyticsReaders",
                "expression": {"domain": ["sales"]},
                "catalog_id": "222222222222",
            },
        )
        self.assertEqual(
            {grant.resource.catalog_id for grant in desired.grants},
            {"222222222222"},
        )
        self.assertEqual(
            {grant.resource.expression_name for grant in desired.grants},
            {"AnalyticsReaders"},
        )
        self.assertFalse(lint_desired(desired))

    def test_matching_named_lf_tag_expression_groups_dedupe_definition(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.group("analytics_a", reader().where(domain="sales")).as_named_expression("AnalyticsReaders")
        policy.group("analytics_b", reader().where(domain="sales")).as_named_expression("AnalyticsReaders")
        policy.bind_role(
            "arn:aws:iam::111122223333:role/Analyst",
            ["analytics_a", "analytics_b"],
        )

        desired = policy.to_desired_state()

        self.assertEqual(len(desired.lf_tag_expressions), 1)
        self.assertEqual(desired.lf_tag_expressions[0].name, "AnalyticsReaders")

    def test_named_lf_tag_expression_groups_reject_conflicting_definitions(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            values=["sales", "finance"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.group("analytics", reader().where(domain="sales")).as_named_expression("SharedReaders")
        policy.group("finance", reader().where(domain="finance")).as_named_expression("SharedReaders")

        with self.assertRaises(PolicyValidationError) as context:
            policy.validate()

        self.assertIn(
            "POLICY_NAMED_EXPRESSION_CONFLICT",
            {finding.code for finding in context.exception.findings},
        )

    def test_named_lf_tag_expression_groups_require_database_assignable_filters(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.tag_key(
            "sensitivity",
            values=["internal"],
            assignable_to=[TagAssignmentScope.TABLE],
        )
        policy.group(
            "analytics",
            reader().where(domain="sales", sensitivity="internal"),
        ).as_named_expression("AnalyticsReaders")

        with self.assertRaises(PolicyValidationError) as context:
            policy.validate()

        self.assertIn(
            "POLICY_NAMED_EXPRESSION_DATABASE_SCOPE_UNSUPPORTED",
            {finding.code for finding in context.exception.findings},
        )

    def test_to_desired_state_generates_resource_tag_assignments(self):
        policy = LakePolicy()
        _define_common_tags(policy)
        policy.tag_database("sales_curated", domain="sales", contains_pii="false")
        policy.tag_table("sales_curated", "customers", contains_pii="false")
        policy.tag_columns("sales_curated", "customers", ["phone_number"], contains_pii="true")

        desired = policy.to_desired_state()

        self.assertEqual(
            [assignment.to_dict() for assignment in desired.resource_tags],
            [
                {
                    "resource": {"kind": "database", "database": "sales_curated"},
                    "tags": {"contains_pii": ["false"], "domain": ["sales"]},
                },
                {
                    "resource": {
                        "kind": "table",
                        "database": "sales_curated",
                        "table": "customers",
                    },
                    "tags": {"contains_pii": ["false"]},
                },
                {
                    "resource": {
                        "kind": "table_with_columns",
                        "database": "sales_curated",
                        "table": "customers",
                        "columns": ["phone_number"],
                    },
                    "tags": {"contains_pii": ["true"]},
                },
            ],
        )

    def test_resource_tag_assignments_accept_mapping_for_non_identifier_tag_keys(self):
        policy = LakePolicy()
        policy.tag_key(
            "data-domain",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.tag_database("sales_curated", tags={"data-domain": "sales"})

        desired = policy.to_desired_state()

        self.assertEqual(
            desired.resource_tags[0].to_dict(),
            {
                "resource": {"kind": "database", "database": "sales_curated"},
                "tags": {"data-domain": ["sales"]},
            },
        )

    def test_resource_tag_assignment_rejects_mapping_keyword_conflict(self):
        policy = LakePolicy()

        with self.assertRaisesRegex(ValueError, "conflicting values"):
            policy.tag_database("sales_curated", tags={"domain": "sales"}, domain="finance")

    def test_resource_tag_assignment_scope_is_enforced(self):
        policy = LakePolicy()
        _define_common_tags(policy)
        policy.tag_columns("sales_curated", "customers", "phone_number", domain="sales")

        with self.assertRaisesRegex(ValueError, "assignable only to database, table"):
            policy.validate()

    def test_resource_tag_assignment_rejects_undefined_value(self):
        policy = LakePolicy()
        _define_common_tags(policy)
        policy.tag_table("sales_curated", "customers", contains_pii="unknown")

        with self.assertRaisesRegex(ValueError, "assigns undefined value"):
            policy.validate()

    def test_resource_tag_assignment_rejects_conflicting_values(self):
        policy = LakePolicy()
        _define_common_tags(policy)
        policy.tag_table("sales_curated", "customers", domain="sales")

        with self.assertRaisesRegex(ValueError, "already has LF-Tag"):
            policy.tag_table("sales_curated", "customers", domain="finance")

    def test_to_desired_state_generates_catalog_scoped_lf_tags_resources_and_grants(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            catalog_id="111111111111",
            values=["finance"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.tag_key(
            "domain",
            catalog_id="222222222222",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.tag_database("sales_curated", catalog_id="222222222222", domain="sales")
        policy.group("dataconsumer", reader(catalog_id="222222222222").where(domain="sales"))
        policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")

        desired = policy.to_desired_state()

        self.assertEqual(
            {(tag.catalog_id, tag.key, tag.values) for tag in desired.lf_tags},
            {
                ("111111111111", "domain", ("finance",)),
                ("222222222222", "domain", ("sales",)),
            },
        )
        self.assertEqual(desired.resource_tags[0].resource.catalog_id, "222222222222")
        self.assertEqual(
            {grant.resource.catalog_id for grant in desired.grants},
            {"222222222222"},
        )
        self.assertIsInstance(desired.to_dict()["lf_tag_key_metadata"], list)
        self.assertFalse(lint_desired(desired))

    def test_catalog_scoped_policy_group_requires_catalog_when_tag_key_is_ambiguous(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            catalog_id="111111111111",
            values=["finance"],
            assignable_to=[TagAssignmentScope.DATABASE],
        )
        policy.tag_key(
            "domain",
            catalog_id="222222222222",
            values=["sales"],
            assignable_to=[TagAssignmentScope.DATABASE],
        )
        policy.group("dataconsumer", reader().where(domain="sales"))

        with self.assertRaisesRegex(ValueError, "undefined tag key"):
            policy.validate()

    def test_to_desired_state_generates_table_creator_grants_that_lint_without_errors(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            values=["sales", "finance"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.group("dataengineer", table_creator().where(domain="sales"))
        policy.bind_role("arn:aws:iam::111122223333:role/DataEngineer", "dataengineer")

        desired = policy.to_desired_state()
        findings = lint_desired(desired)
        finding_codes = {finding.code for finding in findings}

        self.assertEqual([grant.permissions for grant in desired.grants], [
            ("CREATE_TABLE", "DESCRIBE"),
            ("DELETE", "DESCRIBE", "INSERT", "SELECT"),
        ])
        self.assertNotIn("MUTATING_PERMISSION_REVIEW", finding_codes)
        self.assertNotIn("LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT", finding_codes)
        self.assertNotIn("LF_TAG_POLICY_COMBINED_TABLE_SELECT_MUTATION_CONFLICT", finding_codes)

    def test_to_desired_state_generates_producer_grants_that_lint_without_errors(self):
        policy = LakePolicy()
        policy.tag_key(
            "domain",
            values=["sales", "finance"],
            assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
        )
        policy.group("producer", producer().where(domain="sales"))
        policy.bind_role("arn:aws:iam::111122223333:role/Producer", "producer")

        desired = policy.to_desired_state()
        findings = lint_desired(desired)

        self.assertEqual(
            [grant.permissions for grant in desired.grants],
            [
                ("CREATE_TABLE", "DESCRIBE"),
                ("DELETE", "DESCRIBE", "INSERT", "SELECT"),
            ],
        )
        self.assertFalse(findings)

    def test_to_desired_state_generates_database_creator_catalog_grant(self):
        policy = LakePolicy()
        policy.group("catalog_admin", database_creator(catalog_id="111111111111"))
        policy.bind_role(
            "arn:aws:iam::111122223333:role/CatalogAdmin",
            "catalog_admin",
        )

        desired = policy.to_desired_state()

        self.assertEqual(len(desired.grants), 1)
        self.assertEqual(desired.grants[0].resource.kind, "catalog")
        self.assertEqual(desired.grants[0].resource.catalog_id, "111111111111")
        self.assertEqual(desired.grants[0].permissions, ("CREATE_DATABASE",))

    def test_to_desired_state_generates_direct_bundle_grants(self):
        policy = LakePolicy()
        policy.group("steward", steward("sales_tables", catalog_id="111111111111"))
        policy.group("location", data_location_access("arn:aws:s3:::analytics-lake/raw/"))
        policy.group("admin", admin(catalog_id="111111111111"))
        policy.bind_role(
            "arn:aws:iam::111122223333:role/DataSteward",
            ["steward", "location", "admin"],
        )

        desired = policy.to_desired_state()
        grants = {grant.resource.kind: grant for grant in desired.grants}

        self.assertEqual(
            grants["lf_tag_expression"].resource.to_dict(),
            {
                "kind": "lf_tag_expression",
                "catalog_id": "111111111111",
                "expression_name": "sales_tables",
            },
        )
        self.assertEqual(
            grants["lf_tag_expression"].permissions,
            ("DESCRIBE", "GRANT_WITH_LF_TAG_EXPRESSION"),
        )
        self.assertEqual(grants["data_location"].permissions, ("DATA_LOCATION_ACCESS",))
        self.assertEqual(
            grants["catalog"].permissions,
            ("CREATE_DATABASE", "CREATE_LF_TAG", "CREATE_LF_TAG_EXPRESSION", "DESCRIBE"),
        )
        self.assertFalse(lint_desired(desired))

    def test_direct_bundle_rejects_tag_filters(self):
        policy = LakePolicy()
        policy.group("location", data_location_access("arn:aws:s3:::analytics-lake/raw/").where(domain="sales"))

        with self.assertRaisesRegex(ValueError, "cannot use LF-Tag filters"):
            policy.validate()

    def test_write_desired_writes_json(self):
        policy = LakePolicy()
        policy.tag_key("domain", values=["sales"], assignable_to=[TagAssignmentScope.DATABASE])
        policy.group("dataconsumer", reader().where(domain="sales"))
        policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "desired.json"
            policy.write_desired(output_path)
            payload = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(payload["lf_tags"], {"domain": ["sales"]})
        self.assertEqual(payload["lf_tag_key_metadata"]["domain"]["assignable_to"], ["database"])

    def test_load_policy_loads_object_from_python_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            policy_path = Path(tmp) / "policy.py"
            policy_path.write_text(
                """from lakeformation_guard.policy import LakePolicy, TagAssignmentScope, reader

policy = LakePolicy()
policy.tag_key("domain", values=["sales"], assignable_to=[TagAssignmentScope.DATABASE])
policy.group("dataconsumer", reader().where(domain="sales"))
policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")
""",
                encoding="utf-8",
            )

            policy = load_policy(policy_path)

        self.assertEqual(policy.groups[0].name, "dataconsumer")

    def test_templates_are_named_for_user_defined_groups(self):
        self.assertEqual(reader().permission_template, PermissionTemplate.READER)
        self.assertEqual(editor().permission_template, PermissionTemplate.EDITOR)
        self.assertEqual(producer().permission_template, PermissionTemplate.PRODUCER)
        self.assertEqual(
            table_creator().permission_template,
            PermissionTemplate.TABLE_CREATOR,
        )
        self.assertEqual(
            database_creator().permission_template,
            PermissionTemplate.DATABASE_CREATOR,
        )
        self.assertEqual(
            steward("sales_tables").permission_template,
            PermissionTemplate.STEWARD,
        )
        self.assertEqual(admin().permission_template, PermissionTemplate.ADMIN)
        self.assertEqual(
            data_location_access("arn:aws:s3:::analytics-lake/raw/").permission_template,
            PermissionTemplate.DATA_LOCATION_ACCESS,
        )

    def test_ambiguous_creator_template_is_not_public_api(self):
        self.assertFalse(hasattr(lakeformation_guard, "creator"))
        self.assertNotIn("creator", lakeformation_guard.__all__)
        self.assertEqual(
            PermissionTemplate("table_creator"),
            PermissionTemplate.TABLE_CREATOR,
        )
        with self.assertRaises(ValueError):
            PermissionTemplate("creator")

    def test_metadata_keeps_raw_lint_conservative_without_metadata(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "grants": [
                    {
                        "principal": "arn:aws:iam::111122223333:role/DataEngineer",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"]},
                        },
                        "permissions": ["SELECT", "INSERT"],
                    }
                ],
            }
        )

        self.assertIn(
            "LF_TAG_POLICY_TABLE_SELECT_MUTATION_CONFLICT",
            {finding.code for finding in lint_desired(desired)},
        )

    def test_lint_rejects_resource_tag_outside_declared_assignment_scope(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "lf_tag_key_metadata": {
                    "domain": {"assignable_to": ["database", "table"]}
                },
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table_with_columns",
                            "database": "sales_curated",
                            "table": "customers",
                            "columns": ["phone_number"],
                        },
                        "tags": {"domain": ["sales"]},
                    }
                ],
            }
        )

        self.assertIn(
            "RESOURCE_TAG_SCOPE_UNSUPPORTED",
            {finding.code for finding in lint_desired(desired)},
        )

    def test_lint_rejects_resource_tags_on_unsupported_resource_kind(self):
        desired = DesiredState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "resource_tags": [
                    {
                        "resource": {"kind": "data_location", "location": "s3://lake/sales/"},
                        "tags": {"domain": ["sales"]},
                    }
                ],
            }
        )

        self.assertIn(
            "RESOURCE_TAG_KIND_UNSUPPORTED",
            {finding.code for finding in lint_desired(desired)},
        )


def _define_common_tags(policy: LakePolicy) -> None:
    policy.tag_key(
        "domain",
        values=["sales", "finance"],
        assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
    )
    policy.tag_key(
        "contains_pii",
        values=["false", "true"],
        assignable_to=[
            TagAssignmentScope.DATABASE,
            TagAssignmentScope.TABLE,
            TagAssignmentScope.COLUMN,
        ],
    )


if __name__ == "__main__":
    unittest.main()
