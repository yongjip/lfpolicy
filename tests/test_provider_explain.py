import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from lakeformation_guard import (
    CachedCurrentStateProvider,
    CurrentState,
    DesiredState,
    LazyCurrentStateProvider,
    ResourceRef,
    SnapshotCurrentStateProvider,
    SnapshotFileCurrentStateProvider,
    aws_current_state_provider_context,
    desired_state_fingerprint,
    explain,
    lint_desired,
    provider_context_fingerprint,
)
from lakeformation_guard.cli import main
from lakeformation_guard.provider import CURRENT_STATE_CACHE_SCHEMA_VERSION


class FakeCurrentStateProvider:
    def __init__(self, current):
        self.current = current
        self.calls = []

    def load_current_state_for(self, desired):
        self.calls.append(desired)
        return self.current


class ProviderExplainTests(unittest.TestCase):
    def test_snapshot_providers_return_current_state(self):
        current = CurrentState.from_dict(
            {
                "lf_tags": {"domain": ["sales"]},
                "grants": [],
            }
        )

        provider = SnapshotCurrentStateProvider(current)
        self.assertEqual(provider.load_current_state_for(DesiredState.empty()), current)

        with tempfile.TemporaryDirectory() as tmp:
            snapshot_path = Path(tmp) / "current.json"
            snapshot_path.write_text(json.dumps(current.to_dict()), encoding="utf-8")
            file_provider = SnapshotFileCurrentStateProvider(str(snapshot_path))

            loaded = file_provider.load_current_state_for(DesiredState.empty())

        self.assertEqual(loaded, current)

    def test_lazy_provider_defers_factory_until_load(self):
        current = CurrentState.from_dict({"grants": []})
        calls = []

        def factory():
            calls.append("called")
            return FakeCurrentStateProvider(current)

        provider = LazyCurrentStateProvider(factory)

        self.assertEqual(calls, [])
        self.assertEqual(provider.load_current_state_for(DesiredState.empty()), current)
        self.assertEqual(calls, ["called"])

    def test_cached_provider_writes_and_reuses_current_state_cache(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "current-cache.json"
            upstream = FakeCurrentStateProvider(current)
            provider = CachedCurrentStateProvider(upstream, str(cache_path), clock=lambda: 1000.0)

            self.assertEqual(provider.load_current_state_for(desired), current)
            self.assertEqual(len(upstream.calls), 1)

            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(envelope["schema_version"], CURRENT_STATE_CACHE_SCHEMA_VERSION)
            self.assertEqual(envelope["desired_fingerprint"], desired_state_fingerprint(desired))
            self.assertEqual(envelope["provider_fingerprint"], provider_context_fingerprint({}))
            self.assertEqual(envelope["provider_context"], {})
            self.assertEqual(envelope["created_at"], "1970-01-01T00:16:40Z")

            second_upstream = FakeCurrentStateProvider(CurrentState.empty())
            cached_provider = CachedCurrentStateProvider(second_upstream, str(cache_path), clock=lambda: 1001.0)

            self.assertEqual(cached_provider.load_current_state_for(desired), current)
            self.assertEqual(second_upstream.calls, [])

    def test_cached_provider_for_aws_records_context(self):
        desired = DesiredState.from_dict({"grants": []})
        current = CurrentState.empty()

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "current-cache.json"
            provider = CachedCurrentStateProvider.for_aws(
                FakeCurrentStateProvider(current),
                str(cache_path),
                profile_name="prod",
                region_name="us-east-1",
                catalog_id="111122223333",
            )

            self.assertEqual(provider.load_current_state_for(desired), current)
            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(
                envelope["provider_context"],
                {
                    "catalog_id": "111122223333",
                    "profile": "prod",
                    "provider": "aws-lakeformation",
                    "region": "us-east-1",
                },
            )

    def test_aws_current_state_provider_context_uses_explicit_environment_and_defaults(self):
        self.assertEqual(
            aws_current_state_provider_context(
                profile_name="prod",
                region_name="us-east-1",
                catalog_id="111122223333",
                environ={
                    "AWS_PROFILE": "stage",
                    "AWS_REGION": "us-west-2",
                },
            ),
            {
                "catalog_id": "111122223333",
                "profile": "prod",
                "provider": "aws-lakeformation",
                "region": "us-east-1",
            },
        )
        self.assertEqual(
            aws_current_state_provider_context(
                environ={
                    "AWS_DEFAULT_PROFILE": "stage-default",
                    "AWS_DEFAULT_REGION": "us-west-2",
                },
            ),
            {
                "catalog_id": None,
                "profile": "stage-default",
                "provider": "aws-lakeformation",
                "region": "us-west-2",
            },
        )
        self.assertEqual(
            aws_current_state_provider_context(environ={}),
            {
                "catalog_id": None,
                "profile": "__default__",
                "provider": "aws-lakeformation",
                "region": "__default__",
            },
        )

    def test_cached_provider_does_not_use_fixed_temp_path(self):
        desired = DesiredState.from_dict({"grants": []})
        current = CurrentState.empty()

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "current-cache.json"
            fixed_tmp_path = Path(tmp) / "current-cache.json.tmp"
            fixed_tmp_path.write_text("sentinel", encoding="utf-8")

            provider = CachedCurrentStateProvider(FakeCurrentStateProvider(current), str(cache_path))
            self.assertEqual(provider.load_current_state_for(desired), current)

            self.assertEqual(fixed_tmp_path.read_text(encoding="utf-8"), "sentinel")
            self.assertEqual(json.loads(cache_path.read_text(encoding="utf-8"))["current"], current.to_dict())

    def test_cached_provider_refreshes_on_scope_or_provider_context_mismatch_or_expiry(self):
        desired = DesiredState.from_dict({"grants": []})
        different_desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "database", "database": "analytics"},
                        "permissions": ["DESCRIBE"],
                    }
                ]
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "current-cache.json"
            CachedCurrentStateProvider(
                FakeCurrentStateProvider(CurrentState.empty()),
                str(cache_path),
                clock=lambda: 1000.0,
            ).load_current_state_for(different_desired)

            mismatch_upstream = FakeCurrentStateProvider(current)
            mismatch_provider = CachedCurrentStateProvider(mismatch_upstream, str(cache_path), clock=lambda: 1001.0)

            self.assertEqual(mismatch_provider.load_current_state_for(desired), current)
            self.assertEqual(len(mismatch_upstream.calls), 1)

            context_upstream = FakeCurrentStateProvider(CurrentState.empty())
            context_provider = CachedCurrentStateProvider(
                context_upstream,
                str(cache_path),
                provider_context={
                    "provider": "aws-lakeformation",
                    "profile": "prod",
                    "region": "us-east-1",
                    "catalog_id": "111122223333",
                },
                clock=lambda: 1002.0,
            )

            self.assertEqual(context_provider.load_current_state_for(desired), CurrentState.empty())
            self.assertEqual(len(context_upstream.calls), 1)
            context_envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(
                context_envelope["provider_context"],
                {
                    "catalog_id": "111122223333",
                    "profile": "prod",
                    "provider": "aws-lakeformation",
                    "region": "us-east-1",
                },
            )

            expired_upstream = FakeCurrentStateProvider(CurrentState.empty())
            expired_provider = CachedCurrentStateProvider(
                expired_upstream,
                str(cache_path),
                max_age_seconds=1,
                provider_context={
                    "provider": "aws-lakeformation",
                    "profile": "prod",
                    "region": "us-east-1",
                    "catalog_id": "111122223333",
                },
                clock=lambda: 1004.0,
            )

            self.assertEqual(expired_provider.load_current_state_for(desired), CurrentState.empty())
            self.assertEqual(len(expired_upstream.calls), 1)

    def test_explain_reports_direct_table_grant_and_effective_tags(self):
        desired = DesiredState.empty()
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "database", "database": "analytics"},
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            desired,
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.effective_lf_tags["domain"], ("sales",))
        self.assertEqual(report.effective_lf_tags["sensitivity"], ("internal",))
        self.assertEqual(report.findings[0].source, "direct_grant")
        self.assertEqual(report.findings[0].id, "finding_001")

    def test_explain_column_tag_overrides_inherited_same_key_for_selected_column(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "database", "database": "analytics"},
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    },
                    {
                        "resource": {
                            "kind": "table_with_columns",
                            "database": "analytics",
                            "table": "orders",
                            "columns": ["email"],
                        },
                        "tags": {"sensitivity": ["restricted"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    },
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"], "sensitivity": ["internal"]},
                        },
                        "permissions": ["SELECT"],
                    },
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="table_with_columns",
                database_name="analytics",
                table_name="orders",
                columns=("email",),
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.effective_lf_tags, {"domain": ("sales",), "sensitivity": ("restricted",)})
        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.summary()["not_matched"], 1)
        findings_by_source = {finding.source: finding for finding in report.findings}
        self.assertEqual(set(findings_by_source), {"direct_grant", "lf_tag_policy"})
        self.assertEqual(findings_by_source["direct_grant"].status, "matched")
        self.assertEqual(findings_by_source["lf_tag_policy"].status, "not_matched")
        self.assertEqual(
            findings_by_source["lf_tag_policy"].details["mismatched_values"],
            [{"key": "sensitivity", "expected": ["internal"], "actual": ["restricted"]}],
        )
        self.assertTrue(any("Column LF-Tags" in note for note in report.notes))

    def test_explain_column_tag_adds_different_key_to_inherited_tags(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {
                            "kind": "table_with_columns",
                            "database": "analytics",
                            "table": "orders",
                            "columns": ["email"],
                        },
                        "tags": {"sensitivity": ["restricted"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"], "sensitivity": ["restricted"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="table_with_columns",
                database_name="analytics",
                table_name="orders",
                columns=("email",),
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.effective_lf_tags, {"domain": ("sales",), "sensitivity": ("restricted",)})
        self.assertEqual(report.summary()["matched"], 1)

    def test_explain_column_wildcard_grant_covers_non_excluded_columns(self):
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "table_with_columns",
                            "database": "analytics",
                            "table": "orders",
                            "column_wildcard": True,
                            "excluded_columns": ["internal_notes"],
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        covered_report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="table_with_columns",
                database_name="analytics",
                table_name="orders",
                columns=("email",),
            ),
            permissions=("SELECT",),
        )
        excluded_report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="table_with_columns",
                database_name="analytics",
                table_name="orders",
                columns=("internal_notes",),
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(covered_report.summary()["matched"], 1)
        self.assertEqual(covered_report.findings[0].details["column_wildcard"], True)
        self.assertEqual(excluded_report.summary()["not_matched"], 1)
        self.assertEqual(excluded_report.findings[0].details["missing_columns"], ["internal_notes"])

    def test_explain_aggregates_effective_tags_across_requested_columns(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    },
                    {
                        "resource": {
                            "kind": "table_with_columns",
                            "database": "analytics",
                            "table": "orders",
                            "columns": ["email"],
                        },
                        "tags": {"sensitivity": ["restricted"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"sensitivity": ["internal", "restricted"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="table_with_columns",
                database_name="analytics",
                table_name="orders",
                columns=("amount", "email"),
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.effective_lf_tags, {"sensitivity": ("internal", "restricted")})
        self.assertEqual(report.summary()["matched"], 1)

    def test_explain_reports_data_cells_filter_grant_for_target_table(self):
        current = CurrentState.from_dict(
            {
                "data_cells_filters": [
                    {
                        "name": "orders_public",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "row_filter": "country = 'US'",
                        "columns": ["order_id", "status"],
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="table",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].resource.kind, "data_cells_filter")
        self.assertEqual(report.findings[0].details["filter_name"], "orders_public")
        self.assertEqual(
            report.findings[0].details["data_cells_filter"]["row_filter"],
            "country = 'US'",
        )
        self.assertIn("row/column restrictions", report.findings[0].message)

    def test_explain_includes_target_data_cells_filter_definition(self):
        current = CurrentState.from_dict(
            {
                "data_cells_filters": [
                    {
                        "name": "orders_public",
                        "catalog_id": "222222222222",
                        "database": "analytics",
                        "table": "orders",
                        "all_rows": True,
                        "excluded_columns": ["notes"],
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="data_cells_filter",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
                filter_name="orders_public",
            ),
            permissions=("SELECT",),
        )
        payload = report.to_dict()

        self.assertEqual(payload["data_cells_filter"]["name"], "orders_public")
        self.assertEqual(payload["data_cells_filter"]["excluded_columns"], ["notes"])
        self.assertEqual(payload["findings"][0]["details"]["data_cells_filter"]["all_rows"], True)

    def test_explain_does_not_match_different_data_cells_filter_target(self):
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="data_cells_filter",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
                filter_name="orders_private",
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 0)
        self.assertEqual(report.summary()["not_matched"], 1)
        self.assertEqual(report.findings[0].details["grant_filter_name"], "orders_public")
        self.assertEqual(report.findings[0].details["requested_filter_name"], "orders_private")

    def test_explain_reports_table_grant_for_data_cells_filter_target(self):
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="data_cells_filter",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
                filter_name="orders_public",
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].resource.kind, "table")
        self.assertIn("Table-level grant covers", report.findings[0].message)

    def test_explain_ignores_catalog_grant_for_different_target_catalog(self):
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "catalog", "catalog_id": "111111111111"},
                        "permissions": ["CREATE_DATABASE"],
                    }
                ]
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="database", database_name="analytics", catalog_id="222222222222"),
        )

        self.assertEqual(report.summary()["context"], 0)
        self.assertEqual(report.findings, ())

    def test_explain_reports_catalog_grant_context_for_same_target_catalog(self):
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "catalog", "catalog_id": "111111111111"},
                        "permissions": ["CREATE_DATABASE"],
                    }
                ]
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="database", database_name="analytics", catalog_id="111111111111"),
        )

        self.assertEqual(report.summary()["context"], 1)
        self.assertEqual(report.findings[0].resource.catalog_id, "111111111111")

    def test_explain_reports_data_location_context_for_table_target(self):
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "data_location",
                            "location": "arn:aws:s3:::analytics-lake/raw/",
                        },
                        "permissions": ["DATA_LOCATION_ACCESS"],
                    }
                ]
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
        )

        self.assertEqual(report.summary()["context"], 1)
        self.assertEqual(report.findings[0].source, "data_location_grant")
        self.assertIn("table storage locations are not modeled", report.findings[0].message)

    def test_explain_uses_target_catalog_for_effective_lf_tags(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "111111111111",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["finance"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "222222222222",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["finance"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="table",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.effective_lf_tags, {"domain": ("finance",)})
        self.assertEqual(report.summary()["matched"], 1)

    def test_explain_uses_grant_catalog_for_unscoped_lf_tag_policy_target(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "111111111111",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["finance"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "222222222222",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["finance"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.effective_lf_tags, {"domain": ("finance", "sales")})
        self.assertEqual(
            report.effective_lf_tags_by_catalog,
            {
                "111111111111": {"domain": ("sales",)},
                "222222222222": {"domain": ("finance",)},
            },
        )
        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].details["effective_lf_tags_catalog_id"], "222222222222")
        self.assertEqual(report.findings[0].details["effective_lf_tags"], {"domain": ["finance"]})
        self.assertTrue(any("multiple catalogs" in note for note in report.notes))
        self.assertEqual(
            report.to_dict()["effective_lf_tags_by_catalog"],
            [
                {"catalog_id": "111111111111", "lf_tags": {"domain": ["sales"]}},
                {"catalog_id": "222222222222", "lf_tags": {"domain": ["finance"]}},
            ],
        )

    def test_explain_marks_unscoped_lf_tag_policy_ambiguous_across_catalogs(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "111111111111",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["finance"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["sales"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["not_matched"], 1)
        self.assertEqual(
            report.findings[0].details["ambiguous_catalog_ids"],
            ["111111111111", "222222222222"],
        )
        self.assertIn("specify catalog_id", report.findings[0].message)

    def test_explain_resolves_named_lf_tag_expression_grant(self):
        current = CurrentState.from_dict(
            {
                "lf_tag_expressions": {
                    "sales_tables": {"expression": {"domain": ["sales"], "sensitivity": ["internal"]}}
                },
                "resource_tags": [
                    {
                        "resource": {"kind": "database", "database": "analytics"},
                        "tags": {"domain": ["sales"]},
                    },
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"sensitivity": ["internal"]},
                    },
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression_name": "sales_tables",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].source, "named_lf_tag_policy")
        self.assertIn("sales_tables", report.findings[0].message)

    def test_explain_resolves_named_lf_tag_expression_by_catalog_id(self):
        current = CurrentState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["finance"]},
                    },
                    {
                        "name": "shared",
                        "catalog_id": "222222222222",
                        "expression": {"domain": ["sales"]},
                    },
                ],
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"domain": ["sales"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "catalog_id": "222222222222",
                            "resource_type": "TABLE",
                            "expression_name": "shared",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].details["expression_name"], "shared")

    def test_explain_resolves_unscoped_named_lf_tag_expression_to_single_scoped_definition(self):
        state = {
            "lf_tags": {"domain": ["sales"]},
            "lf_tag_expressions": [
                {
                    "name": "shared",
                    "catalog_id": "222222222222",
                    "expression": {"domain": ["sales"]},
                }
            ],
            "resource_tags": [
                {
                    "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                    "tags": {"domain": ["sales"]},
                }
            ],
            "grants": [
                {
                    "principal": "role",
                    "resource": {
                        "kind": "lf_tag_policy",
                        "resource_type": "TABLE",
                        "expression_name": "shared",
                    },
                    "permissions": ["SELECT"],
                }
            ],
        }
        desired = DesiredState.from_dict(state)
        current = CurrentState.from_dict(state)

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(lint_desired(desired), ())
        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.findings[0].details["expression"], {"domain": ["sales"]})

    def test_explain_does_not_resolve_named_expression_from_different_target_catalog(self):
        current = CurrentState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["sales"]},
                    }
                ],
                "resource_tags": [
                    {
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "tags": {"domain": ["sales"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression_name": "shared",
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(
                kind="table",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["not_matched"], 1)
        self.assertEqual(
            report.findings[0].message,
            "Named LF-Tag expression definition is missing from current state.",
        )
        self.assertEqual(report.findings[0].details["expression_catalog_id"], "222222222222")

    def test_explain_rejects_duplicate_lf_tag_expression_identity(self):
        current = CurrentState.from_dict(
            {
                "lf_tag_expressions": [
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["sales"]},
                    },
                    {
                        "name": "shared",
                        "catalog_id": "111111111111",
                        "expression": {"domain": ["finance"]},
                    },
                ]
            }
        )

        with self.assertRaisesRegex(ValueError, "Duplicate LF-Tag expression identity"):
            explain(
                DesiredState.empty(),
                current,
                principal="role",
                resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            )

    def test_explain_reports_non_matching_lf_tag_policy_conditions(self):
        current = CurrentState.from_dict(
            {
                "resource_tags": [
                    {
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "tags": {"domain": ["sales"]},
                    }
                ],
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "lf_tag_policy",
                            "resource_type": "TABLE",
                            "expression": {"domain": ["finance"]},
                        },
                        "permissions": ["SELECT"],
                    }
                ],
            }
        )

        report = explain(
            DesiredState.empty(),
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["not_matched"], 1)
        self.assertEqual(report.findings[0].details["mismatched_values"][0]["actual"], ["sales"])
        self.assertEqual(report.findings[0].details["mismatched_values"][0]["expected"], ["finance"])

    def test_explain_reports_desired_grant_missing_from_current(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.empty()

        report = explain(
            desired,
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["missing"], 1)
        self.assertEqual(report.findings[0].source, "desired_grant")

    def test_explain_treats_current_all_permission_as_covering_requested_and_desired_permissions(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["ALL"],
                    }
                ]
            }
        )

        report = explain(
            desired,
            current,
            principal="role",
            resource=ResourceRef(kind="table", database_name="analytics", table_name="orders"),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.summary()["missing"], 0)
        self.assertEqual(report.findings[0].permissions, ("ALL",))
        self.assertNotIn("missing_permissions", report.findings[0].details)

    def test_explain_does_not_mark_desired_data_cells_filter_missing_when_current_table_grant_covers_it(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        report = explain(
            desired,
            current,
            principal="role",
            resource=ResourceRef(
                kind="data_cells_filter",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
                filter_name="orders_public",
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.summary()["missing"], 0)
        self.assertEqual([finding.source for finding in report.findings], ["direct_grant"])

    def test_explain_marks_scoped_desired_grant_missing_when_current_covering_grant_is_unscoped(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "table",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        report = explain(
            desired,
            current,
            principal="role",
            resource=ResourceRef(
                kind="data_cells_filter",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
                filter_name="orders_public",
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.summary()["missing"], 1)
        self.assertEqual([finding.source for finding in report.findings], ["direct_grant", "desired_grant"])
        self.assertEqual(
            report.findings[1].details["desired_resource"]["catalog_id"],
            "222222222222",
        )

    def test_explain_still_marks_desired_table_missing_when_current_grant_is_only_filtered(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "table",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {
                            "kind": "data_cells_filter",
                            "catalog_id": "222222222222",
                            "database": "analytics",
                            "table": "orders",
                            "filter_name": "orders_public",
                        },
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        report = explain(
            desired,
            current,
            principal="role",
            resource=ResourceRef(
                kind="table",
                catalog_id="222222222222",
                database_name="analytics",
                table_name="orders",
            ),
            permissions=("SELECT",),
        )

        self.assertEqual(report.summary()["matched"], 1)
        self.assertEqual(report.summary()["missing"], 1)
        self.assertEqual(report.findings[1].source, "desired_grant")

    def test_cli_explain_uses_current_snapshot_without_aws(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(json.dumps({"grants": []}), encoding="utf-8")
            current_path.write_text(
                json.dumps(
                    {
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "permissions": ["SELECT"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter.from_boto3") as from_boto3:
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "explain",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--principal",
                            "role",
                            "--database",
                            "analytics",
                            "--table",
                            "orders",
                            "--permissions",
                            "SELECT",
                            "--output",
                            "json",
                        ]
                    )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["schema_version"], "lfguard.explain.v1")
            self.assertEqual(payload["summary"]["matched"], 1)
            self.assertEqual(payload["findings"][0]["id"], "finding_001")
            from_boto3.assert_not_called()

    def test_cli_explain_batch_outputs_json_decisions(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            current_path = tmp_path / "current.json"
            requests_path = tmp_path / "requests.json"
            current_path.write_text(
                json.dumps(
                    {
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                                "permissions": ["SELECT"],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            requests_path.write_text(
                json.dumps(
                    {
                        "requests": [
                            {
                                "id": "allowed",
                                "principal": "role",
                                "database": "analytics",
                                "table": "orders",
                                "permissions": ["SELECT"],
                            },
                            {
                                "id": "denied",
                                "principal": "other-role",
                                "database": "analytics",
                                "table": "orders",
                                "permissions": ["SELECT"],
                            },
                            {
                                "id": "missing-permission",
                                "principal": "role",
                                "database": "analytics",
                                "table": "orders",
                                "permissions": ["DESCRIBE"],
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "explain-batch",
                        "--requests",
                        str(requests_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                    ]
                )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["schema_version"], "lfguard.explain_batch.v1")
            self.assertEqual(payload["summary"], {"total": 3, "allowed": 1, "denied": 2})
            self.assertEqual(
                [(result["id"], result["decision"]) for result in payload["results"]],
                [("allowed", "allowed"), ("denied", "denied"), ("missing-permission", "denied")],
            )

            with contextlib.redirect_stdout(io.StringIO()):
                fail_exit_code = main(
                    [
                        "explain-batch",
                        "--requests",
                        str(requests_path),
                        "--current-snapshot",
                        str(current_path),
                        "--output",
                        "json",
                        "--fail-on-denied",
                    ]
                )

            self.assertEqual(fail_exit_code, 1)

    def test_cli_explain_targets_data_cells_filter_from_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(json.dumps({"grants": []}), encoding="utf-8")
            current_path.write_text(
                json.dumps(
                    {
                        "resource_tags": [
                            {
                                "resource": {
                                    "kind": "table",
                                    "catalog_id": "222222222222",
                                    "database": "analytics",
                                    "table": "orders",
                                },
                                "tags": {"domain": ["sales"]},
                            }
                        ],
                        "grants": [
                            {
                                "principal": "role",
                                "resource": {
                                    "kind": "data_cells_filter",
                                    "catalog_id": "222222222222",
                                    "database": "analytics",
                                    "table": "orders",
                                    "filter_name": "orders_public",
                                },
                                "permissions": ["SELECT"],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter.from_boto3") as from_boto3:
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "explain",
                            "--desired",
                            str(desired_path),
                            "--current-snapshot",
                            str(current_path),
                            "--principal",
                            "role",
                            "--catalog-id",
                            "222222222222",
                            "--database",
                            "analytics",
                            "--table",
                            "orders",
                            "--data-cells-filter",
                            "orders_public",
                            "--permissions",
                            "SELECT",
                            "--output",
                            "json",
                        ]
                    )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["summary"]["matched"], 1)
            self.assertEqual(payload["resource"]["kind"], "data_cells_filter")
            self.assertEqual(payload["effective_lf_tags"], {"domain": ["sales"]})
            self.assertEqual(payload["findings"][0]["resource"]["filter_name"], "orders_public")
            from_boto3.assert_not_called()

    def test_cli_plan_uses_current_cache_without_constructing_aws_adapter(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            cache_path = tmp_path / "current-cache.json"
            desired_path.write_text(json.dumps(desired.to_dict()), encoding="utf-8")
            CachedCurrentStateProvider(
                FakeCurrentStateProvider(current),
                str(cache_path),
                provider_context={
                    "provider": "aws-lakeformation",
                    "profile": "prod",
                    "region": "us-east-1",
                    "catalog_id": "111122223333",
                },
            ).load_current_state_for(desired)

            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter.from_boto3") as from_boto3:
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "plan",
                            "--desired",
                            str(desired_path),
                            "--current-cache",
                            str(cache_path),
                            "--profile",
                            "prod",
                            "--region",
                            "us-east-1",
                            "--catalog-id",
                            "111122223333",
                            "--output",
                            "json",
                        ]
                    )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["changes"], [])
            from_boto3.assert_not_called()

    def test_cli_current_cache_is_scoped_to_aws_context(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        cached_current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            cache_path = tmp_path / "current-cache.json"
            desired_path.write_text(json.dumps(desired.to_dict()), encoding="utf-8")
            CachedCurrentStateProvider(
                FakeCurrentStateProvider(cached_current),
                str(cache_path),
                provider_context={
                    "provider": "aws-lakeformation",
                    "profile": "stage",
                    "region": "us-east-1",
                    "catalog_id": "111122223333",
                },
            ).load_current_state_for(desired)

            adapter = FakeCurrentStateProvider(CurrentState.empty())
            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter.from_boto3", return_value=adapter) as from_boto3:
                with contextlib.redirect_stdout(stdout):
                    exit_code = main(
                        [
                            "plan",
                            "--desired",
                            str(desired_path),
                            "--current-cache",
                            str(cache_path),
                            "--profile",
                            "prod",
                            "--region",
                            "us-east-1",
                            "--catalog-id",
                            "111122223333",
                            "--output",
                            "json",
                        ]
                    )

            payload = json.loads(stdout.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual([change["action"] for change in payload["changes"]], ["grant.add_permissions"])
            self.assertEqual(len(adapter.calls), 1)
            from_boto3.assert_called_once_with(
                profile_name="prod",
                region_name="us-east-1",
                catalog_id="111122223333",
            )
            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(envelope["provider_context"]["profile"], "prod")

    def test_cli_plan_refreshes_current_cache_from_live_provider(self):
        desired = DesiredState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )
        current = CurrentState.from_dict(
            {
                "grants": [
                    {
                        "principal": "role",
                        "resource": {"kind": "table", "database": "analytics", "table": "orders"},
                        "permissions": ["SELECT"],
                    }
                ]
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            cache_path = tmp_path / "current-cache.json"
            desired_path.write_text(json.dumps(desired.to_dict()), encoding="utf-8")

            adapter = FakeCurrentStateProvider(current)
            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter.from_boto3", return_value=adapter) as from_boto3:
                with patch.dict(
                    "os.environ",
                    {
                        "AWS_PROFILE": "",
                        "AWS_DEFAULT_PROFILE": "",
                        "AWS_REGION": "",
                        "AWS_DEFAULT_REGION": "",
                    },
                ):
                    with contextlib.redirect_stdout(stdout):
                        exit_code = main(
                            [
                                "plan",
                                "--desired",
                                str(desired_path),
                                "--current-cache",
                                str(cache_path),
                                "--refresh-current-cache",
                                "--output",
                                "json",
                            ]
                        )

            self.assertEqual(exit_code, 0)
            self.assertEqual(json.loads(stdout.getvalue())["changes"], [])
            self.assertEqual(len(adapter.calls), 1)
            from_boto3.assert_called_once()
            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(envelope["schema_version"], CURRENT_STATE_CACHE_SCHEMA_VERSION)
            self.assertEqual(envelope["current"], current.to_dict())
            self.assertEqual(
                envelope["provider_context"],
                {
                    "catalog_id": None,
                    "profile": "__default__",
                    "provider": "aws-lakeformation",
                    "region": "__default__",
                },
            )

    def test_cli_current_cache_uses_aws_environment_context(self):
        desired = DesiredState.from_dict({"grants": []})
        current = CurrentState.empty()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            cache_path = tmp_path / "current-cache.json"
            desired_path.write_text(json.dumps(desired.to_dict()), encoding="utf-8")

            adapter = FakeCurrentStateProvider(current)
            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter.from_boto3", return_value=adapter):
                with patch.dict(
                    "os.environ",
                    {
                        "AWS_PROFILE": "stage",
                        "AWS_REGION": "us-west-2",
                        "AWS_DEFAULT_PROFILE": "default-profile",
                        "AWS_DEFAULT_REGION": "us-east-1",
                    },
                ):
                    with contextlib.redirect_stdout(stdout):
                        exit_code = main(
                            [
                                "plan",
                                "--desired",
                                str(desired_path),
                                "--current-cache",
                                str(cache_path),
                                "--refresh-current-cache",
                                "--output",
                                "json",
                            ]
                        )

            self.assertEqual(exit_code, 0)
            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(
                envelope["provider_context"],
                {
                    "catalog_id": None,
                    "profile": "stage",
                    "provider": "aws-lakeformation",
                    "region": "us-west-2",
                },
            )

    def test_cli_current_cache_explicit_context_overrides_environment(self):
        desired = DesiredState.from_dict({"grants": []})
        current = CurrentState.empty()

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            cache_path = tmp_path / "current-cache.json"
            desired_path.write_text(json.dumps(desired.to_dict()), encoding="utf-8")

            adapter = FakeCurrentStateProvider(current)
            stdout = io.StringIO()
            with patch("lakeformation_guard.cli.AWSLakeFormationAdapter.from_boto3", return_value=adapter):
                with patch.dict(
                    "os.environ",
                    {
                        "AWS_PROFILE": "stage",
                        "AWS_REGION": "us-west-2",
                    },
                ):
                    with contextlib.redirect_stdout(stdout):
                        exit_code = main(
                            [
                                "plan",
                                "--desired",
                                str(desired_path),
                                "--profile",
                                "prod",
                                "--region",
                                "us-east-1",
                                "--catalog-id",
                                "111122223333",
                                "--current-cache",
                                str(cache_path),
                                "--refresh-current-cache",
                                "--output",
                                "json",
                            ]
                        )

            self.assertEqual(exit_code, 0)
            envelope = json.loads(cache_path.read_text(encoding="utf-8"))
            self.assertEqual(
                envelope["provider_context"],
                {
                    "catalog_id": "111122223333",
                    "profile": "prod",
                    "provider": "aws-lakeformation",
                    "region": "us-east-1",
                },
            )

    def test_cli_rejects_current_cache_with_current_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            cache_path = tmp_path / "current-cache.json"
            desired_path.write_text(json.dumps({"grants": []}), encoding="utf-8")
            current_path.write_text(json.dumps({"grants": []}), encoding="utf-8")

            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                exit_code = main(
                    [
                        "plan",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--current-cache",
                        str(cache_path),
                    ]
                )

            self.assertEqual(exit_code, 2)
            self.assertIn("--current-cache cannot be combined with --current-snapshot", stderr.getvalue())

    def test_cli_explain_outputs_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            desired_path = tmp_path / "desired.json"
            current_path = tmp_path / "current.json"
            desired_path.write_text(json.dumps({"grants": []}), encoding="utf-8")
            current_path.write_text(json.dumps({"grants": []}), encoding="utf-8")

            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                exit_code = main(
                    [
                        "explain",
                        "--desired",
                        str(desired_path),
                        "--current-snapshot",
                        str(current_path),
                        "--principal",
                        "role",
                        "--database",
                        "analytics",
                        "--output",
                        "markdown",
                    ]
                )

            self.assertEqual(exit_code, 0)
            self.assertIn("### lfguard explain", stdout.getvalue())
            self.assertIn("No current or desired grants matched", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
