"""Generic permission bundle example for lfguard."""

from lakeformation_guard.policy import (
    LakePolicy,
    TagAssignmentScope,
    admin,
    data_location_access,
    producer,
    reader,
    steward,
)


policy = LakePolicy()

policy.tag_key(
    "domain",
    values=["sales", "platform"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
)
policy.tag_key(
    "sensitivity",
    values=["public", "internal"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
)

policy.group("readers", reader().where(domain="sales", sensitivity="public"))
policy.group("producers", producer().where(domain="sales"))
policy.group("tag_stewards", steward("sales_tables"))
policy.group("ingest_locations", data_location_access("arn:aws:s3:::analytics-lake/raw/"))
policy.group("platform_admins", admin())

policy.bind_role("arn:aws:iam::111122223333:role/Analyst", "readers")
policy.bind_role("arn:aws:iam::111122223333:role/Producer", ["producers", "ingest_locations"])
policy.bind_role("arn:aws:iam::111122223333:role/DataSteward", "tag_stewards")
policy.bind_role("arn:aws:iam::111122223333:role/PlatformAdmin", "platform_admins")
