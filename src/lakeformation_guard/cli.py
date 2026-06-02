"""Command line interface for lfguard."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from collections import Counter
from importlib import metadata, util
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from ._version import __version__
from .audit import AUDIT_SCHEMA_VERSION, AuditFinding, audit
from .aws import AWSLakeFormationAdapter
from .aws_permissions import (
    AWSIAMPermissionChecker,
    IAMPermissionCheckReport,
    iam_policy_actions,
    iam_policy_template,
)
from .explain import ExplainReport, explain as explain_access
from .io import StateFormatError, dumps_json, dumps_yaml, load_current, load_desired
from .lint import LintFinding, lint_desired
from .models import (
    CurrentState,
    DesiredState,
    Grant,
    GuardrailState,
    ResourceRef,
    ResourceTagAssignment,
)
from .planner import Plan, PlanOptions, plan
from .provider import (
    CachedCurrentStateProvider,
    CurrentStateProvider,
    LazyCurrentStateProvider,
    SnapshotFileCurrentStateProvider,
    aws_current_state_provider_context,
)
from .schema import state_json_schema
from .state_index import (
    data_cells_filter_index,
    duplicate_lf_tag_key_metadata_keys,
    lf_tag_expression_index,
    lf_tag_index,
    lf_tag_key_metadata_identity,
)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help(sys.stderr)
        return 2
    try:
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "generate":
            return _cmd_generate(args)
        if args.command == "sample":
            return _cmd_sample(args)
        if args.command == "bootstrap":
            return _cmd_bootstrap(args)
        if args.command == "schema":
            return _cmd_schema(args)
        if args.command == "doctor":
            return _cmd_doctor(args)
        if args.command == "permissions":
            return _cmd_permissions(args)
        if args.command == "completion":
            return _cmd_completion(args)
        if args.command == "check":
            return _cmd_check(args)
        if args.command == "plan":
            return _cmd_plan(args)
        if args.command == "explain":
            return _cmd_explain(args)
        if args.command == "audit":
            return _cmd_audit(args)
        if args.command == "lint":
            return _cmd_lint(args)
        if args.command == "summary":
            return _cmd_summary(args)
        if args.command == "validate":
            return _cmd_validate(args)
        if args.command == "snapshot":
            return _cmd_snapshot(args)
        if args.command == "import":
            return _cmd_import(args)
        if args.command == "apply":
            return _cmd_apply(args)
    except (StateFormatError, ValueError, RuntimeError) as exc:
        print("error: {}".format(exc), file=sys.stderr)
        return 2
    parser.error("unsupported command: {}".format(args.command))
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="lfguard",
        description="Audit, plan, and conservatively apply AWS Lake Formation LF-Tag guardrails.",
    )
    parser.add_argument("--version", action="version", version="lfguard {}".format(__version__))
    subparsers = parser.add_subparsers(dest="command")

    init_parser = subparsers.add_parser("init", help="Generate a starter desired-state policy file.")
    init_parser.add_argument("--output-file", help="Write starter policy to this file instead of stdout.")
    init_parser.add_argument(
        "--format",
        choices=("json", "yaml"),
        help="Starter policy output format. Defaults to the output file extension, or json for stdout.",
    )
    init_parser.add_argument(
        "--template",
        choices=("data-domain", "blank"),
        default="data-domain",
        help="Starter policy template. Defaults to data-domain.",
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists.")

    generate_parser = subparsers.add_parser("generate", help="Generate desired state from a Python policy file.")
    generate_parser.add_argument("policy_file", help="Python file that defines a LakePolicy object or factory.")
    generate_parser.add_argument(
        "--object",
        default="policy",
        help="Object or zero-argument factory name to load from the policy file. Defaults to policy.",
    )
    generate_parser.add_argument("--output-file", help="Write generated desired state to this file instead of stdout.")
    generate_parser.add_argument(
        "--format",
        choices=("json", "yaml"),
        help="Generated output format. Defaults to the output file extension, or json for stdout.",
    )
    generate_parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the output file does not match generated desired state.",
    )
    generate_parser.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists.")

    sample_parser = subparsers.add_parser("sample", help="Generate offline demo desired/current state files.")
    sample_parser.add_argument("--output-dir", required=True, help="Directory to write sample files into.")
    sample_parser.add_argument(
        "--format",
        choices=("json", "yaml", "both"),
        default="json",
        help="Sample state file format. Defaults to json.",
    )
    sample_parser.add_argument(
        "--include-ci",
        action="store_true",
        help="Also write a starter GitHub Actions workflow for the offline demo.",
    )
    sample_parser.add_argument("--force", action="store_true", help="Overwrite sample files if they already exist.")

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Create a starter lfguard policy repository layout.")
    bootstrap_parser.add_argument("--output-dir", required=True, help="Directory to write the starter layout into.")
    bootstrap_parser.add_argument(
        "--format",
        choices=("json", "yaml"),
        default="json",
        help="Desired policy file format. Defaults to json.",
    )
    bootstrap_parser.add_argument(
        "--template",
        choices=("data-domain", "blank"),
        default="data-domain",
        help="Starter policy template. Defaults to data-domain.",
    )
    bootstrap_parser.add_argument(
        "--include-live-drift",
        action="store_true",
        help="Also write a scheduled GitHub OIDC workflow for live AWS drift checks.",
    )
    bootstrap_parser.add_argument(
        "--include-code-scanning",
        action="store_true",
        help="Also write a GitHub Code Scanning workflow that uploads lfguard SARIF findings.",
    )
    bootstrap_parser.add_argument(
        "--include-review-template",
        action="store_true",
        help="Also write CODEOWNERS and a pull request checklist for policy review.",
    )
    bootstrap_parser.add_argument(
        "--include-editor-config",
        action="store_true",
        help="Also write VS Code settings for lfguard schema validation.",
    )
    bootstrap_parser.add_argument(
        "--policy-owner",
        default="@your-org/data-platform",
        help="CODEOWNERS owner for generated policy review files.",
    )
    bootstrap_parser.add_argument(
        "--aws-role-arn",
        default="arn:aws:iam::111122223333:role/LakeFormationReadOnly",
        help="AWS role ARN for generated live drift or Code Scanning workflows.",
    )
    bootstrap_parser.add_argument(
        "--aws-region",
        default="us-east-1",
        help="AWS region for generated live drift or Code Scanning workflows.",
    )
    bootstrap_parser.add_argument("--force", action="store_true", help="Overwrite bootstrap files if they already exist.")

    schema_parser = subparsers.add_parser("schema", help="Emit the JSON Schema for desired/current state files.")
    schema_parser.add_argument("--output-file", help="Write schema JSON to this file instead of stdout.")

    doctor_parser = subparsers.add_parser("doctor", help="Check local lfguard install and optional integrations.")
    _add_output_arg(doctor_parser)
    _add_report_output_file_arg(doctor_parser)
    doctor_parser.add_argument(
        "--require",
        action="append",
        choices=("aws", "yaml"),
        default=[],
        help="Fail when the named optional extra is not installed. Repeat for multiple extras.",
    )

    permissions_parser = subparsers.add_parser(
        "permissions",
        help="Emit or check starter IAM policies for live lfguard workflows.",
    )
    permissions_parser.add_argument(
        "--template",
        choices=("read-only", "additive-apply", "destructive-apply"),
        default="read-only",
        help="IAM policy template to emit. Defaults to read-only.",
    )
    permissions_parser.add_argument(
        "--include-glue-read",
        action="store_true",
        help="Include common Glue Data Catalog read permissions.",
    )
    permissions_parser.add_argument(
        "--check",
        action="store_true",
        help="Use AWS IAM simulation to check whether the selected template is allowed for the principal.",
    )
    permissions_parser.add_argument("--profile", help="AWS profile for --check.")
    permissions_parser.add_argument("--region", help="AWS region for --check.")
    permissions_parser.add_argument(
        "--principal-arn",
        help="IAM role/user ARN to simulate. Defaults to the current caller, with assumed-role ARNs normalized.",
    )
    _add_output_arg(permissions_parser, markdown=True)
    _add_report_output_file_arg(permissions_parser)

    completion_parser = subparsers.add_parser("completion", help="Emit shell completion scripts for lfguard.")
    completion_parser.add_argument(
        "--shell",
        choices=("bash", "zsh", "fish"),
        default="bash",
        help="Shell completion format to emit. Defaults to bash.",
    )
    _add_report_output_file_arg(completion_parser)

    check_parser = subparsers.add_parser("check", help="Validate and lint local policy files without AWS access.")
    check_parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file.")
    check_parser.add_argument("--current-snapshot", help="Current state JSON/YAML snapshot to also validate.")
    _add_output_arg(check_parser, markdown=True)
    _add_report_output_file_arg(check_parser)
    _add_github_summary_arg(check_parser)
    check_parser.add_argument("--fail-on-findings", action="store_true", help="Exit with status 1 when any lint finding is present.")
    check_parser.add_argument(
        "--fail-on-severity",
        choices=("any", "error"),
        default="any",
        help="Lint finding severity that triggers --fail-on-findings. Defaults to any finding.",
    )

    audit_parser = subparsers.add_parser("audit", help="Report drift between desired and current Lake Formation state.")
    _add_state_args(audit_parser)
    _add_aws_args(audit_parser)
    _add_current_cache_args(audit_parser)
    _add_output_arg(audit_parser, markdown=True, sarif=True)
    _add_report_output_file_arg(audit_parser)
    _add_github_summary_arg(audit_parser)
    audit_parser.add_argument("--fail-on-findings", action="store_true", help="Exit with status 1 when any finding is present.")
    audit_parser.add_argument(
        "--fail-on-severity",
        choices=("any", "error"),
        default="any",
        help="Finding severity that triggers --fail-on-findings. Defaults to any finding.",
    )

    validate_parser = subparsers.add_parser("validate", help="Validate desired/current state files without AWS access.")
    _add_state_args(validate_parser)
    _add_output_arg(validate_parser)
    _add_report_output_file_arg(validate_parser)

    lint_parser = subparsers.add_parser("lint", help="Check a desired policy for semantic issues without AWS access.")
    lint_parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file.")
    _add_output_arg(lint_parser, markdown=True, sarif=True)
    _add_report_output_file_arg(lint_parser)
    _add_github_summary_arg(lint_parser)
    lint_parser.add_argument("--fail-on-findings", action="store_true", help="Exit with status 1 when any lint finding is present.")
    lint_parser.add_argument(
        "--fail-on-severity",
        choices=("any", "error"),
        default="any",
        help="Lint finding severity that triggers --fail-on-findings. Defaults to any finding.",
    )

    summary_parser = subparsers.add_parser("summary", help="Summarize desired and optional current state without AWS access.")
    summary_parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file.")
    summary_parser.add_argument("--current-snapshot", help="Current state JSON/YAML snapshot.")
    _add_output_arg(summary_parser, markdown=True)
    _add_report_output_file_arg(summary_parser)
    _add_github_summary_arg(summary_parser)

    plan_parser = subparsers.add_parser("plan", help="Produce a conservative Lake Formation change plan.")
    _add_state_args(plan_parser)
    _add_aws_args(plan_parser)
    _add_current_cache_args(plan_parser)
    _add_output_arg(plan_parser, markdown=True)
    _add_report_output_file_arg(plan_parser)
    _add_github_summary_arg(plan_parser)
    _add_plan_option_args(plan_parser)
    plan_parser.add_argument("--fail-on-changes", action="store_true", help="Exit with status 1 when the plan contains any change.")

    explain_parser = subparsers.add_parser(
        "explain",
        help="Explain why a principal has or lacks access to a resource.",
    )
    explain_parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file.")
    explain_parser.add_argument(
        "--current-snapshot",
        help="Current state JSON/YAML snapshot. When omitted, live AWS state is loaded with boto3.",
    )
    _add_aws_args(explain_parser)
    _add_current_cache_args(explain_parser)
    explain_parser.add_argument("--principal", required=True, help="Lake Formation principal ARN or identifier.")
    explain_parser.add_argument("--database", help="Database name to explain.")
    explain_parser.add_argument("--table", help="Table name to explain. Requires --database.")
    explain_parser.add_argument(
        "--columns",
        help="Comma-separated columns to explain. Requires --database and --table.",
    )
    explain_parser.add_argument(
        "--data-cells-filter",
        help="Lake Formation data cells filter name to explain. Requires --database and --table.",
    )
    explain_parser.add_argument(
        "--location",
        help="S3 data location ARN/path to explain instead of a catalog resource.",
    )
    explain_parser.add_argument(
        "--permissions",
        help="Comma-separated permissions to require, such as SELECT,DESCRIBE.",
    )
    _add_output_arg(explain_parser, markdown=True)
    _add_report_output_file_arg(explain_parser)
    _add_github_summary_arg(explain_parser)

    snapshot_parser = subparsers.add_parser("snapshot", help="Export live AWS state for a desired policy scope.")
    snapshot_parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file that defines the snapshot scope.")
    _add_aws_args(snapshot_parser)
    snapshot_parser.add_argument("--output-file", help="Write snapshot JSON to this file instead of stdout.")

    import_parser = subparsers.add_parser("import", help="Import live AWS state into a starter desired-state file.")
    _add_aws_args(import_parser)
    import_parser.add_argument(
        "--include",
        default="lf-tags,lf-tag-expressions,data-cells-filters,resource-tags,grants",
        help="Comma-separated sections to import: lf-tags, lf-tag-expressions, data-cells-filters, resource-tags, grants.",
    )
    import_parser.add_argument("--output", required=True, help="Write imported desired state to this JSON/YAML file.")
    import_parser.add_argument(
        "--format",
        choices=("json", "yaml"),
        help="Imported desired-state output format. Defaults to the output extension, or json.",
    )
    import_parser.add_argument(
        "--review-notes",
        help="Write Markdown adoption review notes for the imported scaffold.",
    )
    import_parser.add_argument("--force", action="store_true", help="Overwrite the output file if it already exists.")

    apply_parser = subparsers.add_parser("apply", help="Dry-run or execute a Lake Formation change plan.")
    apply_parser.add_argument("--desired", help="Desired state JSON/YAML file.")
    apply_parser.add_argument(
        "--current-snapshot",
        help="Current state JSON/YAML snapshot. When omitted, live AWS state is loaded with boto3.",
    )
    apply_parser.add_argument("--plan", help="Saved JSON plan from lfguard plan --output json.")
    _add_aws_args(apply_parser)
    _add_current_cache_args(apply_parser)
    _add_output_arg(apply_parser, markdown=True)
    _add_report_output_file_arg(apply_parser)
    _add_github_summary_arg(apply_parser)
    _add_plan_option_args(apply_parser)
    apply_parser.add_argument("--only", help="Apply only comma-separated change IDs from the plan.")
    apply_parser.add_argument("--only-action", help="Apply only comma-separated action types from the plan.")
    apply_parser.add_argument("--max-changes", type=int, help="Fail before AWS calls when selected changes exceed this count.")
    apply_parser.add_argument(
        "--max-destructive",
        type=int,
        help="Fail before AWS calls when selected destructive changes exceed this count.",
    )
    apply_parser.add_argument("--execute", action="store_true", help="Apply the computed plan. Defaults to dry-run.")

    return parser


def _cmd_audit(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _load_current(args, desired)
    findings = audit(desired, current)
    if args.github_summary:
        _append_github_summary(_render_findings_markdown(findings))
    _emit_output(_render_findings(findings, args.output, sarif_uri=args.desired), args.output_file, label="audit report")
    if args.fail_on_findings and _should_fail_on_findings(findings, args.fail_on_severity):
        return 1
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _load_current(args, desired)
    change_plan = plan(desired, current, _plan_options(args))
    if args.github_summary:
        _append_github_summary(_render_plan_markdown(change_plan))
    _emit_output(_render_plan(change_plan, args.output), args.output_file, label="plan report")
    if change_plan.changes and args.fail_on_changes:
        return 1
    return 0


def _cmd_explain(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    resource = _explain_resource(args)
    provider_scope = _desired_with_explain_scope(desired, args.principal, resource)
    current = _current_state_provider(args).load_current_state_for(provider_scope)
    report = explain_access(
        desired,
        current,
        principal=args.principal,
        resource=resource,
        permissions=_parse_optional_csv(args.permissions),
    )
    if args.github_summary:
        _append_github_summary(_render_explain_markdown(report))
    _emit_output(_render_explain(report, args.output), args.output_file, label="explain report")
    return 0


def _cmd_lint(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    findings = lint_desired(desired)
    if args.github_summary:
        _append_github_summary(_render_lint_findings_markdown(findings))
    _emit_output(_render_lint_findings(findings, args.output, sarif_uri=args.desired), args.output_file, label="lint report")
    if args.fail_on_findings and _should_fail_on_lint_findings(findings, args.fail_on_severity):
        return 1
    return 0


def _cmd_summary(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = (
        SnapshotFileCurrentStateProvider(args.current_snapshot).load_current_state_for(desired)
        if args.current_snapshot
        else None
    )
    payload = {"desired": _state_profile(desired)}
    if current:
        payload["current_snapshot"] = _state_profile(current)
    if args.github_summary:
        _append_github_summary(_render_state_profiles_markdown(payload))
    _emit_output(_render_state_profiles(payload, args.output), args.output_file, label="summary report")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    output_format = _resolve_init_format(args.format, args.output_file)
    text = _dump_starter_desired_state(output_format, args.template)
    if args.output_file:
        output_path = Path(args.output_file)
        if output_path.exists() and not args.force:
            raise RuntimeError("{} already exists; pass --force to overwrite it".format(output_path))
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("Could not write starter policy to {}: {}".format(output_path, exc)) from exc
    else:
        print(text, end="")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    from .policy import load_policy

    if args.check and args.force:
        raise RuntimeError("--check cannot be combined with --force")
    if args.check and not args.output_file:
        raise RuntimeError("--check requires --output-file")
    output_format = _resolve_init_format(args.format, args.output_file)
    policy = load_policy(args.policy_file, object_name=args.object)
    text = _dump_desired_state(policy.to_desired_state(), output_format)
    if args.check:
        output_path = Path(args.output_file)
        try:
            current_text = output_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("Could not read generated desired state from {}: {}".format(output_path, exc)) from exc
        if current_text != text:
            print(
                "generated desired state is out of date: {}; run lfguard generate {} --output-file {} --force".format(
                    output_path,
                    args.policy_file,
                    output_path,
                ),
                file=sys.stderr,
            )
            return 1
        print("Generated desired state is up to date: {}".format(output_path))
        return 0
    if args.output_file:
        output_path = Path(args.output_file)
        if output_path.exists() and not args.force:
            raise RuntimeError("{} already exists; pass --force to overwrite it".format(output_path))
        _write_text_file(output_path, text, "generated desired state")
    else:
        print(text, end="")
    return 0


def _cmd_sample(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    files = _sample_files(
        args.format,
        include_ci=args.include_ci,
        workflow_path_prefix=_sample_workflow_path_prefix(output_dir),
    )
    existing = [output_dir / name for name in files if (output_dir / name).exists()]
    if existing and not args.force:
        raise RuntimeError(
            "{} already exists; pass --force to overwrite sample files".format(
                ", ".join(str(path) for path in existing)
            )
        )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            output_path = output_dir / name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Could not write sample files to {}: {}".format(output_dir, exc)) from exc

    print("Wrote lfguard sample files to {}.\n".format(output_dir))
    print("Run:")
    desired_name, current_name = _sample_primary_files(args.format)
    print(
        "  lfguard check --desired {}/{} --current-snapshot {}/{}".format(
            output_dir, desired_name, output_dir, current_name
        )
    )
    print("  lfguard plan --desired {}/{} --current-snapshot {}/{}".format(output_dir, desired_name, output_dir, current_name))
    if args.include_ci:
        print("\nGitHub Actions demo workflow:")
        print("  {}/.github/workflows/lfguard-demo.yml".format(output_dir))
    print("\nSee {}/README.md for more commands.".format(output_dir))
    return 0


def _cmd_bootstrap(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    files = _bootstrap_files(
        args.format,
        args.template,
        include_live_drift=args.include_live_drift,
        include_code_scanning=args.include_code_scanning,
        include_review_template=args.include_review_template,
        include_editor_config=args.include_editor_config,
        policy_owner=args.policy_owner,
        aws_role_arn=args.aws_role_arn,
        aws_region=args.aws_region,
    )
    existing = [output_dir / name for name in files if (output_dir / name).exists()]
    if existing and not args.force:
        raise RuntimeError(
            "{} already exists; pass --force to overwrite bootstrap files".format(
                ", ".join(str(path) for path in existing)
            )
        )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, text in files.items():
            output_path = output_dir / name
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Could not write bootstrap files to {}: {}".format(output_dir, exc)) from exc

    desired_name = _bootstrap_desired_name(args.format)
    print("Wrote lfguard policy bootstrap to {}.\n".format(output_dir))
    print("Review and edit:")
    print("  {}/policy.py".format(output_dir))
    print("  {}/policy/{}".format(output_dir, desired_name))
    print("\nRun:")
    print(
        "  lfguard generate {}/policy.py --output-file {}/policy/{} --force".format(
            output_dir,
            output_dir,
            desired_name,
        )
    )
    print("  lfguard check --desired {}/policy/{} --fail-on-findings".format(output_dir, desired_name))
    if args.include_live_drift:
        print("\nLive drift workflow:")
        print("  {}/.github/workflows/lfguard-live-drift.yml".format(output_dir))
    if args.include_code_scanning:
        print("\nCode Scanning workflow:")
        print("  {}/.github/workflows/lfguard-code-scanning.yml".format(output_dir))
    if args.include_review_template:
        print("\nReview files:")
        print("  {}/.github/CODEOWNERS".format(output_dir))
        print("  {}/.github/pull_request_template.md".format(output_dir))
    if args.include_editor_config:
        print("\nEditor config:")
        print("  {}/.vscode/settings.json".format(output_dir))
        if args.format == "yaml":
            print("  {}/.vscode/extensions.json".format(output_dir))
    print("\nSee {}/README.md for rollout steps.".format(output_dir))
    return 0


def _cmd_schema(args: argparse.Namespace) -> int:
    text = dumps_json(state_json_schema())
    if args.output_file:
        output_path = Path(args.output_file)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("Could not write schema to {}: {}".format(output_path, exc)) from exc
    else:
        print(text, end="")
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    report = _doctor_report(required_extras=args.require)
    _emit_output(_render_doctor(report, args.output), args.output_file, label="doctor report")
    if report["missing_required_extras"]:
        return 1
    return 0


def _cmd_permissions(args: argparse.Namespace) -> int:
    policy = _iam_policy_template(args.template, include_glue_read=args.include_glue_read)
    if args.check:
        checker = AWSIAMPermissionChecker.from_boto3(profile_name=args.profile, region_name=args.region)
        report = checker.check(
            iam_policy_actions(policy),
            template=args.template,
            include_glue_read=args.include_glue_read,
            principal_arn=args.principal_arn,
        )
        _emit_output(
            _render_permissions_check(report, args.output),
            args.output_file,
            label="permissions check",
        )
        return 0 if report.allowed else 1
    _emit_output(
        _render_iam_policy(policy, args.output, template=args.template),
        args.output_file,
        label="permissions policy",
    )
    return 0


def _cmd_completion(args: argparse.Namespace) -> int:
    _emit_output(_render_completion(args.shell), args.output_file, label="completion script")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = load_current(args.current_snapshot) if args.current_snapshot else None
    desired_summary = _state_summary(desired)
    current_summary = _state_summary(current) if current else None
    findings = lint_desired(desired)
    if args.github_summary:
        _append_github_summary(_render_check_report(desired_summary, current_summary, findings, "markdown"))
    _emit_output(
        _render_check_report(desired_summary, current_summary, findings, args.output),
        args.output_file,
        label="check report",
    )
    if args.fail_on_findings and _should_fail_on_lint_findings(findings, args.fail_on_severity):
        return 1
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = load_current(args.current_snapshot) if args.current_snapshot else None
    _validate_state_model(desired, "desired state")
    if current:
        _validate_state_model(current, "current snapshot")
    desired_summary = _state_summary(desired)
    current_summary = _state_summary(current) if current else None
    _emit_output(
        _render_validation(desired_summary, current_summary, args.output),
        args.output_file,
        label="validation report",
    )
    return 0


def _validate_state_model(state: GuardrailState, label: str) -> None:
    try:
        lf_tag_index(state.lf_tags)
        lf_tag_expression_index(state.lf_tag_expressions)
        data_cells_filter_index(state.data_cells_filters)
    except ValueError as exc:
        raise ValueError("{}: {}".format(label, exc)) from exc
    duplicate_metadata = duplicate_lf_tag_key_metadata_keys(state.lf_tag_key_metadata)
    if duplicate_metadata:
        first = duplicate_metadata[0]
        raise ValueError(
            "{}: Duplicate LF-Tag key metadata identity: {}".format(
                label,
                lf_tag_key_metadata_identity(first),
            )
        )


def _cmd_snapshot(args: argparse.Namespace) -> int:
    desired = load_desired(args.desired)
    current = _aws_adapter(args).load_current_state_for(desired)
    text = dumps_json(current.to_dict())
    if args.output_file:
        output_path = Path(args.output_file)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(text, encoding="utf-8")
        except OSError as exc:
            raise RuntimeError("Could not write snapshot to {}: {}".format(output_path, exc)) from exc
    else:
        print(text, end="")
    return 0


def _cmd_import(args: argparse.Namespace) -> int:
    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        raise RuntimeError("{} already exists; pass --force to overwrite it".format(output_path))
    review_notes_path = Path(args.review_notes) if args.review_notes else None
    if review_notes_path and review_notes_path.exists() and not args.force:
        raise RuntimeError("{} already exists; pass --force to overwrite it".format(review_notes_path))
    include = _parse_import_include(args.include)
    imported = _aws_adapter(args).import_state(include=include)
    output_format = _resolve_init_format(args.format, str(output_path))
    _write_text_file(output_path, _dump_state_data(imported.to_dict(), output_format), "imported desired state")
    print("Wrote imported desired state to {}.".format(output_path))
    if review_notes_path:
        _write_text_file(
            review_notes_path,
            _render_import_review_notes(
                imported,
                output_path=output_path,
                include=include,
                catalog_id=args.catalog_id,
            ),
            "import review notes",
        )
        print("Wrote import review notes to {}.".format(review_notes_path))
    return 0


def _cmd_apply(args: argparse.Namespace) -> int:
    change_plan = _load_apply_plan(args)
    change_plan = _filter_apply_plan(change_plan, args)
    budget_error = _apply_budget_error(change_plan, args)
    if budget_error:
        print("error: {}".format(budget_error), file=sys.stderr)
        return 1
    if not args.execute:
        if args.github_summary:
            _append_github_summary(_render_plan_markdown(change_plan, prefix="Dry run: no changes applied."))
        _emit_output(
            _render_plan(change_plan, args.output, prefix="Dry run: no changes applied."),
            args.output_file,
            label="apply report",
        )
        return 0

    _validate_destructive_allowances(change_plan, args)
    adapter = _aws_adapter(args)
    results = adapter.apply(
        change_plan,
        dry_run=False,
        allow_destructive=any(change.destructive for change in change_plan.changes),
    )
    applied_count = sum(1 for result in results if result.applied)
    if args.github_summary:
        _append_github_summary(_render_plan_markdown(change_plan, prefix="Applied {} change(s).".format(applied_count)))
    _emit_output(
        _render_apply(change_plan, results, args.output, applied_count=applied_count),
        args.output_file,
        label="apply report",
    )
    return 0


def _add_state_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--desired", required=True, help="Desired state JSON/YAML file.")
    parser.add_argument(
        "--current-snapshot",
        help="Current state JSON/YAML snapshot. When omitted, live AWS state is loaded with boto3.",
    )


def _add_aws_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--profile", help="AWS profile for live operations.")
    parser.add_argument("--region", help="AWS region for live operations.")
    parser.add_argument("--catalog-id", help="AWS Glue Data Catalog ID.")


def _add_current_cache_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--current-cache",
        help="Read/write a JSON current-state cache. Only valid when live AWS state would otherwise be loaded.",
    )
    parser.add_argument(
        "--refresh-current-cache",
        action="store_true",
        help="Refresh --current-cache from the upstream current-state provider.",
    )
    parser.add_argument(
        "--current-cache-max-age",
        type=int,
        help="Refresh --current-cache when its cached entry is older than this many seconds.",
    )


def _add_output_arg(parser: argparse.ArgumentParser, *, markdown: bool = False, sarif: bool = False) -> None:
    choices = ["text", "json"]
    if markdown:
        choices.append("markdown")
    if sarif:
        choices.append("sarif")
    parser.add_argument("--output", choices=choices, default="text", help="Output format.")


def _add_report_output_file_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--output-file", help="Write command output to this file instead of stdout.")


def _add_github_summary_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--github-summary",
        action="store_true",
        help="Append a Markdown report to $GITHUB_STEP_SUMMARY.",
    )


def _add_plan_option_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--allow-lf-tag-value-removals", action="store_true", help="Plan LF-Tag value removals.")
    parser.add_argument("--allow-lf-tag-expression-updates", action="store_true", help="Plan LF-Tag expression updates.")
    parser.add_argument("--allow-lf-tag-expression-deletes", action="store_true", help="Plan LF-Tag expression deletes.")
    parser.add_argument("--allow-data-cells-filter-updates", action="store_true", help="Plan data cells filter definition updates.")
    parser.add_argument("--allow-data-cells-filter-deletes", action="store_true", help="Plan data cells filter deletes.")
    parser.add_argument("--allow-resource-tag-removals", action="store_true", help="Plan LF-Tag assignment removals.")
    parser.add_argument("--allow-permission-revokes", action="store_true", help="Plan Lake Formation permission revokes.")


def _load_current(args: argparse.Namespace, desired: DesiredState) -> CurrentState:
    return _current_state_provider(args).load_current_state_for(desired)


def _current_state_provider(args: argparse.Namespace) -> CurrentStateProvider:
    current_cache = getattr(args, "current_cache", None)
    refresh_current_cache = bool(getattr(args, "refresh_current_cache", False))
    current_cache_max_age = getattr(args, "current_cache_max_age", None)
    if (refresh_current_cache or current_cache_max_age is not None) and not current_cache:
        raise RuntimeError("--refresh-current-cache and --current-cache-max-age require --current-cache")
    if current_cache and args.current_snapshot:
        raise RuntimeError("--current-cache cannot be combined with --current-snapshot")
    if current_cache_max_age is not None and current_cache_max_age < 0:
        raise RuntimeError("--current-cache-max-age must be >= 0")
    if args.current_snapshot:
        return SnapshotFileCurrentStateProvider(args.current_snapshot)
    if current_cache:
        return CachedCurrentStateProvider(
            LazyCurrentStateProvider(lambda: _aws_adapter(args)),
            current_cache,
            refresh=refresh_current_cache,
            max_age_seconds=current_cache_max_age,
            provider_context=aws_current_state_provider_context(
                profile_name=args.profile,
                region_name=args.region,
                catalog_id=args.catalog_id,
            ),
        )
    return _aws_adapter(args)


def _explain_resource(args: argparse.Namespace) -> ResourceRef:
    if args.location:
        if args.database or args.table or args.columns or args.data_cells_filter:
            raise RuntimeError("--location cannot be combined with --database, --table, --columns, or --data-cells-filter")
        return ResourceRef(kind="data_location", location=args.location, catalog_id=args.catalog_id)
    if not args.database:
        raise RuntimeError("explain requires --database or --location")
    if args.columns and not args.table:
        raise RuntimeError("--columns requires --table")
    if args.data_cells_filter:
        if not args.table:
            raise RuntimeError("--data-cells-filter requires --table")
        if args.columns:
            raise RuntimeError("--data-cells-filter cannot be combined with --columns")
        return ResourceRef(
            kind="data_cells_filter",
            database_name=args.database,
            table_name=args.table,
            filter_name=args.data_cells_filter,
            catalog_id=args.catalog_id,
        )
    if args.table and args.columns:
        return ResourceRef(
            kind="table_with_columns",
            database_name=args.database,
            table_name=args.table,
            columns=_parse_csv_option(args.columns, "--columns"),
            catalog_id=args.catalog_id,
        )
    if args.table:
        return ResourceRef(
            kind="table",
            database_name=args.database,
            table_name=args.table,
            catalog_id=args.catalog_id,
        )
    return ResourceRef(kind="database", database_name=args.database, catalog_id=args.catalog_id)


def _parse_optional_csv(value: Optional[str]) -> Tuple[str, ...]:
    if value is None:
        return ()
    return _parse_csv_option(value, "--permissions")


def _desired_with_explain_scope(desired: DesiredState, principal: str, resource: ResourceRef) -> DesiredState:
    resource_tags = list(desired.resource_tags)
    existing_tag_resources = {assignment.resource for assignment in resource_tags}
    for scoped_resource in _explain_resource_scope(resource):
        if scoped_resource not in existing_tag_resources:
            resource_tags.append(ResourceTagAssignment(resource=scoped_resource, tags={}))
            existing_tag_resources.add(scoped_resource)

    grants = list(desired.grants)
    existing_grants = {(grant.principal, grant.resource) for grant in grants}
    for scoped_resource in _explain_grant_scope(resource):
        key = (principal, scoped_resource)
        if key in existing_grants:
            continue
        grants.append(
            Grant(
                principal=principal,
                resource=scoped_resource,
                permissions=(_scope_permission(scoped_resource),),
            )
        )
        existing_grants.add(key)

    return DesiredState(
        lf_tags=desired.lf_tags,
        lf_tag_expressions=desired.lf_tag_expressions,
        data_cells_filters=desired.data_cells_filters,
        lf_tag_key_metadata=desired.lf_tag_key_metadata,
        resource_tags=tuple(resource_tags),
        grants=tuple(grants),
        config=desired.config,
    )


def _explain_resource_scope(resource: ResourceRef) -> Tuple[ResourceRef, ...]:
    if resource.kind == "database":
        return (resource,)
    if resource.kind == "table":
        return (_database_resource(resource), resource)
    if resource.kind in {"table_with_columns", "data_cells_filter"}:
        return (_database_resource(resource), _table_resource(resource), resource)
    return (resource,)


def _explain_grant_scope(resource: ResourceRef) -> Tuple[ResourceRef, ...]:
    if resource.kind == "table":
        return (_database_resource(resource), resource)
    if resource.kind in {"table_with_columns", "data_cells_filter"}:
        return (_database_resource(resource), _table_resource(resource), resource)
    return (resource,)


def _database_resource(resource: ResourceRef) -> ResourceRef:
    return ResourceRef(kind="database", database_name=resource.database_name, catalog_id=resource.catalog_id)


def _table_resource(resource: ResourceRef) -> ResourceRef:
    return ResourceRef(
        kind="table",
        database_name=resource.database_name,
        table_name=resource.table_name,
        catalog_id=resource.catalog_id,
    )


def _scope_permission(resource: ResourceRef) -> str:
    if resource.kind in {"table", "table_with_columns", "data_cells_filter"}:
        return "SELECT"
    if resource.kind == "data_location":
        return "DATA_LOCATION_ACCESS"
    return "DESCRIBE"


def _aws_adapter(args: argparse.Namespace) -> AWSLakeFormationAdapter:
    return AWSLakeFormationAdapter.from_boto3(
        profile_name=args.profile,
        region_name=args.region,
        catalog_id=args.catalog_id,
    )


def _plan_options(args: argparse.Namespace) -> PlanOptions:
    return PlanOptions(
        allow_lf_tag_value_removals=args.allow_lf_tag_value_removals,
        allow_lf_tag_expression_updates=args.allow_lf_tag_expression_updates,
        allow_lf_tag_expression_deletes=args.allow_lf_tag_expression_deletes,
        allow_data_cells_filter_updates=args.allow_data_cells_filter_updates,
        allow_data_cells_filter_deletes=args.allow_data_cells_filter_deletes,
        allow_resource_tag_removals=args.allow_resource_tag_removals,
        allow_permission_revokes=args.allow_permission_revokes,
    )


def _has_destructive_allowance(args: argparse.Namespace) -> bool:
    return bool(
        args.allow_lf_tag_value_removals
        or args.allow_lf_tag_expression_updates
        or args.allow_lf_tag_expression_deletes
        or args.allow_data_cells_filter_updates
        or args.allow_data_cells_filter_deletes
        or args.allow_resource_tag_removals
        or args.allow_permission_revokes
    )


def _load_apply_plan(args: argparse.Namespace) -> Plan:
    if args.plan:
        if (
            args.desired
            or args.current_snapshot
            or args.current_cache
            or args.refresh_current_cache
            or args.current_cache_max_age is not None
        ):
            raise RuntimeError(
                "--plan cannot be combined with --desired, --current-snapshot, or current cache options"
            )
        return _load_plan_file(args.plan)
    if not args.desired:
        raise RuntimeError("apply requires --desired or --plan")
    desired = load_desired(args.desired)
    current = _load_current(args, desired)
    return plan(desired, current, _plan_options(args))


def _load_plan_file(path: str) -> Plan:
    plan_path = Path(path)
    if plan_path.suffix.lower() not in {"", ".json"}:
        raise StateFormatError("{} must be a JSON plan file".format(plan_path))
    try:
        data = json.loads(plan_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StateFormatError("Could not read {}: {}".format(plan_path, exc)) from exc
    except ValueError as exc:
        raise StateFormatError("Could not parse {}: {}".format(plan_path, exc)) from exc
    if not isinstance(data, Mapping):
        raise StateFormatError("{} must contain a JSON object".format(plan_path))
    return Plan.from_dict(data)


def _filter_apply_plan(change_plan: Plan, args: argparse.Namespace) -> Plan:
    if args.only and args.only_action:
        raise RuntimeError("--only cannot be combined with --only-action")
    if args.only:
        selected_ids = _parse_csv_option(args.only, "--only")
        available_ids = {change.id for change in change_plan.changes}
        missing_ids = sorted(change_id for change_id in selected_ids if change_id not in available_ids)
        if missing_ids:
            raise RuntimeError("Unknown change id(s): {}".format(", ".join(missing_ids)))
        return Plan(tuple(change for change in change_plan.changes if change.id in selected_ids))
    if args.only_action:
        selected_actions = _parse_csv_option(args.only_action, "--only-action")
        filtered = tuple(change for change in change_plan.changes if change.action in selected_actions)
        if not filtered:
            raise RuntimeError("No changes matched --only-action")
        return Plan(filtered)
    return change_plan


def _parse_csv_option(value: str, option_name: str) -> Tuple[str, ...]:
    values = tuple(item.strip() for item in value.split(",") if item.strip())
    if not values:
        raise RuntimeError("{} requires at least one value".format(option_name))
    return values


def _apply_budget_error(change_plan: Plan, args: argparse.Namespace) -> Optional[str]:
    if args.max_changes is not None:
        if args.max_changes < 0:
            raise RuntimeError("--max-changes must be greater than or equal to 0")
        if len(change_plan.changes) > args.max_changes:
            return "selected plan has {} change(s), exceeding --max-changes {}".format(
                len(change_plan.changes),
                args.max_changes,
            )
    if args.max_destructive is not None:
        if args.max_destructive < 0:
            raise RuntimeError("--max-destructive must be greater than or equal to 0")
        destructive_count = len(change_plan.destructive_changes)
        if destructive_count > args.max_destructive:
            return "selected plan has {} destructive change(s), exceeding --max-destructive {}".format(
                destructive_count,
                args.max_destructive,
            )
    return None


def _validate_destructive_allowances(change_plan: Plan, args: argparse.Namespace) -> None:
    for change in change_plan.destructive_changes:
        required_flag = change.requires_flag
        if required_flag and not getattr(args, _flag_dest(required_flag), False):
            raise RuntimeError(
                "{} requires {} before execute".format(change.id or change.target, required_flag)
            )


def _flag_dest(flag: str) -> str:
    return flag[2:].replace("-", "_")


def _parse_import_include(raw: str) -> Tuple[str, ...]:
    supported = {"lf-tags", "lf-tag-expressions", "data-cells-filters", "resource-tags", "grants"}
    includes = tuple(item.strip() for item in raw.split(",") if item.strip())
    unsupported = sorted(set(includes) - supported)
    if unsupported:
        raise RuntimeError("Unsupported import section(s): {}".format(", ".join(unsupported)))
    if not includes:
        raise RuntimeError("--include requires at least one section")
    return includes


def _render_import_review_notes(
    imported: CurrentState,
    *,
    output_path: Path,
    include: Tuple[str, ...],
    catalog_id: Optional[str],
) -> str:
    profile = _state_profile(imported)
    lines = [
        "# lfguard Import Review Notes",
        "",
        "This file documents a reviewed import scaffold. `lfguard import` is not synchronization; the generated desired state becomes policy only after the team decides what `lfguard` owns.",
        "",
        "## Import Context",
        "",
        "- Desired scaffold: `{}`".format(output_path),
        "- Catalog ID: `{}`".format(catalog_id or "not set"),
        "- Included sections: `{}`".format(", ".join(include)),
        "",
        "## Imported Surface",
        "",
        "- LF-Tag definitions: {}".format(profile["lf_tags"]),
        "- Named LF-Tag expressions: {}".format(profile["lf_tag_expressions"]),
        "- Data cells filters: {}".format(profile["data_cells_filters"]),
        "- Resource tag assignments: {}".format(profile["resource_tags"]),
        "- Grants: {}".format(profile["grants"]),
    ]
    if profile["grant_principals"]:
        lines.extend(["- Principals: `{}`".format("`, `".join(profile["grant_principals"]))])
    if profile["grant_resource_kinds"]:
        lines.extend(
            [
                "- Grant resource kinds: `{}`".format(
                    "`, `".join("{}={}".format(kind, count) for kind, count in profile["grant_resource_kinds"].items())
                )
            ]
        )
    if profile["permissions"]:
        lines.extend(["- Permissions: `{}`".format("`, `".join(profile["permissions"]))])

    lines.extend(
        [
            "",
            "## Bounded Discovery Notes",
            "",
            "- Resource-tag import reads LF-Tag assignments only for resources discovered from Lake Formation grants. It does not crawl the whole Glue Data Catalog.",
            "- Data-cells-filter import lists filters only for tables discovered through imported grants. It is not a full catalog-wide filter inventory.",
            "- Grants imported here may include legacy or unmanaged access. Remove entries that should stay outside this repository, or model them with ownership and ignore rules before enforcing drift gates.",
            "",
            "## Review Checklist",
            "",
            "- [ ] Decide which principals, resource patterns, LF-Tags, and filters this repository owns.",
            "- [ ] Remove unmanaged legacy grants that should not become desired policy.",
            "- [ ] Add `ownership` and `ignore` rules before adopting mixed managed/unmanaged accounts.",
            "- [ ] Add scoped exceptions with owner, reason, expiry, and approval metadata for intentional risky grants.",
            "- [ ] Convert repeated permission patterns to `policy.py` when request volume makes raw JSON hard to maintain.",
            "- [ ] Run `lfguard check`, `summary`, `audit`, and `plan` before using apply.",
            "",
            "## Suggested Commands",
            "",
            "```bash",
            "lfguard check --desired {} --fail-on-findings".format(output_path),
            "lfguard summary --desired {} --output markdown".format(output_path),
            "lfguard plan \\",
            "  --desired {} \\".format(output_path),
            "  --current-snapshot snapshots/current.json \\",
            "  --output json \\",
            "  --output-file artifacts/lfguard-plan.json",
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def _state_summary(state: GuardrailState) -> dict:
    return {
        "lf_tags": len(state.lf_tags),
        "lf_tag_expressions": len(state.lf_tag_expressions),
        "data_cells_filters": len(state.data_cells_filters),
        "resource_tags": len(state.resource_tags),
        "grants": len(state.grants),
    }


def _state_profile(state: GuardrailState) -> dict:
    resource_kinds = Counter(assignment.resource.kind for assignment in state.resource_tags)
    grant_resource_kinds = Counter(grant.resource.kind for grant in state.grants)
    resource_tag_keys = sorted({key for assignment in state.resource_tags for key in assignment.tags})
    lf_tag_keys = [tag.key for tag in state.lf_tags]
    lf_tag_ids = [tag.identity for tag in state.lf_tags]
    permissions = sorted({permission for grant in state.grants for permission in grant.permissions})
    grantable_permissions = sorted(
        {permission for grant in state.grants for permission in grant.grantable_permissions}
    )
    return {
        "lf_tags": len(state.lf_tags),
        "lf_tag_keys": lf_tag_keys,
        "lf_tag_ids": lf_tag_ids,
        "lf_tag_values": {tag.key: list(tag.values) for tag in state.lf_tags},
        "lf_tag_values_by_id": {tag.identity: list(tag.values) for tag in state.lf_tags},
        "lf_tag_expressions": len(state.lf_tag_expressions),
        "lf_tag_expression_names": [expression.name for expression in state.lf_tag_expressions],
        "lf_tag_expression_ids": [expression.identity for expression in state.lf_tag_expressions],
        "data_cells_filters": len(state.data_cells_filters),
        "data_cells_filter_ids": [filter_definition.identity for filter_definition in state.data_cells_filters],
        "resource_tags": len(state.resource_tags),
        "resource_kinds": dict(sorted(resource_kinds.items())),
        "resource_tag_keys": resource_tag_keys,
        "grants": len(state.grants),
        "grant_principals": sorted({grant.principal for grant in state.grants}),
        "grant_resource_kinds": dict(sorted(grant_resource_kinds.items())),
        "permissions": permissions,
        "grantable_permissions": grantable_permissions,
    }


def _format_validation_summary(prefix: str, summary: dict) -> str:
    return (
        "{prefix}: {lf_tags} LF-Tag definition(s), "
        "{lf_tag_expressions} LF-Tag expression(s), "
        "{data_cells_filters} data cells filter(s), "
        "{resource_tags} resource tag assignment(s), {grants} grant(s)."
    ).format(prefix=prefix, **summary)


def _resolve_init_format(requested_format: Optional[str], output_file: Optional[str]) -> str:
    if requested_format:
        return requested_format
    if output_file and Path(output_file).suffix.lower() in {".yaml", ".yml"}:
        return "yaml"
    return "json"


def _dump_starter_desired_state(output_format: str, template: str = "data-domain") -> str:
    data = _starter_desired_state(template)
    return _dump_state_data(data, output_format)


def _dump_desired_state(desired: DesiredState, output_format: str) -> str:
    return _dump_state_data(desired.to_dict(), output_format, generated_header=True)


def _dump_state_data(data: Mapping[str, Any], output_format: str, *, generated_header: bool = False) -> str:
    if output_format == "yaml":
        header = "# Generated by policy.py. Do not edit directly.\n" if generated_header else ""
        return header + dumps_yaml(data)
    return dumps_json(data)


def _starter_permission_group_policy():
    from .policy import (
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
    return policy


def _blank_permission_group_policy():
    from .policy import LakePolicy

    return LakePolicy()


def _starter_policy_source() -> str:
    return '''"""Lake Formation permission groups for lfguard."""

from lakeformation_guard.policy import (
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
'''


def _blank_policy_source() -> str:
    return '''"""Lake Formation permission groups for lfguard."""

from lakeformation_guard.policy import LakePolicy


policy = LakePolicy()
'''


def _doctor_report(required_extras: Optional[Iterable[str]] = None) -> dict:
    report = {
        "version": __version__,
        "python": {
            "version": platform.python_version(),
            "executable": sys.executable,
        },
        "optional_dependencies": {
            "boto3": _dependency_status(
                "boto3",
                "boto3",
                extra="aws",
                purpose="live AWS snapshot and apply workflows",
            ),
            "PyYAML": _dependency_status(
                "yaml",
                "PyYAML",
                extra="yaml",
                purpose="YAML desired/current state files",
            ),
        },
        "aws_environment": {
            "profile": os.environ.get("AWS_PROFILE"),
            "region": os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION"),
            "catalog_id": os.environ.get("LF_GUARD_CATALOG_ID"),
        },
        "aws_calls_made": False,
    }
    required = tuple(sorted(set(required_extras or ())))
    report["required_extras"] = list(required)
    report["missing_required_extras"] = [
        extra for extra in required if not _optional_extra_installed(report, extra)
    ]
    return report


def _optional_extra_installed(report: dict, extra: str) -> bool:
    for status in report["optional_dependencies"].values():
        if status["extra"] == extra:
            return bool(status["installed"])
    return False


def _dependency_status(module_name: str, distribution_name: str, *, extra: str, purpose: str) -> dict:
    installed = util.find_spec(module_name) is not None
    version = None
    if installed:
        try:
            version = metadata.version(distribution_name)
        except metadata.PackageNotFoundError:
            version = None
    return {
        "installed": installed,
        "version": version,
        "extra": extra,
        "purpose": purpose,
    }


def _print_doctor(report: dict) -> None:
    print(_render_doctor(report, "text"), end="")


def _render_doctor(report: dict, output: str) -> str:
    if output == "json":
        return dumps_json(report)
    lines = [
        "lfguard: {}".format(report["version"]),
        "Python: {version} ({executable})".format(**report["python"]),
        "Optional dependencies:",
    ]
    for name, status in report["optional_dependencies"].items():
        if status["installed"]:
            suffix = " {}".format(status["version"]) if status["version"] else ""
            lines.append("- {}: installed{} ({})".format(name, suffix, status["purpose"]))
        else:
            lines.append("- {}: missing; install lfguard[{}] for {}".format(name, status["extra"], status["purpose"]))
    lines.append("AWS environment:")
    aws_env = report["aws_environment"]
    lines.append("- profile: {}".format(aws_env["profile"] or "not set"))
    lines.append("- region: {}".format(aws_env["region"] or "not set"))
    lines.append("- catalog_id: {}".format(aws_env["catalog_id"] or "not set"))
    if report["required_extras"]:
        lines.append("Required extras:")
        for extra in report["required_extras"]:
            state = "missing" if extra in report["missing_required_extras"] else "installed"
            lines.append("- {}: {}".format(extra, state))
    lines.append("No AWS calls were made.")
    return "\n".join(lines) + "\n"


def _iam_policy_template(template: str, *, include_glue_read: bool = False) -> dict:
    return iam_policy_template(template, include_glue_read=include_glue_read)


def _render_iam_policy(policy: dict, output: str, *, template: str) -> str:
    policy_json = dumps_json(policy)
    if output == "markdown":
        return "\n".join(
            [
                "### lfguard permissions: {}".format(template),
                "",
                "Review and scope this starter IAM policy before using it in production.",
                "",
                "```json",
                policy_json.rstrip(),
                "```",
                "",
            ]
        )
    return policy_json


def _render_permissions_check(report: IAMPermissionCheckReport, output: str) -> str:
    payload = report.to_dict()
    if output == "json":
        return dumps_json(payload)
    if output == "markdown":
        lines = [
            "### lfguard permissions check: {}".format(report.template),
            "",
            "- Result: **{}**".format("pass" if report.allowed else "fail"),
            "- Principal: `{}`".format(report.principal_arn),
        ]
        if report.caller_arn:
            lines.append("- Caller: `{}`".format(report.caller_arn))
        lines.extend(
            [
                "- Allowed actions: `{allowed}/{total}`".format(**payload["summary"]),
                "",
                "| Action | Decision |",
                "| --- | --- |",
            ]
        )
        for action in report.actions:
            lines.append("| {} | {} |".format(_markdown_cell(action.action), _markdown_cell(action.decision)))
        lines.append("")
        return "\n".join(lines) + "\n"

    lines = [
        "Permissions check: {}".format("pass" if report.allowed else "fail"),
        "Template: {}".format(report.template),
        "Principal: {}".format(report.principal_arn),
    ]
    if report.caller_arn:
        lines.append("Caller: {}".format(report.caller_arn))
    lines.append("Allowed actions: {allowed}/{total}".format(**payload["summary"]))
    if report.denied_actions:
        lines.append("Denied actions:")
        for action in report.denied_actions:
            lines.append("- {}".format(action))
    else:
        lines.append("All required actions are allowed.")
    return "\n".join(lines) + "\n"


_COMPLETION_COMMANDS = (
    "init",
    "generate",
    "sample",
    "bootstrap",
    "schema",
    "doctor",
    "permissions",
    "completion",
    "check",
    "validate",
    "lint",
    "summary",
    "audit",
    "plan",
    "explain",
    "snapshot",
    "import",
    "apply",
)


_COMPLETION_OPTIONS = {
    "init": ("--output-file", "--format", "--template", "--force", "--help"),
    "generate": ("--object", "--output-file", "--format", "--check", "--force", "--help"),
    "sample": ("--output-dir", "--format", "--include-ci", "--force", "--help"),
    "bootstrap": (
        "--output-dir",
        "--format",
        "--template",
        "--include-live-drift",
        "--include-code-scanning",
        "--include-review-template",
        "--include-editor-config",
        "--policy-owner",
        "--aws-role-arn",
        "--aws-region",
        "--force",
        "--help",
    ),
    "schema": ("--output-file", "--help"),
    "doctor": ("--output", "--output-file", "--require", "--help"),
    "permissions": (
        "--template",
        "--include-glue-read",
        "--check",
        "--profile",
        "--region",
        "--principal-arn",
        "--output",
        "--output-file",
        "--help",
    ),
    "completion": ("--shell", "--output-file", "--help"),
    "check": (
        "--desired",
        "--current-snapshot",
        "--output",
        "--output-file",
        "--github-summary",
        "--fail-on-findings",
        "--fail-on-severity",
        "--help",
    ),
    "validate": ("--desired", "--current-snapshot", "--output", "--output-file", "--help"),
    "lint": (
        "--desired",
        "--output",
        "--output-file",
        "--github-summary",
        "--fail-on-findings",
        "--fail-on-severity",
        "--help",
    ),
    "summary": ("--desired", "--current-snapshot", "--output", "--output-file", "--github-summary", "--help"),
    "audit": (
        "--desired",
        "--current-snapshot",
        "--profile",
        "--region",
        "--catalog-id",
        "--current-cache",
        "--refresh-current-cache",
        "--current-cache-max-age",
        "--output",
        "--output-file",
        "--github-summary",
        "--fail-on-findings",
        "--fail-on-severity",
        "--help",
    ),
    "plan": (
        "--desired",
        "--current-snapshot",
        "--profile",
        "--region",
        "--catalog-id",
        "--current-cache",
        "--refresh-current-cache",
        "--current-cache-max-age",
        "--output",
        "--output-file",
        "--github-summary",
        "--allow-lf-tag-value-removals",
        "--allow-lf-tag-expression-updates",
        "--allow-lf-tag-expression-deletes",
        "--allow-data-cells-filter-updates",
        "--allow-data-cells-filter-deletes",
        "--allow-resource-tag-removals",
        "--allow-permission-revokes",
        "--fail-on-changes",
        "--help",
    ),
    "explain": (
        "--desired",
        "--current-snapshot",
        "--profile",
        "--region",
        "--catalog-id",
        "--current-cache",
        "--refresh-current-cache",
        "--current-cache-max-age",
        "--principal",
        "--database",
        "--table",
        "--columns",
        "--data-cells-filter",
        "--location",
        "--permissions",
        "--output",
        "--output-file",
        "--github-summary",
        "--help",
    ),
    "snapshot": ("--desired", "--profile", "--region", "--catalog-id", "--output-file", "--help"),
    "import": (
        "--profile",
        "--region",
        "--catalog-id",
        "--include",
        "--output",
        "--format",
        "--review-notes",
        "--force",
        "--help",
    ),
    "apply": (
        "--desired",
        "--current-snapshot",
        "--plan",
        "--profile",
        "--region",
        "--catalog-id",
        "--current-cache",
        "--refresh-current-cache",
        "--current-cache-max-age",
        "--output",
        "--output-file",
        "--github-summary",
        "--allow-lf-tag-value-removals",
        "--allow-lf-tag-expression-updates",
        "--allow-lf-tag-expression-deletes",
        "--allow-data-cells-filter-updates",
        "--allow-data-cells-filter-deletes",
        "--allow-resource-tag-removals",
        "--allow-permission-revokes",
        "--only",
        "--only-action",
        "--max-changes",
        "--max-destructive",
        "--execute",
        "--help",
    ),
}


def _render_completion(shell: str) -> str:
    if shell == "zsh":
        return _render_zsh_completion()
    if shell == "fish":
        return _render_fish_completion()
    return _render_bash_completion()


def _completion_commands() -> str:
    return " ".join(_COMPLETION_COMMANDS)


def _completion_options(command: str) -> str:
    return " ".join(_COMPLETION_OPTIONS.get(command, ()))


def _render_bash_completion() -> str:
    lines = [
        "_lfguard_complete() {",
        "  local cur cmd commands opts",
        "  COMPREPLY=()",
        '  cur="${COMP_WORDS[COMP_CWORD]}"',
        '  commands="{}"'.format(_completion_commands()),
        '  cmd=""',
        "  for word in \"${COMP_WORDS[@]:1}\"; do",
        "    case \"$word\" in",
        "      -* ) ;;",
        "      * ) cmd=\"$word\"; break ;;",
        "    esac",
        "  done",
        '  if [[ -z "$cmd" || "$COMP_CWORD" -eq 1 ]]; then',
        '    COMPREPLY=( $(compgen -W "$commands --version --help" -- "$cur") )',
        "    return 0",
        "  fi",
        '  opts=""',
        '  case "$cmd" in',
    ]
    for command in _COMPLETION_COMMANDS:
        lines.append('    {} ) opts="{}" ;;'.format(command, _completion_options(command)))
    lines.extend(
        [
            "  esac",
            '  COMPREPLY=( $(compgen -W "$opts" -- "$cur") )',
            "  return 0",
            "}",
            "complete -F _lfguard_complete lfguard",
            "",
        ]
    )
    return "\n".join(lines)


def _render_zsh_completion() -> str:
    lines = [
        "#compdef lfguard",
        "",
        "_lfguard() {",
        "  local -a commands",
        "  commands=(",
    ]
    for command in _COMPLETION_COMMANDS:
        lines.append("    '{}:{}'".format(command, command))
    lines.extend(
        [
            "  )",
            "  _arguments -C \\",
            "    '1:command:->command' \\",
            "    '*::option:->option'",
            "  case $state in",
            "    command)",
            "      _describe 'commands' commands",
            "      ;;",
            "    option)",
            "      case $words[2] in",
        ]
    )
    for command in _COMPLETION_COMMANDS:
        options = " ".join("'{}'".format(option) for option in _COMPLETION_OPTIONS.get(command, ()))
        lines.append("        {}) compadd {} ;;".format(command, options))
    lines.extend(
        [
            "      esac",
            "      ;;",
            "  esac",
            "}",
            "",
            "_lfguard \"$@\"",
            "",
        ]
    )
    return "\n".join(lines)


def _render_fish_completion() -> str:
    lines = [
        "complete -c lfguard -f",
    ]
    for command in _COMPLETION_COMMANDS:
        lines.append("complete -c lfguard -n '__fish_use_subcommand' -a '{}'".format(command))
        for option in _COMPLETION_OPTIONS.get(command, ()):
            option_name = option[2:] if option.startswith("--") else option
            lines.append(
                "complete -c lfguard -n '__fish_seen_subcommand_from {}' -l {}".format(command, option_name)
            )
    lines.append("")
    return "\n".join(lines)


def _render_check_report(
    desired_summary: dict,
    current_summary: Optional[dict],
    findings: Iterable[LintFinding],
    output: str,
) -> str:
    findings = tuple(findings)
    lint_summary = _lint_finding_summary(findings)
    if output == "json":
        payload: Any = {
            "valid": True,
            "desired": {"valid": True, **desired_summary},
            "lint": {
                "summary": lint_summary,
                "findings": [finding.to_dict() for finding in findings],
            },
        }
        if current_summary:
            payload["current_snapshot"] = {"valid": True, **current_summary}
        return dumps_json(payload)
    if output == "markdown":
        return _render_check_report_markdown(desired_summary, current_summary, findings)

    lines = ["lfguard check {}.".format("passed" if not findings else "completed with lint findings")]
    lines.append(_format_validation_summary("Desired state is valid", desired_summary))
    if current_summary:
        lines.append(_format_validation_summary("Current snapshot is valid", current_summary))
    lint_text = _render_lint_findings(findings, "text").rstrip()
    if lint_text:
        lines.append(lint_text)
    return "\n".join(lines) + "\n"


def _render_check_report_markdown(
    desired_summary: dict,
    current_summary: Optional[dict],
    findings: Iterable[LintFinding],
) -> str:
    findings = tuple(findings)
    lint_summary = _lint_finding_summary(findings)
    lines = [
        "### lfguard check",
        "",
        "#### Validation",
        "",
        "| File | Status | LF-Tag definitions | Resource tag assignments | Grants |",
        "| --- | --- | --- | --- | --- |",
        "| desired | valid | {lf_tags} | {resource_tags} | {grants} |".format(**desired_summary),
    ]
    if current_summary:
        lines.append(
            "| current snapshot | valid | {lf_tags} | {resource_tags} | {grants} |".format(**current_summary)
        )
    lines.extend(
        [
            "",
            "#### Lint",
            "",
        ]
    )
    if not findings:
        lines.append("No lint findings.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "- Total findings: {total}".format(**lint_summary),
            "- Error findings: {errors}".format(**lint_summary),
            "- Warning findings: {warnings}".format(**lint_summary),
            "",
            "| Severity | Code | Target | Message |",
            "| --- | --- | --- | --- |",
        ]
    )
    for finding in findings:
        lines.append(
            "| {severity} | {code} | {target} | {message} |".format(
                severity=_markdown_cell(finding.severity),
                code=_markdown_cell(finding.code),
                target=_markdown_cell(finding.target),
                message=_markdown_cell(finding.message),
            )
        )
    return "\n".join(lines) + "\n"


def _render_validation(desired_summary: dict, current_summary: Optional[dict], output: str) -> str:
    if output == "json":
        payload: Any = {"desired": {"valid": True, **desired_summary}}
        if current_summary:
            payload["current_snapshot"] = {"valid": True, **current_summary}
        return dumps_json(payload)
    lines = [_format_validation_summary("Desired state is valid", desired_summary)]
    if current_summary:
        lines.append(_format_validation_summary("Current snapshot is valid", current_summary))
    return "\n".join(lines) + "\n"


def _render_lint_findings(findings: Iterable[LintFinding], output: str, *, sarif_uri: Optional[str] = None) -> str:
    findings = tuple(findings)
    summary = _lint_finding_summary(findings)
    if output == "json":
        return dumps_json(
            {
                "summary": summary,
                "findings": [finding.to_dict() for finding in findings],
            }
        )
    if output == "markdown":
        return _render_lint_findings_markdown(findings)
    if output == "sarif":
        return dumps_json(_findings_to_sarif(findings, sarif_uri=sarif_uri))
    if not findings:
        return "No lint findings.\n"
    lines = [_format_lint_finding_summary(summary)]
    for finding in findings:
        lines.append(
            "- [{severity}] {code} {target}: {message}".format(
                severity=finding.severity,
                code=finding.code,
                target=finding.target,
                message=finding.message,
            )
        )
    return "\n".join(lines) + "\n"


def _render_state_profiles(profiles: dict, output: str) -> str:
    if output == "json":
        return dumps_json(profiles)
    if output == "markdown":
        return _render_state_profiles_markdown(profiles)
    lines = []
    for name, profile in profiles.items():
        lines.append("{} summary:".format(_profile_label(name)))
        lines.extend(_render_state_profile_lines(profile))
    return "\n".join(lines) + "\n"


def _render_state_profiles_markdown(profiles: dict) -> str:
    lines = ["### lfguard summary", ""]
    for name, profile in profiles.items():
        lines.extend(
            [
                "#### {}".format(_profile_label(name)),
                "",
                "| Metric | Value |",
                "| --- | --- |",
            ]
        )
        for metric, value in _state_profile_metrics(profile):
            lines.append("| {} | {} |".format(_markdown_cell(metric), _markdown_cell(value)))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_state_profile_lines(profile: dict) -> list:
    return ["- {}: {}".format(metric, value) for metric, value in _state_profile_metrics(profile)]


def _state_profile_metrics(profile: dict) -> tuple:
    lf_tag_labels = profile["lf_tag_keys"]
    if len(lf_tag_labels) != len(set(lf_tag_labels)):
        lf_tag_labels = profile.get("lf_tag_ids", lf_tag_labels)
    return (
        ("LF-Tag definitions", _count_with_list(profile["lf_tags"], lf_tag_labels)),
        (
            "LF-Tag expressions",
            _count_with_list(
                profile["lf_tag_expressions"],
                profile.get("lf_tag_expression_ids", profile["lf_tag_expression_names"]),
            ),
        ),
        ("Data cells filters", _count_with_list(profile["data_cells_filters"], profile["data_cells_filter_ids"])),
        ("Resource tag assignments", str(profile["resource_tags"])),
        ("Resource kinds", _format_counts(profile["resource_kinds"])),
        ("Resource tag keys", _format_list(profile["resource_tag_keys"])),
        ("Grants", str(profile["grants"])),
        ("Grant principals", _format_list(profile["grant_principals"])),
        ("Grant resource kinds", _format_counts(profile["grant_resource_kinds"])),
        ("Permissions", _format_list(profile["permissions"])),
        ("Grantable permissions", _format_list(profile["grantable_permissions"])),
    )


def _profile_label(name: str) -> str:
    return name.replace("_", " ").capitalize()


def _count_with_list(count: int, values: Iterable[str]) -> str:
    rendered = _format_list(values)
    if rendered == "none":
        return str(count)
    return "{} ({})".format(count, rendered)


def _format_counts(counts: Mapping[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join("{}={}".format(key, counts[key]) for key in sorted(counts))


def _format_list(values: Iterable[str]) -> str:
    values = tuple(values)
    if not values:
        return "none"
    return ", ".join(str(value) for value in values)


def _render_lint_findings_markdown(findings: Iterable[LintFinding]) -> str:
    findings = tuple(findings)
    summary = _lint_finding_summary(findings)
    lines = ["### lfguard lint", ""]
    if not findings:
        lines.append("No lint findings.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "- Total findings: {total}".format(**summary),
            "- Error findings: {errors}".format(**summary),
            "- Warning findings: {warnings}".format(**summary),
            "",
            "| Severity | Code | Target | Message |",
            "| --- | --- | --- | --- |",
        ]
    )
    for finding in findings:
        lines.append(
            "| {severity} | {code} | {target} | {message} |".format(
                severity=_markdown_cell(finding.severity),
                code=_markdown_cell(finding.code),
                target=_markdown_cell(finding.target),
                message=_markdown_cell(finding.message),
            )
        )
    return "\n".join(lines) + "\n"


def _lint_finding_summary(findings: Iterable[LintFinding]) -> dict:
    findings = tuple(findings)
    return {
        "total": len(findings),
        "errors": sum(1 for finding in findings if finding.severity == "error"),
        "warnings": sum(1 for finding in findings if finding.severity == "warning"),
    }


def _format_lint_finding_summary(summary: dict) -> str:
    return "Lint findings: {total} total, {errors} error(s), {warnings} warning(s).".format(**summary)


def _should_fail_on_lint_findings(findings: Iterable[LintFinding], fail_on_severity: str) -> bool:
    findings = tuple(findings)
    if fail_on_severity == "error":
        return any(finding.severity == "error" for finding in findings)
    return bool(findings)


def _starter_desired_state(template: str = "data-domain") -> dict:
    if template == "blank":
        return {
            "lf_tags": {},
            "resource_tags": [],
            "grants": [],
        }
    if template != "data-domain":
        raise ValueError("unsupported starter template: {}".format(template))
    return {
        "lf_tags": {
            "domain": ["analytics"],
            "sensitivity": ["public", "internal", "restricted"],
        },
        "resource_tags": [
            {
                "resource": {
                    "kind": "table",
                    "database": "analytics",
                    "table": "orders",
                },
                "tags": {
                    "domain": ["analytics"],
                    "sensitivity": ["internal"],
                },
            }
        ],
        "grants": [
            {
                "principal": "arn:aws:iam::111122223333:role/Analyst",
                "resource": {
                    "kind": "lf_tag_policy",
                    "resource_type": "TABLE",
                    "expression": {
                        "domain": ["analytics"],
                        "sensitivity": ["public", "internal"],
                    },
                },
                "permissions": ["DESCRIBE", "SELECT"],
            }
        ],
    }


def _bootstrap_files(
    output_format: str,
    template: str,
    *,
    include_live_drift: bool = False,
    include_code_scanning: bool = False,
    include_review_template: bool = False,
    include_editor_config: bool = False,
    policy_owner: str = "@your-org/data-platform",
    aws_role_arn: str = "arn:aws:iam::111122223333:role/LakeFormationReadOnly",
    aws_region: str = "us-east-1",
) -> dict:
    desired_name = _bootstrap_desired_name(output_format)
    desired_path = "policy/{}".format(desired_name)
    needs_yaml_extra = output_format == "yaml"
    if template == "blank":
        policy_source = _blank_policy_source()
        desired_text = _dump_desired_state(
            _blank_permission_group_policy().to_desired_state(),
            output_format,
        )
    else:
        policy_source = _starter_policy_source()
        desired_text = _dump_desired_state(
            _starter_permission_group_policy().to_desired_state(),
            output_format,
        )
    files = {
        "policy.py": policy_source,
        desired_path: desired_text,
        "policy/lfguard.schema.json": dumps_json(state_json_schema()),
        ".github/workflows/lfguard-policy.yml": _bootstrap_github_actions_workflow(
            desired_path,
            needs_yaml_extra=needs_yaml_extra,
        ),
        ".pre-commit-config.yaml": _bootstrap_pre_commit_config(desired_path),
        "README.md": _bootstrap_readme(
            desired_path,
            needs_yaml_extra=needs_yaml_extra,
            include_live_drift=include_live_drift,
            include_code_scanning=include_code_scanning,
            include_review_template=include_review_template,
            include_editor_config=include_editor_config,
            policy_owner=policy_owner,
            aws_role_arn=aws_role_arn,
            aws_region=aws_region,
        ),
    }
    if include_live_drift:
        files[".github/workflows/lfguard-live-drift.yml"] = _bootstrap_live_drift_workflow(
            desired_path,
            needs_yaml_extra=needs_yaml_extra,
            aws_role_arn=aws_role_arn,
            aws_region=aws_region,
        )
        files["iam/lfguard-read-only.json"] = dumps_json(_iam_policy_template("read-only"))
    if include_code_scanning:
        files[".github/workflows/lfguard-code-scanning.yml"] = _bootstrap_code_scanning_workflow(
            desired_path,
            needs_yaml_extra=needs_yaml_extra,
            aws_role_arn=aws_role_arn,
            aws_region=aws_region,
        )
        files["iam/lfguard-read-only.json"] = dumps_json(_iam_policy_template("read-only"))
    if include_review_template:
        files[".github/CODEOWNERS"] = _bootstrap_codeowners(policy_owner)
        files[".github/pull_request_template.md"] = _bootstrap_pull_request_template(desired_path)
    if include_editor_config:
        files[".vscode/settings.json"] = _bootstrap_vscode_settings(desired_path, needs_yaml_extra=needs_yaml_extra)
        if needs_yaml_extra:
            files[".vscode/extensions.json"] = _bootstrap_vscode_extensions()
    return files


def _bootstrap_desired_name(output_format: str) -> str:
    if output_format == "yaml":
        return "desired.yaml"
    return "desired.json"


def _bootstrap_github_actions_workflow(desired_path: str, *, needs_yaml_extra: bool) -> str:
    install_target = '"lfguard[yaml]"' if needs_yaml_extra else "lfguard"
    doctor_command = "lfguard doctor --require yaml" if needs_yaml_extra else "lfguard doctor"
    return """name: lfguard policy

