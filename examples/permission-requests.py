"""Permission request bundle example for lfguard.

This file models approved access requests as local data and compiles them to
ordinary Lake Formation desired state. It is intentionally not an approval UI.
"""

from dataclasses import dataclass
from typing import Tuple

from lakeformation_guard.policy import (
    LakePolicy,
    TagAssignmentScope,
    data_location_access,
    producer,
    reader,
    steward,
)


@dataclass(frozen=True)
class AccessRequest:
    ticket: str
    summary: str
    requested_by: str
    principal: str
    groups: Tuple[str, ...]
    database: str
    table: str
    permissions: Tuple[str, ...]
    owner: str
    approved_by: str
    review_by: str
    evidence_prefix: str


CATALOG_ID = "111122223333"

APPROVED_REQUESTS = (
    AccessRequest(
        ticket="DATA-1042",
        summary="Finance analyst read access to curated invoice data",
        requested_by="finance-analytics",
        principal="arn:aws:iam::111122223333:role/FinanceAnalyst",
        groups=("finance_reader",),
        database="finance_curated",
        table="invoices",
        permissions=("SELECT",),
        owner="finance-analytics",
        approved_by="data-governance",
        review_by="2026-12-31",
        evidence_prefix="artifacts/requests/DATA-1042",
    ),
    AccessRequest(
        ticket="DATA-1043",
        summary="Finance producer write workflow for curated finance tables",
        requested_by="finance-platform",
        principal="arn:aws:iam::111122223333:role/FinanceProducer",
        groups=("finance_producer", "finance_raw_location"),
        database="finance_curated",
        table="invoices",
        permissions=("ALTER", "DESCRIBE", "INSERT"),
        owner="finance-platform",
        approved_by="data-governance",
        review_by="2026-12-31",
        evidence_prefix="artifacts/requests/DATA-1043",
    ),
    AccessRequest(
        ticket="DATA-1044",
        summary="Stewardship workflow for finance LF-Tag expression grants",
        requested_by="data-governance",
        principal="arn:aws:iam::111122223333:role/FinanceSteward",
        groups=("finance_steward",),
        database="finance_curated",
        table="invoices",
        permissions=("DESCRIBE", "GRANT_WITH_LF_TAG_EXPRESSION"),
        owner="data-governance",
        approved_by="data-governance",
        review_by="2026-09-30",
        evidence_prefix="artifacts/requests/DATA-1044",
    ),
)


policy = LakePolicy()

policy.tag_key(
    "domain",
    values=["finance", "sales"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
    catalog_id=CATALOG_ID,
)
policy.tag_key(
    "sensitivity",
    values=["public", "internal"],
    assignable_to=[TagAssignmentScope.DATABASE, TagAssignmentScope.TABLE],
    catalog_id=CATALOG_ID,
)

policy.tag_database("finance_curated", domain="finance", sensitivity="internal", catalog_id=CATALOG_ID)
policy.tag_table("finance_curated", "invoices", domain="finance", sensitivity="internal", catalog_id=CATALOG_ID)
policy.tag_table("finance_curated", "exchange_rates", domain="finance", sensitivity="public", catalog_id=CATALOG_ID)

policy.group("finance_reader", reader(catalog_id=CATALOG_ID).where(domain="finance", sensitivity="internal"))
policy.group("finance_producer", producer(catalog_id=CATALOG_ID).where(domain="finance"))
policy.group("finance_steward", steward("finance_tables", catalog_id=CATALOG_ID))
policy.group(
    "finance_raw_location",
    data_location_access("arn:aws:s3:::finance-lake/raw/", catalog_id=CATALOG_ID),
)

for request in APPROVED_REQUESTS:
    # Request metadata stays in this source file for PR review and evidence
    # paths. The binding is what compiles to Lake Formation desired state.
    policy.bind_role(request.principal, request.groups)
