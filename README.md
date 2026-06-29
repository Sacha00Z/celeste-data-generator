<p align="center">
  <img src="assets/celeste-data-generator-logo.png" alt="Celeste Data Generator logo" width="180">
</p>

<h1 align="center">Celeste Data Generator</h1>

<p align="center">
  <img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-6b7280?style=flat-square">
  <a href="LICENSE">
    <img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-6b7280?style=flat-square">
  </a>
  <img alt="Status" src="https://img.shields.io/badge/status-pre--release-6b7280?style=flat-square">
  <img alt="Config" src="https://img.shields.io/badge/config-YAML-6b7280?style=flat-square">
</p>

A Python CLI tool for generating Celeste demo JSON data and optionally sending it to Evolve Generate Batch, Generate OnDemand, or Front Office ticket APIs.

## Features

- Generates Celeste-compatible Australian client data
- Uses Faker when installed, with a curated fallback generator
- Writes generated JSON files to `output/`
- Supports request profiles for different templates and pipelines
- Includes an interactive setup helper for user-owned Generate pipelines
- Calls Generate Batch with multipart input data and pipeline variables
- Calls Generate OnDemand once per generated client
- Creates Front Office tickets with client-matched metadata
- Keeps local credentials in ignored environment files for safer public release

## Before You Start

API modes require access to an Evolve environment with suitable API permissions. Before running setup, have these values ready:

- Evolve endpoint
- Evolve API key
- Front Office ticket holder
- Azure Blob container SAS URI
- optional test email recipients

The setup script creates or updates ignored local files for you:

- `environment.local.yaml` for credentials and local environment settings
- request YAML files that point to your own Generate pipeline folder

Real credentials, SAS URIs, generated output, and local request overrides should stay out of commits.

## Installation

Run the setup in order:

### 1. Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

### 2. Create local config and pipelines

```bash
python3 setup.py
```

`setup.py` prompts only for missing local environment values, then confirms the user-owned Generate folder and pipeline names. It can create a working folder, deploy `Celeste Print` and `Celeste Email` pipelines, and write request YAML files using your own pipeline paths.

### 3. Generate data or call APIs

```bash
python3 generate_celeste_data.py 5
python3 generate_celeste_data.py 5 --mode gb --request requestLoanOffer.yaml
```

## Configuration

The project uses two config layers.

`environment.yaml` contains environment settings and is safe to commit as a placeholder. `environment.local.yaml` contains real local settings and is ignored by git.

Request files such as `request.yaml`, `requestInvestment.yaml`, and `requestLoanOffer.yaml` contain template-dependent settings:

- template path
- output filename base
- Generate Batch and OnDemand pipeline names
- optional Front Office production actions

Environment email settings control generated delivery addresses:

```yaml
email:
  test_recipients:
    - celeste-demo-gmail@example.com
    - celeste-demo-outlook@example.com
  simulator_domain: simulator.quadientcloud.com
```

For small runs, records alternate through `test_recipients`. For larger runs, the generator reserves three records for each configured test recipient, then fills the rest with simulator addresses.

Use `--request` to switch template profiles:

```bash
python3 generate_celeste_data.py 5 --mode go --request requestLoanOffer.yaml
```

## Modes

The CLI has one local generation mode and three API modes.

| Mode | Name | What it does | Record behavior |
| --- | --- | --- | --- |
| `file` | Local file | Generates a Celeste JSON input file only | Any positive record count |
| `gb` | Generate Batch | Sends one multipart request to Generate Batch | One job with all records in one input file |
| `go` | Generate OnDemand | Sends one multipart request to Generate OnDemand per client | Defaults to 1; maximum 10 per run |
| `fo` | Front Office | Creates one Front Office ticket per client | Maximum 10 per run |

Generate API modes send the configured pipeline variables `Template` and `OutputFilename`. OnDemand adds the generated `ClientID` to `OutputFilename` for each request so multiple one-client outputs do not overwrite each other. Batch keeps the configured base filename because one batch job produces one combined output.

Front Office mode embeds one generated client in each ticket request. Ticket client metadata comes from that client, while the dashboard title is derived from the template name. `productionActions` is omitted unless actions are listed in the request YAML.

## Basic Workflow

Use these commands as the common starting points.

### 1. Generate a local JSON file

```bash
python3 generate_celeste_data.py 25
```

This writes:

```text
output/Celeste-25-clients.json
```

Running the same record count again overwrites the existing local JSON file.

### 2. Start a Generate Batch job

```bash
python3 generate_celeste_data.py 100 --mode gb
```

### 3. Start Generate OnDemand jobs

```bash
python3 generate_celeste_data.py 5 --mode go
```

If the record count is omitted, `go` defaults to one:

```bash
python3 generate_celeste_data.py --mode go
```

### 4. Create Front Office tickets

```bash
python3 generate_celeste_data.py 5 --mode fo
```

## Useful Commands

```bash
python3 generate_celeste_data.py 25
python3 generate_celeste_data.py 10 --mode gb
python3 generate_celeste_data.py --mode go
python3 generate_celeste_data.py 2 --mode fo --request requestInvestment.yaml
python3 generate_celeste_data.py 5 --mode gb --request requestLoanOffer.yaml
python3 generate_celeste_data.py 5 --seed 1 # Repeatable generated data for testing
python3 generate_celeste_data.py 5 --output-dir /tmp/celeste-output
python3 setup.py --dry-run
python3 generate_celeste_data.py --help
```

## Request Profiles

Request YAML files use a small set of template-focused settings:

```yaml
template_path: icm:S:Production:S:UserResource//Interactive/StandardPackage/Templates/StandardDemo/Celeste/Celeste Investment.jld
output_filename: Celeste-Investment
include_correlation_id_in_filenames: false

generate:
  on_demand:
    pipeline_name: YOUR_INITIALS/Celeste Print
  batch:
    pipeline_name: YOUR_INITIALS/Celeste Print

front_office:
  production_actions:
    - PRINT
```

`production_actions` is a YAML block sequence. If no actions are listed, the Front Office request omits `productionActions` entirely.

`requestLoanOffer.yaml` targets the Celeste Loan Offer template and the Email pipeline. A 5-record Generate Batch run has been validated with that profile, including the attachment-generation and email-send steps.

## Notes for Contributors

AI/code-agent contributors should read [AGENTS.md](AGENTS.md) before changing API or configuration behavior.

## License and Disclaimer

This project is released under the [MIT License](LICENSE).

This project is an independent demo data generator and API test harness for use with configured Quadient Inspire Evolve environments. [Quadient Inspire Evolve](https://www.quadient.com/en-int/customer-communications/inspire-evolve) is described by Quadient as a SaaS customer communications management solution that brings Content Author, Front Office, Generate, and Archive capabilities together in Quadient Cloud for secure, personalized customer communications, including on-demand and batch generation scenarios.

This project is not affiliated with, endorsed by, or sponsored by Quadient. It does not grant access to Inspire Evolve, Front Office, Azure Blob Storage, Celeste templates, or any other protected environment. Users are responsible for supplying valid credentials and ensuring they have permission to use the configured systems and templates.

Use of Inspire Evolve and related Quadient cloud services may be governed by Quadient's applicable terms, including the [Quadient Digital Terms and Conditions for Inspire Evolve](https://www.quadient.com/en-us/digital-terms). Review the current Quadient terms for your region and agreement before using this tool with a live environment.
