#!/usr/bin/env python3
"""Generate Celeste JSON data for local test harness uploads."""

from __future__ import annotations

import argparse
import json
import mimetypes
import random
import re
import string
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib import error, parse, request

try:
    from titlecase import titlecase as external_titlecase
except ImportError:
    external_titlecase = None


DEFAULT_ENVIRONMENT_PATH = Path(__file__).with_name("environment.yaml")
LOCAL_ENVIRONMENT_PATH = Path(__file__).with_name("environment.local.yaml")
DEFAULT_REQUEST_PATH = Path(__file__).with_name("request.yaml")
DEFAULT_OUTPUT_DIR = Path(__file__).with_name("output")
GENERATE_API_BASE_PATH = "/production/v7"
FRONT_OFFICE_API_BASE_PATH = "/frontoffice/api/system/v2"
BATCH_DATA_FILENAME = "Celeste-clients.json"
ON_DEMAND_DATA_FILENAME_PREFIX = "Celeste-on-demand"
MAX_SINGLE_RECORD_API_CALLS = 10
FRONT_OFFICE_STATE_ID = "S_simple_scenario_writer_assigned"
FRONT_OFFICE_TICKET_ICON_BASE = "companyRoot://WebResources/TicketIcons"
FRONT_OFFICE_TICKET_ICONS = [
    "doc_01.png",
    "doc_08.png",
    "doc_09.png",
    "doc_10.png",
    "doc_11.png",
    "doc_12.png",
    "doc_13.png",
    "doc_14.png",
    "doc_15.png",
]
PHONE_NUMBER = "+61000000000"
DEFAULT_TEST_RECIPIENTS = ["celeste-demo-gmail@example.com", "celeste-demo-outlook@example.com"]
SIMULATOR_DOMAIN = "simulator.quadientcloud.com"
TEST_RECIPIENT_SLOTS = 3

AU_STATES = [
    ("New South Wales", "NSW", ["Sydney", "Newcastle", "Wollongong", "Parramatta", "Dubbo"], ("2000", "2999")),
    ("Victoria", "VIC", ["Melbourne", "Geelong", "Ballarat", "Bendigo", "Dandenong"], ("3000", "3999")),
    ("Queensland", "QLD", ["Brisbane", "Gold Coast", "Cairns", "Townsville", "Toowoomba"], ("4000", "4999")),
    ("South Australia", "SA", ["Adelaide", "Mount Gambier", "Whyalla", "Gawler", "Port Augusta"], ("5000", "5999")),
    ("Western Australia", "WA", ["Perth", "Fremantle", "Bunbury", "Albany", "Geraldton"], ("6000", "6999")),
    ("Tasmania", "TAS", ["Hobart", "Launceston", "Devonport", "Burnie", "Kingston"], ("7000", "7999")),
    ("Northern Territory", "NT", ["Darwin", "Palmerston", "Alice Springs", "Katherine", "Nhulunbuy"], ("0800", "0999")),
    ("Australian Capital Territory", "ACT", ["Canberra", "Belconnen", "Gungahlin", "Tuggeranong", "Woden"], ("2600", "2618")),
]

FIRST_NAMES = {
    "F": ["Olivia", "Amelia", "Charlotte", "Mia", "Ava", "Grace", "Chloe", "Matilda", "Sophie", "Ruby"],
    "M": ["Oliver", "Noah", "Henry", "Leo", "Jack", "William", "Charlie", "Lucas", "Thomas", "Hudson"],
}
LAST_NAMES = [
    "Smith",
    "Jones",
    "Williams",
    "Brown",
    "Wilson",
    "Taylor",
    "Nguyen",
    "Martin",
    "Anderson",
    "Thompson",
    "Walker",
    "Ryan",
]
STREET_NAMES = [
    "George Street",
    "Collins Street",
    "Queen Street",
    "King William Road",
    "St Georges Terrace",
    "Macquarie Street",
    "Elizabeth Street",
    "Victoria Parade",
    "Flinders Lane",
    "Northbourne Avenue",
]