on:
  workflow_dispatch:
  pull_request:
    paths:
      - "{desired_path}"
      - "policy.py"
      - "policy/lfguard.schema.json"

permissions:
  contents: read

jobs:
  policy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Install lfguard
        run: python -m pip install {install_target}

      - name: Check lfguard install
        run: {doctor_command}

      - name: Check and summarize policy
        run: |
          mkdir -p artifacts
          lfguard generate policy.py --output-file {desired_path} --check

          lfguard check \\
            --desired {desired_path} \\
            --output markdown \\
            --output-file artifacts/lfguard-check.md \\
            --fail-on-findings \\
            --github-summary

          lfguard summary \\
            --desired {desired_path} \\
            --output markdown \\
            --output-file artifacts/lfguard-summary.md \\
            --github-summary

      - name: Upload lfguard reports
        if: always()
        uses: actions/upload-artifact@v6
        with:
          name: lfguard-policy-reports
          path: artifacts/
          if-no-files-found: ignore
""".format(
        desired_path=desired_path,
        doctor_command=doctor_command,
        install_target=install_target,
    )


def _bootstrap_pre_commit_config(desired_path: str) -> str:
    return """repos:
  - repo: local
    hooks:
      - id: lfguard-generate-check
        name: lfguard generate and check desired policy
        entry: bash -c 'lfguard generate policy.py --output-file {desired_path} --force && lfguard check --desired {desired_path} --fail-on-findings'
        language: system
        pass_filenames: false
        files: ^(policy\\.py|policy/desired\\.(json|ya?ml))$
