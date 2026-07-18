"""Example migration from imported desired JSON to policy.py.

Keep the imported file as temporary evidence, then model the owned surface with
tag keys, resource tags, permission groups, and role bindings. Generate desired
state from this file and compare it with the reviewed import before deleting the
temporary scaffold.
"""

from lfpolicy.policy import (
    LakePolicy,
    TagAssignmentScope,
    data_location_access,
    producer,
    reader,
)


CATALOG_ID = "111122223333"

# Representative shape copied from an lfpolicy import scaffold. This reference is
# not used for generation; it documents what was converted into the policy below.
IMPORTED_DESIRED_REFERENCE = {
    "lf_tags": {
        "domain": ["finance"],
        "sensitivity": ["internal", "public"],
    },
    "resource_tags": [
        {
            "resource": {"kind": "database", "database": "finance_curated", "catalog_id": CATALOG_ID},
            "tags": {"domain": ["finance"], "sensitivity": ["internal"]},
        },
        {
            "resource": {
                "kind": "table",
                "database": "finance_curated",
                "table": "invoices",
                "catalog_id": CATALOG_ID,
            },
            "tags": {"domain": ["finance"], "sensitivity": ["internal"]},
        },
    ],
    "grants": [
        {
            "principal": "arn:aws:iam::111122223333:role/FinanceAnalyst",
            "resource": {
                "kind": "lf_tag_policy",
                "resource_type": "TABLE",
                "expression": {"domain": ["finance"], "sensitivity": ["internal"]},
                "catalog_id": CATALOG_ID,
            },
            "permissions": ["DESCRIBE", "SELECT"],
        }
    ],
}


policy = LakePolicy()

policy.tag_key(
    "domain",
    values=["finance"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
    catalog_id=CATALOG_ID,
)
policy.tag_key(
    "sensitivity",
    values=["internal", "public"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
    catalog_id=CATALOG_ID,
)

policy.tag_database("finance_curated", catalog_id=CATALOG_ID, domain="finance", sensitivity="internal")
policy.tag_table("finance_curated", "invoices", catalog_id=CATALOG_ID, domain="finance", sensitivity="internal")
policy.tag_table(
    "finance_curated",
    "exchange_rates",
    catalog_id=CATALOG_ID,
    domain="finance",
    sensitivity="public",
)

policy.group(
    "finance_reader",
    reader(catalog_id=CATALOG_ID).where(domain="finance", sensitivity="internal"),
)
policy.group("finance_producer", producer(catalog_id=CATALOG_ID).where(domain="finance"))
policy.group(
    "finance_raw_location",
    data_location_access("arn:aws:s3:::finance-lake/raw/", catalog_id=CATALOG_ID),
)

policy.bind_role("arn:aws:iam::111122223333:role/FinanceAnalyst", "finance_reader")
policy.bind_role(
    "arn:aws:iam::111122223333:role/FinanceProducer",
    ("finance_producer", "finance_raw_location"),
)