STOCKS = [
    ("Apple Inc.", "US0378331005"),
    ("Microsoft Corporation", "US5949181045"),
    ("Amazon.com, Inc.", "US0231351067"),
    ("Alphabet Inc.", "US02079K3059"),
    ("Meta Platforms, Inc.", "US30303M1027"),
    ("NVIDIA Corporation", "US67066G1040"),
    ("Tesla, Inc.", "US88160R1014"),
    ("Netflix, Inc.", "US64110L1061"),
    ("Adobe Inc.", "US00724F1012"),
    ("Cisco Systems, Inc.", "US17275R1023"),
]

ORDER_TYPES = [
    "At best purchase price",
    "At best sale price",
    "Limit purchase order",
    "Limit sale order",
]


@dataclass(frozen=True)
class Identity:
    first_name: str
    last_name: str
    gender: str
    title: str
    address1: str
    address2: str
    city: str
    zip: str
    state: str
    state_abbreviation: str


@dataclass(frozen=True)
class AppConfig:
    ticket_holder: str
    environment: dict[str, Any]
    request: dict[str, Any]


def main() -> int:
    args = parse_args()
    record_count = resolve_record_count(args.records, args.mode)
    rng = random.Random(args.seed)
    config = load_config(args.environment, args.request)

    identities = load_identities(record_count, rng)
    emails = build_email_plan(record_count, config, rng)
    payload = {
        "Clients": [
            build_client(identity, email, config.ticket_holder, rng)
            for identity, email in zip(identities, emails)
        ]
    }
    output_path = write_payload(payload, record_count, args.output_dir)
    print(output_path)

    if args.mode == "gb":
        response = call_generate_batch(config, output_path)
        print_response("Generate Batch", response)
    elif args.mode == "go":
        for index, client in enumerate(payload["Clients"], start=1):
            response = call_generate_on_demand(config, client, index)
            print_response(f"Generate OnDemand {index}", response)
    elif args.mode == "fo":
        for index, client in enumerate(payload["Clients"], start=1):
            response = call_front_office_ticket(config, client)
            print_response(f"Front Office ticket {index}", response)

    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Celeste JSON test data.")
    parser.add_argument(
        "records",
        type=positive_int,
        nargs="?",
        help="Number of records or API calls. Optional only for '--mode go', where it defaults to 1.",
    )
    parser.add_argument(
        "--mode",
        choices=("file", "gb", "go", "fo"),
        default="file",
        help="Operation mode: file, gb (Generate Batch), go (Generate OnDemand), or fo (Front Office tickets).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Directory for generated JSON. Defaults to the project output folder.",
    )
    parser.add_argument("--seed", type=int, default=None, help="Optional random seed for repeatable test data.")
    parser.add_argument(
        "-e",
        "--environment",
        type=Path,
        default=default_environment_path(),
        help="Environment YAML file. Defaults to environment.local.yaml when present, otherwise environment.yaml.",
    )
    parser.add_argument(
        "-r",
        "--request",
        type=Path,
        default=DEFAULT_REQUEST_PATH,
        help="Request YAML file. Defaults to request.yaml next to this script.",
    )
    return parser.parse_args()


def default_environment_path() -> Path:
    return LOCAL_ENVIRONMENT_PATH if LOCAL_ENVIRONMENT_PATH.exists() else DEFAULT_ENVIRONMENT_PATH


def resolve_record_count(records: int | None, mode: str) -> int:
    if records is None:
        if mode == "go":
            records = 1
        else:
            raise SystemExit("records is required unless you run '--mode go'.")

    if mode in {"go", "fo"} and records > MAX_SINGLE_RECORD_API_CALLS:
        raise SystemExit(f"--mode {mode} accepts at most {MAX_SINGLE_RECORD_API_CALLS} records.")

    return records


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("records must be greater than zero")
    return parsed