""".format(
        desired_path=desired_path
    )


def _bootstrap_live_drift_workflow(
    desired_path: str,
    *,
    needs_yaml_extra: bool,
    aws_role_arn: str,
    aws_region: str,
) -> str:
    install_target = '"lfguard[aws,yaml]"' if needs_yaml_extra else '"lfguard[aws]"'
    doctor_command = "lfguard doctor --require aws --require yaml" if needs_yaml_extra else "lfguard doctor --require aws"
    return """name: lfguard live drift

on:
  workflow_dispatch:
  schedule:
    - cron: "17 * * * *"

permissions:
  contents: read
  id-token: write

jobs:
  drift:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: {aws_role_arn}
          aws-region: {aws_region}

      - name: Install lfguard
        run: python -m pip install {install_target}

      - name: Check lfguard install
        run: {doctor_command}

      - name: Validate policy before AWS access
        run: |
          mkdir -p artifacts snapshots
          lfguard generate policy.py --output-file {desired_path} --check

          lfguard check \\
            --desired {desired_path} \\
            --output markdown \\
            --output-file artifacts/lfguard-check.md \\
            --fail-on-findings \\
            --github-summary

          lfguard summary \\
            --desired {desired_path} \\
            --output markdown \\
            --output-file artifacts/lfguard-summary.md \\
            --github-summary

      - name: Capture current Lake Formation state
        run: |
          lfguard snapshot \\
            --desired {desired_path} \\
            --region {aws_region} \\
            --output-file snapshots/current.json

      - name: Audit and plan drift
        run: |
          set +e

          lfguard audit \\
            --desired {desired_path} \\
            --current-snapshot snapshots/current.json \\
            --output markdown \\
            --output-file artifacts/lfguard-audit.md \\
            --fail-on-findings \\
            --github-summary
          audit_status=$?

          set -e

          lfguard plan \\
            --desired {desired_path} \\
            --current-snapshot snapshots/current.json \\
            --output markdown \\
            --output-file artifacts/lfguard-plan.md \\
            --github-summary

          exit "$audit_status"

      - name: Upload lfguard reports
        if: always()
        uses: actions/upload-artifact@v6
        with:
          name: lfguard-live-drift-reports
          path: |
            artifacts/
            snapshots/
          if-no-files-found: ignore
          retention-days: 14
