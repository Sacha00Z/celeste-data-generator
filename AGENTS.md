# Agent Notes

This project generates Celeste demo JSON data and can optionally call Evolve Generate and Front Office APIs.

Start with [docs/AI_CONTEXT.md](docs/AI_CONTEXT.md) before changing API/config behavior. It records the tested request shapes and the project decisions that are easy to accidentally undo.

Key rules:

- Do not commit real endpoints, API keys, SAS URIs, generated output, or local environment files.
- Keep stable environment settings in `environment.local.yaml` locally; publishable defaults belong in `environment.yaml`.
- Keep template/request-specific settings in request YAML files such as `request.yaml` or `requestInvestment.yaml`.
- Preserve the generated JSON key `TicketAsignee`; the spelling matches the Celeste data definition.
- `go` and `fo` modes intentionally cap request counts at 10.
- Generated JSON output should default to `output/`.
