# AI Contributor Context

This document captures implementation context for future AI/code-assistant sessions.

## Project Shape

`generate_celeste_data.py` creates Celeste-compatible JSON data. It has four modes:

- `file`: generate JSON only.
- `gb`: Generate Batch API.
- `go`: Generate OnDemand API.
- `fo`: Front Office ticket API.

Generated JSON files go to `output/` by default. The directory is ignored.

## Configuration Split

Configuration is intentionally split:

- `environment.yaml`: publishable placeholder for environment settings.
- `environment.local.yaml`: ignored local file with real endpoint, API key, SAS URI, ticket holder.
- `request.yaml`: default template/request profile.
- `request*.yaml`: optional alternative request profiles for other templates.
- `setup_celeste_environment.py`: interactive helper that creates a user-owned Generate working folder, deploys user-namespaced Celeste Print/Email pipelines, and writes request YAML files.

Environment settings include endpoint, API key, ticket holder, Azure Blob SAS URI, test email recipients, and simulator email domain. Request settings include template path, output filename, pipeline names, filename correlation behavior, and Front Office production actions.

The script prefers `environment.local.yaml` when it exists. Public repos should contain only placeholder secrets.

Publishable request YAML files should not point at a contributor's personal pipeline folder. Use placeholders such as `YOUR_INITIALS/Celeste Print`, or have users run `setup_celeste_environment.py` to create local request files for their own pipeline folder.

Publishable `environment.yaml` should use placeholder test recipients. Real test inboxes belong in ignored `environment.local.yaml`.

## Generate API Behavior

Generate calls use multipart form-data. The `json` multipart part must be sent as a file part named `json` with a filename, not as a plain form field. Evolve otherwise fails to parse `pipelineName`.

Batch uses:

```text
POST /production/v7/startBatchJob
```

The multipart request contains:

- `json`: request JSON file with `pipelineName` and `variables`.
- `dataFile1`: generated Celeste JSON file.

OnDemand uses:

```text
POST /production/v7/onDemand
```

It uses the same multipart pattern, but sends one generated client per request.

The pipeline reads data from:

```text
request://
```

The current pipeline writes output to shared Azure Blob storage through Evolve's `share://...` connector. The Python script does not create working folders or upload batch input to Azure Blob directly. Generate owns multipart request storage and job working folder lifecycle.

## Pipeline Variables

The script sends these Generate variables:

```json
[
  {"codeName": "Template", "value": "..."},
  {"codeName": "OutputFilename", "value": "..."}
]
```

The exact code name `OutputFilename` matters. A previous `OutputFileName` spelling was ignored by Evolve.

The Evolve pipeline should use these variable references:

```text
${pipeline.Template}
${pipeline.OutputFilename}
```

The pipeline appends `.%e`, so `output_filename` in request YAML should be a base filename without `.pdf`.

OnDemand appends the generated `ClientID` to `OutputFilename` so multiple one-client calls do not overwrite each other. Batch sends the configured base filename unchanged because one batch request produces one combined PDF.

## Email Address Generation

The generated `Email` field uses `environment.email.test_recipients` and `environment.email.simulator_domain`.

For small runs, records alternate through `test_recipients`. For larger runs, the generator reserves three records for each configured test recipient, fills the remainder with simulator addresses, and shuffles the combined list.

## Front Office Behavior

Front Office ticket creation uses:

```text
POST /frontoffice/api/system/v2/tickets
```

The ticket body embeds exactly one generated client in:

```text
documentData.dataDefinitions[0].value.Clients[0]
```

Ticket metadata is derived from that client:

- `contract.contractId`: `ClientID`
- `contract.contractName`: full name
- `properties.properties.title`: template/process display name, derived from the template filename unless `front_office.ticket_title` is configured.
- `properties.properties.description`: template/process display name plus full name, `ClientID`, and human-readable production actions when present.

`productionActions` is omitted unless `request.front_office.production_actions` contains one or more YAML sequence items. Do not send an empty array.

Example YAML block sequence:

```yaml
front_office:
  production_actions:
    - PRINT
```

## Tested Behavior

Validated in staging:

- OnDemand single-client request.
- OnDemand multi-call request with unique output filenames.
- Batch with 1, 10, and 100 records.
- Batch with 5 records through `requestLoanOffer.yaml` and the two-step Email pipeline.
- Front Office single ticket creation.

Batch output is expected to be one combined PDF. OnDemand output is one PDF per request.

## Safety Notes

Before publishing:

- Ensure `environment.local.yaml` is ignored and absent from commits.
- Ensure `output/` is ignored and absent from commits.
- Run a secret scan for live API keys, SAS signatures, personal emails, and staging URLs.