""".format(
        aws_region=aws_region,
        aws_role_arn=aws_role_arn,
        desired_path=desired_path,
        doctor_command=doctor_command,
        install_target=install_target,
    )


def _bootstrap_code_scanning_workflow(
    desired_path: str,
    *,
    needs_yaml_extra: bool,
    aws_role_arn: str,
    aws_region: str,
) -> str:
    install_target = '"lfguard[aws,yaml]"' if needs_yaml_extra else '"lfguard[aws]"'
    doctor_command = "lfguard doctor --require aws --require yaml" if needs_yaml_extra else "lfguard doctor --require aws"
    return """name: lfguard code scanning

on:
  workflow_dispatch:
  schedule:
    - cron: "31 * * * *"

permissions:
  contents: read
  id-token: write
  security-events: write

jobs:
  code-scanning:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: {aws_role_arn}
          aws-region: {aws_region}

      - name: Install lfguard
        run: python -m pip install {install_target}

      - name: Check lfguard install
        run: {doctor_command}

      - name: Generate lfguard SARIF reports
        run: |
          mkdir -p artifacts snapshots
          lfguard generate policy.py --output-file {desired_path} --check

          lfguard validate --desired {desired_path}

          lfguard lint \\
            --desired {desired_path} \\
            --output sarif \\
            --output-file artifacts/lfguard-lint.sarif

          lfguard snapshot \\
            --desired {desired_path} \\
            --region {aws_region} \\
            --output-file snapshots/current.json

          lfguard audit \\
            --desired {desired_path} \\
            --current-snapshot snapshots/current.json \\
            --output sarif \\
            --output-file artifacts/lfguard-audit.sarif

      - name: Upload lfguard lint SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: artifacts/lfguard-lint.sarif
          category: lfguard-lint

      - name: Upload lfguard audit SARIF
        uses: github/codeql-action/upload-sarif@v3
        with:
          sarif_file: artifacts/lfguard-audit.sarif
          category: lfguard-audit

      - name: Enforce lfguard gates
        run: |
          set +e

          lfguard check \\
            --desired {desired_path} \\
            --current-snapshot snapshots/current.json \\
            --output markdown \\
            --output-file artifacts/lfguard-check.md \\
            --fail-on-findings \\
            --github-summary
          check_status=$?

          lfguard audit \\
            --desired {desired_path} \\
            --current-snapshot snapshots/current.json \\
            --output markdown \\
            --output-file artifacts/lfguard-audit.md \\
            --fail-on-findings \\
            --github-summary
          audit_status=$?

          if [ "$check_status" -ne 0 ] || [ "$audit_status" -ne 0 ]; then
            exit 1
          fi

      - name: Upload lfguard reports
        if: always()
        uses: actions/upload-artifact@v6
        with:
          name: lfguard-code-scanning-reports
          path: |
            artifacts/
            snapshots/
          if-no-files-found: ignore
          retention-days: 14
