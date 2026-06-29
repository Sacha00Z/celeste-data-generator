#!/usr/bin/env python3
"""Interactive setup for Celeste Generate pipelines and request profiles."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from generate_celeste_data import (
    GENERATE_API_BASE_PATH,
    api_key_for,
    build_url,
    default_environment_path,
    load_config,
    send_request,
)


SCRIPT_DIR = Path(__file__).resolve().parent

TEMPLATE_INVESTMENT = (
    "icm:S:Production:S:UserResource//Interactive/StandardPackage/"
    "Templates/StandardDemo/Celeste/Celeste Investment.jld"
)
TEMPLATE_LOAN_OFFER = (
    "icm:S:Production:S:UserResource//Interactive/StandardPackage/"
    "Templates/StandardDemo/Celeste/Celeste Loan Offer.jld"
)

REQUEST_PROFILES = [
    {
        "path": "request.yaml",
        "template_path": TEMPLATE_INVESTMENT,
        "output_filename": "Celeste-Investment",
        "pipeline_kind": "print",
        "production_actions": ["PRINT", "EMAIL_WITH_ATTACHMENT"],
    },
    {
        "path": "requestInvestment.yaml",
        "template_path": TEMPLATE_INVESTMENT,
        "output_filename": "Celeste-Investment",
        "pipeline_kind": "print",
        "production_actions": ["PRINT", "EMAIL_WITH_ATTACHMENT"],
    },
    {
        "path": "requestLoanOffer.yaml",
        "template_path": TEMPLATE_LOAN_OFFER,
        "output_filename": "Celeste-Loan-Offer",
        "pipeline_kind": "email",
        "production_actions": ["PRINT", "EMAIL_WITH_ATTACHMENT"],
    },
]


def main() -> int:
    args = parse_args()
    config = load_config(args.environment, SCRIPT_DIR / "request.yaml")
    evolve = config.environment["evolve"]

    print("Celeste environment setup")
    print(f"Environment: {args.environment}")
    print(f"Endpoint: {evolve.get('endpoint', '')}")
    print()

    answers = collect_answers()
    preview(answers, args.request_dir)

    if args.dry_run:
        print("Dry run only. No API calls or file writes were made.")
        return 0

    if confirm("Deploy working folder and pipelines now?", default=True):
        working_folder_id = create_working_folder(config, answers)
        print(f"Created working folder: {working_folder_id}")
        deploy_pipeline(config, build_print_pipeline(answers, working_folder_id))
        deploy_pipeline(config, build_email_pipeline(answers, working_folder_id))
    else:
        print("Skipped deployment.")

    if confirm("Write request YAML files now?", default=True):
        write_request_profiles(args.request_dir, answers)
    else:
        print("Skipped request YAML files.")

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up Celeste Generate pipelines and request YAML files.")
    parser.add_argument(
        "-e",
        "--environment",
        type=Path,
        default=default_environment_path(),
        help="Environment YAML file. Defaults to environment.local.yaml when present.",
    )
    parser.add_argument(
        "--request-dir",
        type=Path,
        default=SCRIPT_DIR,
        help="Directory where request YAML files should be written. Defaults to this script's directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the resolved setup values without calling APIs or writing files.",
    )
    return parser.parse_args()


def collect_answers() -> dict[str, Any]:
    initials = prompt(
        "User initials / pipeline folder",
        "ABC",
        validate_path_segment,
    )
    pipeline_folder = prompt("Pipeline folder", initials, validate_pipeline_path)
    print_pipeline = prompt("Print pipeline name", f"{pipeline_folder}/Celeste Print", validate_pipeline_path)
    email_pipeline = prompt("Email pipeline name", f"{pipeline_folder}/Celeste Email", validate_pipeline_path)
    working_folder = prompt("Working folder name", f"{initials} Celeste", validate_working_folder_name)
    retention_days = prompt_int("Working folder retention days", 90, minimum=1)
    output_share_path = prompt(
        "Print output share path",
        f"share://{initials}/Celeste",
        validate_non_empty,
    )
    print_config = prompt("Print pipeline production configuration", "icm://", validate_non_empty)
    attachment_config = prompt(
        "Email attachment production configuration",
        f"icm://Custom Solutions/Production Configuration/{initials}-Print-Multiple2.job",
        validate_non_empty,
    )
    email_config = prompt(
        "Email production configuration",
        f"icm://Custom Solutions/Production Configuration/{initials}/{initials} Fix Fonts.job",
        validate_non_empty,
    )
    create_draft = confirm("Create pipelines as drafts?", default=False)

    return {
        "initials": initials,
        "pipeline_folder": pipeline_folder,
        "print_pipeline": print_pipeline,
        "email_pipeline": email_pipeline,
        "working_folder": working_folder,
        "retention_days": retention_days,
        "output_share_path": output_share_path.rstrip("/"),
        "print_config": print_config,
        "attachment_config": attachment_config,
        "email_config": email_config,
        "create_draft": create_draft,
    }


def preview(answers: dict[str, Any], request_dir: Path) -> None:
    print()
    print("Planned setup")
    print(json.dumps(
        {
            "workingFolderName": answers["working_folder"],
            "printPipeline": answers["print_pipeline"],
            "emailPipeline": answers["email_pipeline"],
            "requestFiles": [str(request_dir / profile["path"]) for profile in REQUEST_PROFILES],
        },
        indent=2,
    ))
    print()


def create_working_folder(config: Any, answers: dict[str, Any]) -> str:
    payload = {
        "name": answers["working_folder"],
        "workingFolderRetention": {"inDays": answers["retention_days"]},
    }
    response = post_generate_json(config, "createWorkingFolder", payload)
    working_folder_id = response.get("workingFolderId")
    if not isinstance(working_folder_id, str) or not working_folder_id:
        raise SystemExit(f"createWorkingFolder did not return a workingFolderId: {json.dumps(response, indent=2)}")
    return working_folder_id


def deploy_pipeline(config: Any, payload: dict[str, Any]) -> None:
    response = post_generate_json(config, "createOrUpdateProcessingPipeline", payload)
    print(f"Deployed pipeline {payload['pipelineName']}: {json.dumps(response, indent=2)}")


def post_generate_json(config: Any, resource: str, payload: dict[str, Any]) -> Any:
    evolve = config.environment["evolve"]
    url = build_url(evolve["endpoint"], GENERATE_API_BASE_PATH, resource)
    api_key = api_key_for(evolve, "environment.evolve.api_key")
    return send_request(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body=json.dumps(payload).encode("utf-8"),
    )


def build_print_pipeline(answers: dict[str, Any], working_folder_id: str) -> dict[str, Any]:
    return base_pipeline(
        answers,
        answers["print_pipeline"],
        working_folder_id,
        [
            {
                "name": "Print",
                "isRetryProcessingEnabled": False,
                "failureNotificationEnabled": False,
                "continueOnFailure": False,
                "generate": {
                    "template": "${pipeline.Template}",
                    "channel": "Print",
                    "outputType": "PDF",
                    "generateType": "ContentAuthor",
                    "productionConfiguration": answers["print_config"],
                    "outputModule": "",
                    "outputPath": f"{answers['output_share_path']}/${{pipeline.OutputFilename}}.%e",
                    "attachments": [],
                    "pdfAttachments": {"fileAttachments": []},
                    "inputPaths": [{"name": "${system.defaultDataInputName}", "path": "request://"}],
                    "customParameters": [],
                    "communicationIdStrategy": "OverrideWithCustomValue",
                    "metadataPath": "job://",
                    "sheetNamesMetadata": [],
                },
            }
        ],
    )


def build_email_pipeline(answers: dict[str, Any], working_folder_id: str) -> dict[str, Any]:
    return base_pipeline(
        answers,
        answers["email_pipeline"],
        working_folder_id,
        [
            {
                "name": "Print Attachments",
                "isRetryProcessingEnabled": False,
                "failureNotificationEnabled": False,
                "continueOnFailure": False,
                "generate": {
                    "template": "${pipeline.Template}",
                    "channel": "Print",
                    "outputType": "PDF",
                    "generateType": "ContentAuthor",
                    "productionConfiguration": answers["attachment_config"],
                    "outputModule": "",
                    "outputPath": "job://attachments/file_${system.emailAttachmentsFilePattern}.pdf",
                    "attachments": [],
                    "pdfAttachments": {"fileAttachments": []},
                    "inputPaths": [{"name": "${system.defaultDataInputName}", "path": "request://"}],
                    "customParameters": [],
                    "communicationIdStrategy": "OverrideWithCustomValue",
                    "metadataPath": "job://",
                    "sheetNamesMetadata": [],
                },
            },
            {
                "name": "Send Attachments",
                "isRetryProcessingEnabled": False,
                "failureNotificationEnabled": False,
                "continueOnFailure": False,
                "generate": {
                    "template": "${pipeline.Template}",
                    "channel": "Email",
                    "generateType": "ContentAuthor",
                    "productionConfiguration": answers["email_config"],
                    "outputModule": "",
                    "outputPath": "job://",
                    "attachments": [
                        {
                            "attachmentName": "Attachment.pdf",
                            "path": "job://attachments/file_${system.emailAttachmentsFilePattern}.pdf",
                        }
                    ],
                    "inputPaths": [{"name": "${system.defaultDataInputName}", "path": "request://"}],
                    "customParameters": [],
                    "correlationId": "${system.templateCorrelationId}${system.jobId}${system.correlationId}",
                    "communicationIdStrategy": "OverrideWithCustomValue",
                    "metadataPath": "job://",
                    "sheetNamesMetadata": [],
                },
            },
        ],
    )


def base_pipeline(
    answers: dict[str, Any],
    pipeline_name: str,
    working_folder_id: str,
    steps: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "pipelineName": pipeline_name,
        "description": "Celeste demo data pipeline.",
        "triggers": {
            "hotFolderTrigger": {"isEnabled": False},
            "timeTrigger": {"cronExpressions": [], "isEnabled": False},
            "hitTrigger": {"isEnabled": False},
            "isListenerJobEnabled": False,
        },
        "steps": steps,
        "onErrorSteps": [],
        "variables": [
            {"codeName": "OutputFilename", "value": "Celeste-clients", "isRequired": True},
            {"codeName": "Template", "value": TEMPLATE_LOAN_OFFER, "isRequired": True},
        ],
        "workingFolderId": working_folder_id,
        "createWorkingFolder": False,
        "isDraft": answers["create_draft"],
        "hasTriggersActive": False,
        "pipelineType": "Generate",
        "priority": 50,
        "retryStepProcessingMode": "Disabled",
    }


def write_request_profiles(request_dir: Path, answers: dict[str, Any]) -> None:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("Missing dependency: install PyYAML with 'python3 -m pip install -r requirements.txt'.") from exc

    request_dir.mkdir(parents=True, exist_ok=True)
    for profile in REQUEST_PROFILES:
        pipeline_name = answers["email_pipeline"] if profile["pipeline_kind"] == "email" else answers["print_pipeline"]
        payload = {
            "template_path": profile["template_path"],
            "output_filename": profile["output_filename"],
            "include_correlation_id_in_filenames": False,
            "generate": {
                "on_demand": {"pipeline_name": pipeline_name},
                "batch": {"pipeline_name": pipeline_name},
            },
            "front_office": {
                "production_actions": profile["production_actions"],
            },
        }
        target = request_dir / profile["path"]
        if target.exists() and not confirm(f"Overwrite {target}?", default=False):
            print(f"Skipped {target}")
            continue
        with target.open("w", encoding="utf-8") as yaml_file:
            yaml.safe_dump(payload, yaml_file, sort_keys=False)
        print(f"Wrote {target}")


def prompt(label: str, default: str, validator: Any) -> str:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        value = raw or default
        error = validator(value)
        if error:
            print(error)
            continue
        return value


def prompt_int(label: str, default: int, *, minimum: int) -> int:
    while True:
        raw = input(f"{label} [{default}]: ").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            print("Enter a whole number.")
            continue
        if value < minimum:
            print(f"Enter a value greater than or equal to {minimum}.")
            continue
        return value


def confirm(label: str, *, default: bool) -> bool:
    suffix = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{suffix}]: ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False
        print("Enter yes or no.")


def validate_non_empty(value: str) -> str | None:
    return None if value.strip() else "Value cannot be empty."


def validate_working_folder_name(value: str) -> str | None:
    if len(value) > 20:
        return "Working folder names must be 20 characters or fewer."
    if re.search(r'[\t\n\f\r\b\\/":*?<>|\x00]', value):
        return "Working folder names cannot contain tabs, slashes, quotes, wildcards, angle brackets, pipes, or control characters."
    return validate_non_empty(value)


def validate_path_segment(value: str) -> str | None:
    if "/" in value:
        return "Enter just one folder segment here; slashes are added by the pipeline name prompts."
    return validate_pipeline_path(value)


def validate_pipeline_path(value: str) -> str | None:
    if len(value) > 279:
        return "Pipeline paths must be 279 characters or fewer."
    if re.search(r'[\t\n\f\r\b\\":*?<>|\x00]', value):
        return "Pipeline paths cannot contain tabs, quotes, wildcards, angle brackets, pipes, backslashes, or control characters."
    if "//" in value or value.startswith("/") or value.endswith("/"):
        return "Pipeline paths can contain single slashes between folder names, but not leading, trailing, or repeated slashes."
    return validate_non_empty(value)


if __name__ == "__main__":
    raise SystemExit(main())