def load_config(environment_path: Path, request_path: Path) -> AppConfig:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("Missing dependency: install PyYAML with 'python3 -m pip install -r requirements.txt'.") from exc

    environment = load_yaml_mapping(environment_path, yaml, "Environment")
    request_config = load_yaml_mapping(request_path, yaml, "Request")

    evolve = mapping_at(environment, "evolve")
    ticket_holder = required_string(evolve, "ticket_holder", "environment.evolve.ticket_holder")
    parse_azure_blob_sas_uri(environment)

    return AppConfig(ticket_holder=ticket_holder, environment=environment, request=request_config)


def load_yaml_mapping(path: Path, yaml: Any, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{label} file not found: {path}")

    with path.open("r", encoding="utf-8") as yaml_file:
        raw = yaml.safe_load(yaml_file) or {}

    if not isinstance(raw, dict):
        raise SystemExit(f"{label} file must contain a YAML mapping: {path}")

    return raw


def call_generate_batch(config: AppConfig, data_file: Path) -> Any:
    evolve = mapping_at(config.environment, "evolve")
    generate = mapping_at(config.request, "generate")
    batch = mapping_at(generate, "batch")
    pipeline_name = required_string(batch, "pipeline_name", "request.generate.batch.pipeline_name")
    api_key = api_key_for(evolve, "environment.evolve.api_key")
    request_json = {
        "pipelineName": pipeline_name,
        "variables": generate_variable_list(config),
    }
    fields: dict[str, str] = {}
    files = {
        "json": ("request.json", json.dumps(request_json).encode("utf-8"), "application/json"),
        "dataFile1": (BATCH_DATA_FILENAME, data_file.read_bytes(), "application/json"),
    }
    content_type, body = encode_multipart(fields, files)
    url = build_url(
        required_string(evolve, "endpoint", "environment.evolve.endpoint"),
        GENERATE_API_BASE_PATH,
        "startBatchJob",
    )
    return send_request(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
        body=body,
    )


def call_generate_on_demand(config: AppConfig, client: dict[str, Any], sequence: int) -> Any:
    evolve = mapping_at(config.environment, "evolve")
    generate = mapping_at(config.request, "generate")
    on_demand = mapping_at(generate, "on_demand")
    api_key = api_key_for(evolve, "environment.evolve.api_key")
    request_json = {
        "pipelineName": required_string(on_demand, "pipeline_name", "request.generate.on_demand.pipeline_name"),
        "variables": generate_variable_list(config, client),
    }

    filename = f"{ON_DEMAND_DATA_FILENAME_PREFIX}-{sequence}.json"
    fields: dict[str, str] = {}
    files = {
        "json": ("request.json", json.dumps(request_json).encode("utf-8"), "application/json"),
        "dataFile1": (filename, json.dumps(single_client_payload(client)).encode("utf-8"), "application/json"),
    }
    content_type, body = encode_multipart(fields, files)
    url = build_url(
        required_string(evolve, "endpoint", "environment.evolve.endpoint"),
        GENERATE_API_BASE_PATH,
        "onDemand",
    )
    return send_request(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": content_type},
        body=body,
    )


def call_front_office_ticket(config: AppConfig, client: dict[str, Any]) -> Any:
    evolve = mapping_at(config.environment, "evolve")
    api_key = api_key_for(evolve, "environment.evolve.api_key")
    url = build_url(
        required_string(evolve, "endpoint", "environment.evolve.endpoint"),
        FRONT_OFFICE_API_BASE_PATH,
        "tickets",
    )
    ticket_payload = build_front_office_ticket(config, client)
    return send_request(
        url,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        body=json.dumps(ticket_payload).encode("utf-8"),
    )


def build_front_office_ticket(config: AppConfig, client: dict[str, Any]) -> dict[str, Any]:
    ticket_payload = {
        "documentData": {
            "templateName": template_path(config),
            "dataDefinitions": [
                {
                    "moduleName": "DataInput",
                    "type": "json",
                    "value": single_client_payload(client),
                }
            ],
            "commands": [],
        },
        "stateId": FRONT_OFFICE_STATE_ID,
        "holder": {"type": "userName", "holder": config.ticket_holder},
        "attachments": [],
        "contract": {
            "contractId": format_client_value("{ClientID}", client),
            "contractName": format_client_value("{FullName}", client),
        },
        "properties": {
            "properties": {
                "icon": front_office_ticket_icon(config, client),
                "title": front_office_ticket_title(config),
                "description": front_office_ticket_description(config, client),
            }
        },
        "uploadAttachmentFromLocalDriveEnabled": True,
        "addAttachmentFromGlobalStorageEnabled": True,
        "type": "ticket",
    }
    actions = front_office_production_actions(config)
    if actions:
        ticket_payload["productionActions"] = actions
    return ticket_payload


def front_office_production_actions(config: AppConfig) -> list[str]:
    front_office = mapping_at(config.request, "front_office", required=False)
    actions = front_office.get("production_actions", [])
    if actions is None:
        return []
    if not isinstance(actions, list) or not all(isinstance(action, str) and action.strip() for action in actions):
        raise SystemExit("Config key 'request.front_office.production_actions' must be a list of non-empty strings.")
    return [action.strip() for action in actions]


def front_office_ticket_title(config: AppConfig) -> str:
    front_office = mapping_at(config.request, "front_office", required=False)
    configured_title = front_office.get("ticket_title")
    if isinstance(configured_title, str) and configured_title.strip():
        return human_title(configured_title)
    return human_title(Path(template_path(config)).stem)


def front_office_ticket_description(config: AppConfig, client: dict[str, Any]) -> str:
    client_description = format_client_value("{FullName} ({ClientID})", client)
    description = f"{front_office_ticket_title(config)} for {client_description}"
    actions = front_office_production_actions(config)
    if actions:
        description = f"{description}. Actions: {', '.join(human_title(action) for action in actions)}."
    return description


def front_office_ticket_icon(config: AppConfig, client: dict[str, Any]) -> str:
    front_office = mapping_at(config.request, "front_office", required=False)
    configured_icon = front_office.get("ticket_icon")
    if isinstance(configured_icon, str) and configured_icon.strip():
        icon_filename = configured_icon.strip().split("/")[-1]
        validate_ticket_icon(icon_filename)
        return ticket_icon_path(icon_filename)

    candidates = icon_candidates_for_request(config)
    source = "|".join(
        [
            template_path(config),
            ",".join(front_office_production_actions(config)),
            str(client.get("ClientID", "")),
            str(client.get("AccountNumber", "")),
            str(client.get("StatementDate", "")),
        ]
    )
    index = uuid.uuid5(uuid.NAMESPACE_URL, source).int % len(candidates)
    return ticket_icon_path(candidates[index])


def icon_candidates_for_request(config: AppConfig) -> list[str]:
    template_name = Path(template_path(config)).stem.lower()
    actions = {action.upper() for action in front_office_production_actions(config)}
    candidates: list[str] = []

    if "loan" in template_name:
        candidates.extend(["doc_13.png", "doc_08.png", "doc_01.png"])
    if "investment" in template_name or "advice" in template_name:
        candidates.extend(["doc_11.png", "doc_10.png", "doc_14.png"])
    if "statement" in template_name or "notice" in template_name:
        candidates.extend(["doc_01.png", "doc_14.png"])

    if "PRINT" in actions:
        candidates.extend(["doc_01.png", "doc_14.png"])
    if "EMAIL_WITH_ATTACHMENT" in actions:
        candidates.extend(["doc_12.png", "doc_15.png"])

    return unique_valid_icons(candidates) or FRONT_OFFICE_TICKET_ICONS


def unique_valid_icons(icons: list[str]) -> list[str]:
    unique_icons = []
    for icon in icons:
        if icon in FRONT_OFFICE_TICKET_ICONS and icon not in unique_icons:
            unique_icons.append(icon)
    return unique_icons


def validate_ticket_icon(icon_filename: str) -> None:
    if icon_filename not in FRONT_OFFICE_TICKET_ICONS:
        valid_icons = ", ".join(FRONT_OFFICE_TICKET_ICONS)
        raise SystemExit(f"Config key 'request.front_office.ticket_icon' must be one of: {valid_icons}.")


def ticket_icon_path(icon_filename: str) -> str:
    return f"{FRONT_OFFICE_TICKET_ICON_BASE}/{icon_filename}"


def human_title(value: str) -> str:
    words = re.sub(r"[_\-]+", " ", value).strip()
    words = re.sub(r"\s+", " ", words)
    if not words:
        return ""
    if external_titlecase:
        return external_titlecase(words)
    return words.title()


def template_path(config: AppConfig) -> str:
    return required_string(config.request, "template_path", "request.template_path")


def output_filename(config: AppConfig, client: dict[str, Any] | None = None) -> str:
    filename = required_string(config.request, "output_filename", "request.output_filename")
    if client is None:
        return filename

    parts = [safe_filename_token(str(client.get("ClientID", "")))]
    if include_correlation_id_in_filenames(config):
        parts.append(correlation_id_for_client(client))
    return filename_with_suffix(filename, "-".join(part for part in parts if part))


def include_correlation_id_in_filenames(config: AppConfig) -> bool:
    value = config.request.get("include_correlation_id_in_filenames", False)
    if not isinstance(value, bool):
        raise SystemExit("Config key 'request.include_correlation_id_in_filenames' must be true or false.")
    return value


def correlation_id_for_client(client: dict[str, Any]) -> str:
    source = "-".join(
        str(client.get(key, ""))
        for key in ["ClientID", "AccountNumber", "StatementDate"]
    )
    return str(uuid.uuid5(uuid.NAMESPACE_URL, source)).split("-")[0]


def safe_filename_token(value: str) -> str:
    return "".join(character if character.isalnum() or character in "-_" else "-" for character in value).strip("-")


def filename_with_suffix(filename: str, suffix: str) -> str:
    if not suffix:
        return filename_stem(filename)
    return f"{filename_stem(filename)}-{suffix}"


def filename_stem(filename: str) -> str:
    path = Path(filename)
    return path.stem if path.suffix else filename


def generate_variables(config: AppConfig, client: dict[str, Any] | None = None) -> dict[str, str]:
    return {
        "Template": template_path(config),
        "OutputFilename": output_filename(config, client),
    }


def generate_variable_list(config: AppConfig, client: dict[str, Any] | None = None) -> list[dict[str, str]]:
    return [
        {"codeName": name, "value": value}
        for name, value in generate_variables(config, client).items()
    ]


def single_client_payload(client: dict[str, Any]) -> dict[str, Any]:
    return {"Clients": [client]}


def format_client_value(template: str, client: dict[str, Any]) -> str:
    values = {key: "" if value is None else value for key, value in client.items()}
    values["FullName"] = f"{client.get('FirstName', '')} {client.get('LastName', '')}".strip()
    return template.format_map(DefaultFormatValues(values))


class DefaultFormatValues(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return ""


def api_key_for(section: dict[str, Any], key_path: str) -> str:
    api_key = section.get("api_key")
    if isinstance(api_key, str) and api_key.strip():
        return api_key.strip()
    raise SystemExit(f"Config key '{key_path}' must contain an API key for this mode.")


def mapping_at(parent: dict[str, Any], key: str, *, required: bool = True) -> dict[str, Any]:
    value = parent.get(key)
    if value is None and not required:
        return {}
    if not isinstance(value, dict):
        raise SystemExit(f"Config key '{key}' must be a mapping.")
    return value


def required_string(parent: dict[str, Any], key: str, key_path: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"Config key '{key_path}' must be a non-empty string.")
    return value.strip()


def parse_azure_blob_sas_uri(raw: dict[str, Any]) -> tuple[str, str] | None:
    azure_blob = mapping_at(raw, "azure_blob", required=False)
    if not azure_blob:
        return None
    sas_uri = required_string(azure_blob, "sas_uri", "azure_blob.sas_uri")
    parsed = parse.urlsplit(sas_uri)
    if not parsed.scheme or not parsed.netloc or not parsed.path or not parsed.query:
        raise SystemExit("Config key 'azure_blob.sas_uri' must be a full container SAS URI.")
    root = parse.urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    auth = parse.urlunsplit(("", "", "", parsed.query, parsed.fragment))
    return root, auth


def build_url(endpoint: str, base_path: str, resource: str) -> str:
    root = endpoint.rstrip("/") + "/"
    path = "/".join(part.strip("/") for part in [base_path, resource] if part)
    return parse.urljoin(root, path)


def send_request(url: str, *, method: str, headers: dict[str, str], body: bytes) -> Any:
    api_request = request.Request(url, data=body, headers=headers, method=method)
    try:
        with request.urlopen(api_request, timeout=120) as response:
            response_body = response.read()
            return decode_response(response.status, response_body, response.headers.get_content_type())
    except error.HTTPError as exc:
        response_body = exc.read()
        detail = decode_response(exc.code, response_body, exc.headers.get_content_type())
        raise SystemExit(f"{method} {url} failed with HTTP {exc.code}: {json.dumps(detail, indent=2)}") from exc
    except error.URLError as exc:
        raise SystemExit(f"{method} {url} failed: {exc.reason}") from exc


def decode_response(status: int, body: bytes, content_type: str) -> Any:
    if not body:
        return {"status": status}
    text = body.decode("utf-8", errors="replace")
    if content_type == "application/json" or text.lstrip().startswith(("{", "[")):
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
    return {"status": status, "body": text}


def print_response(label: str, response: Any) -> None:
    print(f"{label}: {json.dumps(response, indent=2)}")


def encode_multipart(fields: dict[str, str], files: dict[str, tuple[str, bytes, str | None]]) -> tuple[str, bytes]:
    boundary = f"----celeste-{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for name, value in fields.items():
        lines.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"\r\n'.encode("utf-8"),
                b"Content-Type: application/json\r\n\r\n",
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    for name, (filename, content, content_type) in files.items():
        guessed_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
        lines.extend(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode("utf-8"),
                f"Content-Type: {guessed_type}\r\n\r\n".encode("utf-8"),
                content,
                b"\r\n",
            ]
        )
    lines.append(f"--{boundary}--\r\n".encode("utf-8"))
    return f"multipart/form-data; boundary={boundary}", b"".join(lines)


def load_identities(count: int, rng: random.Random) -> list[Identity]:
    try:
        from faker import Faker
    except ImportError:
        return fallback_identities(count, rng)

    fake = Faker("en_AU")
    fake.seed_instance(rng.randint(1, 999_999_999))

    try:
        return faker_identities(count, fake, rng)
    except Exception:
        return fallback_identities(count, rng)


def faker_identities(count: int, fake: Any, rng: random.Random) -> list[Identity]:
    identities = []
    for _ in range(count):
        state, state_abbreviation, cities, postcode_range = weighted_state(rng)
        gender = rng.choice(["F", "M"])
        title = rng.choice(["Ms.", "Mrs."]) if gender == "F" else "Mr."
        postcode = rng.randint(int(postcode_range[0]), int(postcode_range[1]))

        first_name = fake.first_name_female() if gender == "F" else fake.first_name_male()
        address2 = fake.secondary_address() if rng.random() < 0.12 else ""
        identities.append(
            Identity(
                first_name=first_name,
                last_name=fake.last_name(),
                gender=gender,
                title=title,
                address1=str(fake.street_address()).replace("\n", ", "),
                address2=address2,
                city=rng.choice(cities),
                zip=f"{postcode:04d}",
                state=state,
                state_abbreviation=state_abbreviation,
            )
        )
    return identities


def fallback_identities(count: int, rng: random.Random) -> list[Identity]:
    identities = []
    for _ in range(count):
        state, state_abbreviation, cities, postcode_range = weighted_state(rng)
        gender = rng.choice(["F", "M"])
        title = rng.choice(["Ms.", "Mrs."]) if gender == "F" else "Mr."
        postcode = rng.randint(int(postcode_range[0]), int(postcode_range[1]))
        address2 = f"Unit {rng.randint(1, 40)}" if rng.random() < 0.12 else ""

        identities.append(
            Identity(
                first_name=rng.choice(FIRST_NAMES[gender]),
                last_name=rng.choice(LAST_NAMES),
                gender=gender,
                title=title,
                address1=f"{rng.randint(1, 299)} {rng.choice(STREET_NAMES)}",
                address2=address2,
                city=rng.choice(cities),
                zip=f"{postcode:04d}",
                state=state,
                state_abbreviation=state_abbreviation,
            )
        )
    return identities


def weighted_state(rng: random.Random) -> tuple[str, str, list[str], tuple[str, str]]:
    weights = [32, 26, 20, 7, 11, 2, 1, 1]
    return rng.choices(AU_STATES, weights=weights, k=1)[0]


def build_client(identity: Identity, email: str, ticket_holder: str, rng: random.Random) -> dict[str, Any]:
    statement_date = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    stock_name, stock_isin = rng.choice(STOCKS)
    dealt_quantity = rng.choice([25, 50, 75, 100, 150, 200, 250, 500])
    dealt_price = rng.randint(1_500, 450_000)
    trading_fee = rng.choice([5, 10, 15, 20])
    applicable_taxes = round_money(dealt_quantity * dealt_price * rng.uniform(0.0001, 0.0008))
    settlement_amount = round_money((dealt_quantity * dealt_price / 100) + trading_fee + applicable_taxes)
    credit_limit = round_money(rng.choice([5000, 7500, 10000, 15000, 20000, 25000]))
    revised_balance = round_money(max(0, float(credit_limit) - float(settlement_amount) % float(credit_limit)))

    return {
        "ClientID": f"L{rng.randint(10000, 99999)}",
        "TicketAsignee": ticket_holder,
        "FirstName": identity.first_name,
        "LastName": identity.last_name,
        "Gender": identity.gender,
        "Title": "",
        "AddressSalutation": identity.title,
        "Address1": identity.address1,
        "Address2": identity.address2,
        "City": identity.city,
        "Zip": identity.zip,
        "State": identity.state,
        "StateAbbreviation": identity.state_abbreviation,
        "AccountNumber": digits(rng, 8),
        "AnnualPercentage": f"{rng.randint(5, 30)}%",
        "CreditLimit": f"{credit_limit:.2f}",
        "StatementDate": statement_date,
        "DelayedPayment": str(rng.randint(0, 10)),
        "Email": email,
        "Length": str(rng.choice([12, 18, 24, 36, 48])),
        "Phone": PHONE_NUMBER,
        "TotalAmount": str(rng.randint(500, 20000)),
        "Transactions": {
            "ReferenceNumber": reference_number(rng),
            "InvestmentAccount": account_triplet(rng),
            "SettlementAccount": account_triplet(rng),
            "OrderType": rng.choice(ORDER_TYPES),
            "OrderDealtOn": statement_date,
            "Venue": "CELESTE Bank Global Markets",
            "StockName": stock_name,
            "StockISIN": stock_isin,
            "DealtQuantity": dealt_quantity,
            "DealtPrice": dealt_price,
            "Conditions": rng.choice(["None", "Good for day", "Fill or kill"]),
            "TradingFee": trading_fee,
            "ApplicableTaxes": applicable_taxes,
            "SettlementAmount": settlement_amount,
            "RevisedBalance": revised_balance,
        },
    }


def build_email_plan(total_records: int, config: AppConfig, rng: random.Random) -> list[str]:
    test_recipients = email_test_recipients(config)
    test_recipient_limit = len(test_recipients) * TEST_RECIPIENT_SLOTS
    if total_records <= test_recipient_limit:
        return [test_recipients[index % len(test_recipients)] for index in range(total_records)]

    demo_slots = [
        recipient
        for recipient in test_recipients
        for _ in range(TEST_RECIPIENT_SLOTS)
    ]
    simulator_count = total_records - len(demo_slots)
    simulator_slots = simulator_email_plan(simulator_count, config, rng)
    emails = demo_slots + simulator_slots
    rng.shuffle(emails)
    return emails


def email_test_recipients(config: AppConfig) -> list[str]:
    email = mapping_at(config.environment, "email", required=False)
    recipients = email.get("test_recipients", DEFAULT_TEST_RECIPIENTS)
    if not isinstance(recipients, list) or not all(isinstance(recipient, str) and recipient.strip() for recipient in recipients):
        raise SystemExit("Config key 'email.test_recipients' must be a list of non-empty strings.")
    return [recipient.strip() for recipient in recipients]


def simulator_email_domain(config: AppConfig) -> str:
    email = mapping_at(config.environment, "email", required=False)
    domain = email.get("simulator_domain", SIMULATOR_DOMAIN)
    if not isinstance(domain, str) or not domain.strip():
        raise SystemExit("Config key 'email.simulator_domain' must be a non-empty string.")
    return domain.strip()


def simulator_email_plan(count: int, config: AppConfig, rng: random.Random) -> list[str]:
    if count <= 0:
        return []

    emails = ["delivered"] * count
    available_indexes = list(range(count))

    bounce_count = int(count * 0.025)
    if bounce_count == 0 and count >= 40 and rng.random() < 0.5:
        bounce_count = 1
    for index in take_indexes(available_indexes, bounce_count, rng):
        emails[index] = rng.choice(["softbounced", "hardbounced"])

    remaining_indexes = [index for index in available_indexes if emails[index] == "delivered"]
    spam_count = min(2, max(0, int(count * 0.015)))
    if spam_count == 0 and count >= 20 and rng.random() < 0.35:
        spam_count = 1
    for index in take_indexes(remaining_indexes, spam_count, rng):
        emails[index] = "delivered-spam"

    remaining_indexes = [index for index in available_indexes if emails[index] == "delivered"]
    unsubscribe_count = 1 if count >= 150 and rng.random() < 0.4 else 0
    for index in take_indexes(remaining_indexes, unsubscribe_count, rng):
        emails[index] = "delivered-unsubscribed"

    remaining_indexes = [index for index in available_indexes if emails[index] == "delivered"]
    link_click_count = max(0, int(count * 0.04))
    for index in take_indexes(remaining_indexes, link_click_count, rng):
        emails[index] = "delivered-linkclick"

    rng.shuffle(emails)
    return [f"{email}@{simulator_email_domain(config)}" for email in emails]


def take_indexes(indexes: list[int], count: int, rng: random.Random) -> list[int]:
    if count <= 0 or not indexes:
        return []
    selected = rng.sample(indexes, min(count, len(indexes)))
    for index in selected:
        indexes.remove(index)
    return selected


def digits(rng: random.Random, length: int) -> str:
    return "".join(rng.choice(string.digits) for _ in range(length))


def reference_number(rng: random.Random) -> str:
    return "".join(rng.choice(string.ascii_uppercase) for _ in range(6)) + digits(rng, 10)


def account_triplet(rng: random.Random) -> str:
    return f"{digits(rng, 3)}-{digits(rng, 6)}-{digits(rng, 3)}"


def round_money(value: float | int) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def write_payload(payload: dict[str, Any], record_count: int, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"Celeste-{record_count}-clients.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    raise SystemExit(main())