""".format(
        aws_region=aws_region,
        aws_role_arn=aws_role_arn,
        desired_path=desired_path,
        doctor_command=doctor_command,
        install_target=install_target,
    )


def _bootstrap_codeowners(policy_owner: str) -> str:
    return """# Replace this placeholder with the GitHub team or user that owns Lake Formation policy.
policy/* {policy_owner}
snapshots/* {policy_owner}
iam/* {policy_owner}
.github/workflows/lfguard-*.yml {policy_owner}
""".format(
        policy_owner=policy_owner,
    )


def _bootstrap_pull_request_template(desired_path: str) -> str:
    return """# Lake Formation Policy Change

## Review Checklist

- [ ] `lfguard check --desired {desired_path} --fail-on-findings` passes.
- [ ] `lfguard summary --desired {desired_path} --output markdown` was reviewed for changed LF-Tag keys, resources, principals, and permissions.
- [ ] If a current-state snapshot is included, `lfguard audit` findings are understood and intentional.
- [ ] If a plan is included, every `lfguard plan` change was reviewed before apply.
- [ ] Destructive flags such as `--allow-permission-revokes`, `--allow-resource-tag-removals`, and `--allow-lf-tag-value-removals` are used only in a separately approved workflow.
- [ ] Live AWS roles and IAM policies are scoped to the intended read or apply operation.

## Notes

Describe the policy intent, expected drift, and rollout or rollback plan.
""".format(
        desired_path=desired_path,
    )


def _bootstrap_vscode_settings(desired_path: str, *, needs_yaml_extra: bool) -> str:
    if needs_yaml_extra:
        return dumps_json(
            {
                "yaml.schemas": {
                    "./policy/lfguard.schema.json": [
                        desired_path,
                        "snapshots/*.yaml",
                        "snapshots/*.yml",
                    ]
                }
            }
        )
    return dumps_json(
        {
            "json.schemas": [
                {
                    "fileMatch": [
                        desired_path,
                        "snapshots/*.json",
                    ],
                    "url": "./policy/lfguard.schema.json",
                }
            ]
        }
    )


def _bootstrap_vscode_extensions() -> str:
    return dumps_json({"recommendations": ["redhat.vscode-yaml"]})


def _bootstrap_readme(
    desired_path: str,
    *,
    needs_yaml_extra: bool,
    include_live_drift: bool = False,
    include_code_scanning: bool = False,
    include_review_template: bool = False,
    include_editor_config: bool = False,
    policy_owner: str = "@your-org/data-platform",
    aws_role_arn: str = "arn:aws:iam::111122223333:role/LakeFormationReadOnly",
    aws_region: str = "us-east-1",
) -> str:
    install_command = 'python -m pip install "lfguard[yaml]"' if needs_yaml_extra else "python -m pip install lfguard"
    workflow_files = ""
    workflow_steps = ""
    live_drift_next_step = "Add a read-only Lake Formation snapshot workflow when you are ready to check live AWS drift."
    if include_live_drift or include_code_scanning:
        live_extra = "lfguard[aws,yaml]" if needs_yaml_extra else "lfguard[aws]"
        workflow_files = """- `iam/lfguard-read-only.json`: starter IAM policy for the role used by generated
  live AWS workflows.
"""
    if include_live_drift:
        live_extra = "lfguard[aws,yaml]" if needs_yaml_extra else "lfguard[aws]"
        live_drift_next_step = "Review the generated live drift workflow and attach least-privilege read permissions."
        workflow_files += """- `.github/workflows/lfguard-live-drift.yml`: scheduled live AWS drift check
  using GitHub OIDC and `{live_extra}`.
""".format(
            live_extra=live_extra,
        )
        workflow_steps += """
## Live Drift Workflow

The generated live drift workflow assumes `{aws_role_arn}` in `{aws_region}`.
Review `.github/workflows/lfguard-live-drift.yml`, attach the starter
`iam/lfguard-read-only.json` permissions to the assumed role, then enable the
workflow after the desired policy is reviewed.
""".format(
            aws_region=aws_region,
            aws_role_arn=aws_role_arn,
        )
    if include_code_scanning:
        live_extra = "lfguard[aws,yaml]" if needs_yaml_extra else "lfguard[aws]"
        live_drift_next_step = "Review the generated Code Scanning workflow and attach least-privilege read permissions."
        workflow_files += """- `.github/workflows/lfguard-code-scanning.yml`: GitHub Code Scanning workflow
  that uploads `lfguard` SARIF findings using `{live_extra}`.
""".format(
            live_extra=live_extra,
        )
        workflow_steps += """
## Code Scanning Workflow

The generated Code Scanning workflow assumes `{aws_role_arn}` in `{aws_region}`.
Review `.github/workflows/lfguard-code-scanning.yml`, attach the starter
`iam/lfguard-read-only.json` permissions to the assumed role, and confirm the
repository can upload SARIF before enabling the workflow.
""".format(
            aws_region=aws_region,
            aws_role_arn=aws_role_arn,
        )
    if include_live_drift and include_code_scanning:
        live_drift_next_step = "Review the generated live workflows and attach least-privilege read permissions."
    review_files = ""
    review_steps = ""
    if include_review_template:
        review_files = """- `.github/CODEOWNERS`: policy ownership rules for `{policy_owner}`.
- `.github/pull_request_template.md`: Lake Formation policy review checklist.
""".format(
            policy_owner=policy_owner,
        )
        review_steps = """
## Review Governance

Replace `{policy_owner}` in `.github/CODEOWNERS` with the GitHub team or user
that owns Lake Formation policy review. Keep the pull request checklist aligned
with the CI workflows your repository enables.
""".format(
            policy_owner=policy_owner,
        )
    editor_files = ""
    editor_steps = ""
    if include_editor_config:
        editor_files = """- `.vscode/settings.json`: editor schema association for `{desired_path}`.
""".format(
            desired_path=desired_path,
        )
        if needs_yaml_extra:
            editor_files += "- `.vscode/extensions.json`: VS Code YAML extension recommendation.\n"
            editor_steps = """
## Editor Validation

Open this directory in VS Code to validate `{desired_path}` against
`policy/lfguard.schema.json`. Install the recommended YAML extension from
`.vscode/extensions.json` if VS Code prompts you.
""".format(
                desired_path=desired_path,
            )
        else:
            editor_steps = """
## Editor Validation

Open this directory in VS Code to validate `{desired_path}` against
`policy/lfguard.schema.json`.
""".format(
                desired_path=desired_path,
            )
    return """# lfguard Policy Bootstrap

This directory is a starter Lake Formation policy-as-code layout generated by
`lfguard bootstrap`.

## Files

- `policy.py`: Python source of truth for permission groups.
- `{desired_path}`: generated desired LF-Tag and grant policy.
- `policy/lfguard.schema.json`: JSON Schema for editor integration.
- `.github/workflows/lfguard-policy.yml`: offline CI check, summary, and report
  artifact workflow.
- `.pre-commit-config.yaml`: local generate-and-check hook.
{workflow_files}
{review_files}
{editor_files}

## First Checks

```bash
{install_command}
lfguard generate policy.py --output-file {desired_path} --force
lfguard check --desired {desired_path} --fail-on-findings
lfguard summary --desired {desired_path}
```
{workflow_steps}
{review_steps}
{editor_steps}

## Next Steps

1. Replace example LF-Tag keys, values, permission groups, and principals in
   `policy.py` with sanitized names from your environment.
2. Generate `{desired_path}`, then commit `policy.py`, the generated desired
   file, schema, workflow, pre-commit configuration, and any generated review or
   editor files.
3. {live_drift_next_step}
4. Review every `lfguard plan` before using `lfguard apply --execute`.
""".format(
        desired_path=desired_path,
        editor_files=editor_files,
        editor_steps=editor_steps,
        install_command=install_command,
        review_files=review_files,
        review_steps=review_steps,
        workflow_files=workflow_files,
        workflow_steps=workflow_steps,
        live_drift_next_step=live_drift_next_step,
    )


def _sample_desired_state() -> dict:
    return {
        "lf_tags": {
            "sensitivity": ["public", "internal", "restricted"],
            "domain": ["sales", "finance"],
        },
        "data_cells_filters": [
            {
                "name": "orders_public",
                "database": "analytics",
                "table": "orders",
                "row_filter": "country = 'US'",
                "columns": ["order_id", "status"],
            }
        ],
        "resource_tags": [
            {
                "resource": {
                    "kind": "table",
                    "database": "analytics",
                    "table": "orders",
                },
                "tags": {
                    "sensitivity": ["internal"],
                    "domain": ["sales"],
                },
            }
        ],
        "grants": [
            {
                "principal": "arn:aws:iam::111122223333:role/Analyst",
                "resource": {
                    "kind": "lf_tag_policy",
                    "resource_type": "TABLE",
                    "expression": {
                        "domain": ["sales"],
                        "sensitivity": ["public", "internal"],
                    },
                },
                "permissions": ["SELECT", "DESCRIBE"],
            },
            {
                "principal": "arn:aws:iam::111122223333:role/FilteredAnalyst",
                "resource": {
                    "kind": "data_cells_filter",
                    "database": "analytics",
                    "table": "orders",
                    "filter_name": "orders_public",
                },
                "permissions": ["SELECT"],
            }
        ],
    }


def _sample_current_state() -> dict:
    return {
        "lf_tags": {
            "sensitivity": ["public"],
            "domain": ["sales", "finance"],
        },
        "data_cells_filters": [
            {
                "name": "orders_public",
                "database": "analytics",
                "table": "orders",
                "row_filter": "country = 'US'",
                "columns": ["order_id", "status"],
            }
        ],
        "resource_tags": [
            {
                "resource": {
                    "kind": "table",
                    "database": "analytics",
                    "table": "orders",
                },
                "tags": {
                    "domain": ["sales"],
                },
            }
        ],
        "grants": [],
    }


def _sample_files(output_format: str, *, include_ci: bool = False, workflow_path_prefix: str = ".") -> dict:
    desired = _sample_desired_state()
    current = _sample_current_state()
    files = {}
    if output_format in {"json", "both"}:
        files["desired.json"] = dumps_json(desired)
        files["current-snapshot.json"] = dumps_json(current)
    if output_format in {"yaml", "both"}:
        files["desired.yaml"] = dumps_yaml(desired)
        files["current-snapshot.yaml"] = dumps_yaml(current)
    desired_name, current_name = _sample_primary_files(output_format)
    files["README.md"] = _sample_readme(
        desired_name,
        current_name,
        include_yaml_note=output_format in {"yaml", "both"},
        include_both_note=output_format == "both",
        include_ci_note=include_ci,
    )
    if include_ci:
        files[".github/workflows/lfguard-demo.yml"] = _sample_github_actions_workflow(
            desired_name,
            current_name,
            workflow_path_prefix=workflow_path_prefix,
            needs_yaml_extra=desired_name.endswith((".yaml", ".yml")),
        )
    return files


def _sample_primary_files(output_format: str) -> tuple:
    if output_format == "yaml":
        return "desired.yaml", "current-snapshot.yaml"
    return "desired.json", "current-snapshot.json"


def _sample_workflow_path_prefix(output_dir: Path) -> str:
    rendered = str(output_dir)
    if rendered in {"", "."}:
        return "."
    if output_dir.is_absolute():
        return output_dir.name or "."
    return rendered.rstrip("/") or "."


def _workflow_path(prefix: str, name: str) -> str:
    if prefix == ".":
        return name
    return "{}/{}".format(prefix, name)


def _sample_github_actions_workflow(
    desired_name: str,
    current_name: str,
    *,
    workflow_path_prefix: str,
    needs_yaml_extra: bool,
) -> str:
    desired_path = _workflow_path(workflow_path_prefix, desired_name)
    current_path = _workflow_path(workflow_path_prefix, current_name)
    install_target = '"lfguard[yaml]"' if needs_yaml_extra else "lfguard"
    return """name: lfguard demo

on:
  workflow_dispatch:
  pull_request:
    paths:
      - "{desired_path}"
      - "{current_path}"

permissions:
  contents: read

jobs:
  lfguard:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6

      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Install lfguard
        run: python -m pip install {install_target}

      - name: Check, audit, and plan
        run: |
          mkdir -p artifacts

          lfguard check \\
            --desired {desired_path} \\
            --current-snapshot {current_path} \\
            --output markdown \\
            --output-file artifacts/lfguard-check.md \\
            --fail-on-findings \\
            --github-summary

          lfguard audit \\
            --desired {desired_path} \\
            --current-snapshot {current_path} \\
            --output markdown \\
            --output-file artifacts/lfguard-audit.md \\
            --github-summary

          lfguard plan \\
            --desired {desired_path} \\
            --current-snapshot {current_path} \\
            --output markdown \\
            --output-file artifacts/lfguard-plan.md \\
            --github-summary

      - name: Upload lfguard reports
        if: always()
        uses: actions/upload-artifact@v6
        with:
          name: lfguard-demo-reports
          path: artifacts/
          if-no-files-found: ignore
""".format(
        current_path=current_path,
        desired_path=desired_path,
        install_target=install_target,
    )


def _sample_readme(
    desired_name: str,
    current_name: str,
    *,
    include_yaml_note: bool = False,
    include_both_note: bool = False,
    include_ci_note: bool = False,
) -> str:
    yaml_note = ""
    if include_yaml_note:
        yaml_note = """## YAML Support

YAML state files require the optional YAML extra when you read them:

```bash
python -m pip install "lfguard[yaml]"
```

"""
    both_note = ""
    if include_both_note:
        both_note = """This directory includes both JSON and YAML state files. The JSON commands work
with the base `lfguard` install.

"""
    ci_note = ""
    if include_ci_note:
        ci_note = """## GitHub Actions Demo

This directory includes `.github/workflows/lfguard-demo.yml`, an offline
workflow that checks, audits, plans, and uploads Markdown reports. If
this sample directory is not your repository root, commit the sample directory
and copy its `.github` directory to the repository root before enabling the
workflow.

"""
    return """# lfguard Demo

This directory contains a desired Lake Formation guardrail policy and a
deliberately incomplete current-state snapshot. It is safe to use without AWS
credentials.

{both_note}{yaml_note}{ci_note}
## Check State Files

```bash
lfguard check --desired {desired_name} --current-snapshot {current_name}
```

## Summarize Policy

```bash
lfguard summary --desired {desired_name} --current-snapshot {current_name}
```

## Audit Drift

```bash
lfguard audit --desired {desired_name} --current-snapshot {current_name}
```

## Plan Safe Changes

```bash
lfguard plan --desired {desired_name} --current-snapshot {current_name}
```

Expected summary:

```text
Plan: 4 change(s), 4 safe, 0 destructive.
```

## Explain A Row/Column Filter Grant

The sample desired state includes a Lake Formation data cells filter definition
and a missing `SELECT` grant on that filter:

```bash
lfguard explain \\
  --desired {desired_name} \\
  --current-snapshot {current_name} \\
  --principal arn:aws:iam::111122223333:role/FilteredAnalyst \\
  --database analytics \\
  --table orders \\
  --data-cells-filter orders_public \\
  --permissions SELECT
```

## Live Cache Example

Use reviewed snapshots for immutable evidence. For repeated live reads against
the same AWS context, scope the cache by profile, region, catalog, and desired
state:

```bash
lfguard plan \\
  --desired {desired_name} \\
  --profile prod \\
  --region us-east-1 \\
  --catalog-id 111122223333 \\
  --current-cache .lfguard/prod-us-east-1-111122223333-current.json \\
  --current-cache-max-age 900
```

## Save Reports

```bash
lfguard check \\
  --desired {desired_name} \\
  --current-snapshot {current_name} \\
  --output markdown \\
  --output-file lfguard-check.md

lfguard audit \\
  --desired {desired_name} \\
  --current-snapshot {current_name} \\
  --output json \\
  --output-file lfguard-audit.json

lfguard plan \\
  --desired {desired_name} \\
  --current-snapshot {current_name} \\
  --output markdown \\
  --output-file lfguard-plan.md
```
""".format(
        both_note=both_note,
        ci_note=ci_note,
        current_name=current_name,
        desired_name=desired_name,
        yaml_note=yaml_note,
    )


def _render_explain(report: ExplainReport, output: str) -> str:
    if output == "json":
        return dumps_json(report.to_dict())
    if output == "markdown":
        return _render_explain_markdown(report)
    summary = report.summary()
    lines = [
        "Explain: {principal} -> {resource}".format(
            principal=report.principal,
            resource=report.resource.identity,
        ),
        "Findings: {matched} matched, {not_matched} not matched, {missing} missing, {context} context.".format(
            **summary
        ),
    ]
    if report.requested_permissions:
        lines.append("Requested permissions: {}".format(", ".join(report.requested_permissions)))
    else:
        lines.append("Requested permissions: any")
    if report.effective_lf_tags:
        rendered_tags = ", ".join(
            "{}={}".format(key, "|".join(values))
            for key, values in sorted(report.effective_lf_tags.items())
        )
        lines.append("Effective LF-Tags: {}".format(rendered_tags))
    else:
        lines.append("Effective LF-Tags: none")
    catalog_tag_lines = _render_effective_lf_tag_catalog_lines(report)
    if catalog_tag_lines:
        lines.append("Effective LF-Tags by catalog:")
        lines.extend(catalog_tag_lines)
    if report.findings:
        lines.append("Explanation:")
        for finding in report.findings:
            permissions = ", ".join(finding.permissions) if finding.permissions else "none"
            resource = finding.resource.identity if finding.resource else "n/a"
            lines.append(
                "- [{status}] {source} {permissions} on {resource}: {message}".format(
                    status=finding.status,
                    source=finding.source,
                    permissions=permissions,
                    resource=resource,
                    message=finding.message,
                )
            )
    if report.notes:
        lines.append("Notes:")
        for note in report.notes:
            lines.append("- {}".format(note))
    return "\n".join(lines) + "\n"


def _render_explain_markdown(report: ExplainReport) -> str:
    summary = report.summary()
    lines = [
        "### lfguard explain",
        "",
        "- Principal: `{}`".format(report.principal),
        "- Resource: `{}`".format(report.resource.identity),
        "- Matched grants: {matched}".format(**summary),
        "- Not matched: {not_matched}".format(**summary),
        "- Missing desired grants: {missing}".format(**summary),
        "- Context grants: {context}".format(**summary),
    ]
    if report.requested_permissions:
        lines.append("- Requested permissions: `{}`".format(", ".join(report.requested_permissions)))
    if report.effective_lf_tags:
        lines.extend(["", "#### Effective LF-Tags", "", "| Key | Values |", "| --- | --- |"])
        for key, values in sorted(report.effective_lf_tags.items()):
            lines.append("| {} | {} |".format(_markdown_cell(key), _markdown_cell(", ".join(values))))
    else:
        lines.extend(["", "No effective LF-Tags found for the target in current state."])
    if _should_render_effective_lf_tag_catalogs(report):
        lines.extend(["", "#### Effective LF-Tags By Catalog", "", "| Catalog ID | Key | Values |", "| --- | --- | --- |"])
        for catalog_id, tags in sorted(report.effective_lf_tags_by_catalog.items(), key=lambda item: item[0] or ""):
            for key, values in sorted(tags.items()):
                lines.append(
                    "| {} | {} | {} |".format(
                        _markdown_cell(catalog_id or ""),
                        _markdown_cell(key),
                        _markdown_cell(", ".join(values)),
                    )
                )
    if report.findings:
        lines.extend(
            [
                "",
                "#### Findings",
                "",
                "| Status | Source | Permissions | Resource | Message |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for finding in report.findings:
            lines.append(
                "| {status} | {source} | {permissions} | {resource} | {message} |".format(
                    status=_markdown_cell(finding.status),
                    source=_markdown_cell(finding.source),
                    permissions=_markdown_cell(", ".join(finding.permissions)),
                    resource=_markdown_cell(finding.resource.identity if finding.resource else ""),
                    message=_markdown_cell(finding.message),
                )
            )
    if report.notes:
        lines.extend(["", "#### Notes"])
        for note in report.notes:
            lines.append("- {}".format(note))
    return "\n".join(lines) + "\n"


def _should_render_effective_lf_tag_catalogs(report: ExplainReport) -> bool:
    return any(catalog_id for catalog_id in report.effective_lf_tags_by_catalog)


def _render_effective_lf_tag_catalog_lines(report: ExplainReport) -> list:
    if not _should_render_effective_lf_tag_catalogs(report):
        return []
    lines = []
    for catalog_id, tags in sorted(report.effective_lf_tags_by_catalog.items(), key=lambda item: item[0] or ""):
        rendered_tags = ", ".join(
            "{}={}".format(key, "|".join(values))
            for key, values in sorted(tags.items())
        )
        lines.append("- {}: {}".format(catalog_id or "unscoped", rendered_tags or "none"))
    return lines


def _print_plan(change_plan: Plan, output: str, *, prefix: Optional[str] = None) -> None:
    print(_render_plan(change_plan, output, prefix=prefix), end="")


def _render_plan(change_plan: Plan, output: str, *, prefix: Optional[str] = None) -> str:
    if output == "json":
        data: Any = change_plan.to_dict()
        if prefix:
            data = {"message": prefix, "plan": data}
        return dumps_json(data)
    if output == "markdown":
        return _render_plan_markdown(change_plan, prefix=prefix)
    lines = []
    if prefix:
        lines.append(prefix)
    summary = change_plan.summary()
    lines.append(
        "Plan: {total} change(s), {safe} safe, {destructive} destructive.".format(
            **summary
        )
    )
    if not change_plan.changes:
        return "\n".join(lines) + "\n"
    for change in change_plan.changes:
        marker = "destructive" if change.destructive else "safe"
        lines.append(
            "- [{marker}] {id} {action} {target}: {reason}".format(
                marker=marker,
                id=change.id,
                action=change.action,
                target=change.target,
                reason=change.reason,
            )
        )
    return "\n".join(lines) + "\n"


def _print_plan_markdown(change_plan: Plan, *, prefix: Optional[str] = None) -> None:
    print(_render_plan_markdown(change_plan, prefix=prefix), end="")


def _render_plan_markdown(change_plan: Plan, *, prefix: Optional[str] = None) -> str:
    lines = []
    if prefix:
        lines.extend([prefix, ""])
    summary = change_plan.summary()
    lines.extend(
        [
            "### lfguard plan",
            "",
            "- Total changes: {total}".format(**summary),
            "- Safe changes: {safe}".format(**summary),
            "- Destructive changes: {destructive}".format(**summary),
        ]
    )
    if not change_plan.changes:
        lines.extend(["", "No changes."])
        return "\n".join(lines) + "\n"
    lines.extend(["", "| ID | Safety | Action | Target | Reason |", "| --- | --- | --- | --- | --- |"])
    for change in change_plan.changes:
        marker = "destructive" if change.destructive else "safe"
        lines.append(
            "| {id} | {safety} | {action} | {target} | {reason} |".format(
                id=_markdown_cell(change.id or ""),
                safety=_markdown_cell(marker),
                action=_markdown_cell(change.action),
                target=_markdown_cell(change.target),
                reason=_markdown_cell(change.reason),
            )
        )
    return "\n".join(lines) + "\n"


def _render_apply(change_plan: Plan, results: Iterable[Any], output: str, *, applied_count: int) -> str:
    if output == "json":
        return dumps_json({"plan": change_plan.to_dict(), "results": [result.to_dict() for result in results]})
    return _render_plan(change_plan, output, prefix="Applied {} change(s).".format(applied_count))


def _print_findings(findings: Iterable[AuditFinding], output: str) -> None:
    print(_render_findings(findings, output), end="")


def _render_findings(findings: Iterable[AuditFinding], output: str, *, sarif_uri: Optional[str] = None) -> str:
    findings = tuple(findings)
    summary = _finding_summary(findings)
    if output == "json":
        return dumps_json(
            {
                "schema_version": AUDIT_SCHEMA_VERSION,
                "summary": summary,
                "findings": [finding.to_dict() for finding in findings],
            }
        )
    if output == "sarif":
        return dumps_json(_findings_to_sarif(findings, sarif_uri=sarif_uri))
    if output == "markdown":
        return _render_findings_markdown(findings)
    lines = []
    if not findings:
        return "No findings.\n"
    lines.append(_format_finding_summary(summary))
    for finding in findings:
        lines.append(
            "- [{severity}] {code} {target}: {message}".format(
                severity=finding.severity,
                code=finding.code,
                target=finding.target,
                message=finding.message,
            )
        )
    return "\n".join(lines) + "\n"


def _print_findings_markdown(findings: Iterable[AuditFinding]) -> None:
    print(_render_findings_markdown(findings), end="")


def _render_findings_markdown(findings: Iterable[AuditFinding]) -> str:
    findings = tuple(findings)
    summary = _finding_summary(findings)
    lines = ["### lfguard audit", ""]
    if not findings:
        lines.append("No findings.")
        return "\n".join(lines) + "\n"
    lines.extend(
        [
            "- Total findings: {total}".format(**summary),
            "- Error findings: {errors}".format(**summary),
            "- Warning findings: {warnings}".format(**summary),
            "",
            "| Severity | Code | Target | Message |",
            "| --- | --- | --- | --- |",
        ]
    )
    for finding in findings:
        lines.append(
            "| {severity} | {code} | {target} | {message} |".format(
                severity=_markdown_cell(finding.severity),
                code=_markdown_cell(finding.code),
                target=_markdown_cell(finding.target),
                message=_markdown_cell(finding.message),
            )
        )
    return "\n".join(lines) + "\n"


def _findings_to_sarif(findings: Iterable[Any], *, sarif_uri: Optional[str] = None) -> dict:
    findings = tuple(findings)
    rules = []
    for code in sorted({finding.code for finding in findings}):
        rule_findings = [finding for finding in findings if finding.code == code]
        severity = "error" if any(finding.severity == "error" for finding in rule_findings) else "warning"
        rules.append(
            {
                "id": code,
                "name": code,
                "shortDescription": {"text": rule_findings[0].message},
                "defaultConfiguration": {"level": _sarif_level(severity)},
            }
        )
    return {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "lfguard",
                        "version": __version__,
                        "informationUri": "https://github.com/yongjip/aws-datalake-guard",
                        "rules": rules,
                    }
                },
                "results": [
                    {
                        "ruleId": finding.code,
                        "level": _sarif_level(finding.severity),
                        "message": {"text": "{}: {}".format(finding.target, finding.message)},
                        "locations": [_sarif_location(finding, sarif_uri)],
                        "properties": {
                            "severity": finding.severity,
                            "target": finding.target,
                            "details": dict(finding.details),
                        },
                    }
                    for finding in findings
                ],
            }
        ],
    }


def _sarif_level(severity: str) -> str:
    if severity == "error":
        return "error"
    if severity == "warning":
        return "warning"
    return "note"


def _sarif_location(finding: Any, sarif_uri: Optional[str]) -> dict:
    artifact_uri = sarif_uri or "lfguard-audit"
    return {
        "physicalLocation": {
            "artifactLocation": {"uri": artifact_uri},
            "region": {"snippet": {"text": finding.target}},
        },
        "logicalLocations": [{"fullyQualifiedName": finding.target}],
    }


def _finding_summary(findings: Iterable[AuditFinding]) -> dict:
    findings = tuple(findings)
    return {
        "total": len(findings),
        "errors": sum(1 for finding in findings if finding.severity == "error"),
        "warnings": sum(1 for finding in findings if finding.severity == "warning"),
    }


def _format_finding_summary(summary: dict) -> str:
    return "Findings: {total} total, {errors} error(s), {warnings} warning(s).".format(**summary)


def _should_fail_on_findings(findings: Iterable[AuditFinding], fail_on_severity: str) -> bool:
    findings = tuple(findings)
    if fail_on_severity == "error":
        return any(finding.severity == "error" for finding in findings)
    return bool(findings)


def _emit_output(text: str, output_file: Optional[str], *, label: str) -> None:
    if output_file:
        _write_text_file(Path(output_file), text, label)
        return
    print(text, end="")


def _write_text_file(output_path: Path, text: str, label: str) -> None:
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Could not write {} to {}: {}".format(label, output_path, exc)) from exc


def _append_github_summary(markdown_text: str) -> None:
    summary_file = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_file:
        raise RuntimeError("GITHUB_STEP_SUMMARY is not set; use --output markdown or run inside GitHub Actions")
    try:
        with Path(summary_file).open("a", encoding="utf-8") as handle:
            handle.write(markdown_text)
            if not markdown_text.endswith("\n"):
                handle.write("\n")
            handle.write("\n")
    except OSError as exc:
        raise RuntimeError("Could not write GitHub summary to {}: {}".format(summary_file, exc)) from exc


def _markdown_cell(value: object) -> str:
    return str(value).replace("\\", "\\\\").replace("|", "\\|").replace("\n", "<br>")
