"""Minimal Python policy builder example for lfpolicy."""

from lfpolicy.policy import (
    LakePolicy,
    TagAssignmentScope,
    database_creator,
    editor,
    reader,
    table_creator,
)


policy = LakePolicy()

policy.tag_key(
    "domain",
    values=["sales", "finance", "platform"],
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

policy.tag_database("sales_curated", domain="sales", contains_pii="false")
policy.tag_table("sales_curated", "customers", contains_pii="false")
policy.tag_columns("sales_curated", "customers", "phone_number", contains_pii="true")
policy.tag_database("platform_ops", domain="platform", contains_pii="false")
policy.tag_table("platform_ops", "jobs", contains_pii="false")

policy.group("dataconsumer", reader().where(domain="sales", contains_pii="false"))
policy.group("dataengineer", table_creator().where(domain="sales"))
policy.group("operations", editor().where(domain="platform"))
policy.group("catalog_admin", database_creator())

policy.bind_role("arn:aws:iam::111122223333:role/DataConsumer", "dataconsumer")
policy.bind_role("arn:aws:iam::111122223333:role/DataEngineer", "dataengineer")
policy.bind_role("arn:aws:iam::111122223333:role/Operations", "operations")
policy.bind_role("arn:aws:iam::111122223333:role/CatalogAdmin", "catalog_admin")
