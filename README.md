# Claims Intake Service

The claims intake service accepts a first notice of loss from the claims portal,
validates it against the policy master and the rule table in
`docs/api-contract.md`, and either records the notification and issues a claim
reference or refuses the submission with a specific reason. It decides whether a
notification is well formed and admissible. It does not decide whether the claim
will be paid.

`POST /notifications` is the only endpoint. A well-formed, admissible body
returns `201` with a `CLM-YYYY-NNNNNN` reference. Everything else uses the error
envelope in contract section 5 and the status mapping in section 6.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/api-contract.md` | What the service accepts, returns, and refuses. The authority. |
| `docs/requirements-brief.md` | The open work items and their acceptance criteria. |
| `docs/payload-triage.md` | Day 1 classification of the edge payloads. |
| `data/` | Synthetic policies and notification payloads. |
| `src/claims/` | The service. |
| `src/claims/api/routes.py` | The HTTP surface. |
| `tests/` | Unit tests mirror `src/claims/`. Integration tests exercise HTTP. |
| `Dockerfile` | The runtime image. |

## Working in this repository

You are inside a Linux container. Confirm it before you start:

```
uname -sm     # Linux aarch64
pwd           # /workspaces/claims-intake
```

Dependencies are already installed. There is no install step. If a tool you need
is missing, that is a defect in the image specification and should be reported
rather than worked around.

## Run the service

From the repository root:

```
uv run uvicorn claims.api.routes:app --host 0.0.0.0 --port 8000
```

Submit a notification:

```
curl -X POST http://127.0.0.1:8000/notifications \
  -H "Content-Type: application/json" \
  -d '{
    "policy_number": "MOT-4471",
    "loss_date": "2026-04-02",
    "claim_type": "collision",
    "estimated_amount": "4200.00",
    "description": "Rear ended at a junction."
  }'
```

An accepted notification returns `201` with `claim_reference` and
`"status": "recorded"`. A refused notification returns the contract envelope
(`code`, `message`, `detail`) and is not recorded.

Example payloads live in `data/fnol_valid.json`, `data/fnol_invalid.json`, and
`data/fnol_edge.json`.

## Run the tests

From the repository root:

```
uv run pytest
uv run ruff check .
uv run mypy
```

`uv run pytest tests/integration` runs only the HTTP tests.

## Build the image

```
docker buildx build --platform linux/amd64 -t claims-intake .
```

Then run it:

```
docker run --rm -p 8000:8000 claims-intake
```

The service inside the image is the same `POST /notifications` surface. The
container listens on port 8000.

### Why `--platform linux/amd64`

This development container reports `Linux aarch64`. Docker's default is to build
for the machine that is building. Left alone, that produces a `linux/arm64`
image: it will start here and fail on the hosts this service is actually judged
and deployed on, which are `amd64` (`ubuntu-latest` in GitHub Actions, and the
usual x86_64 server).

`--platform linux/amd64` is the instruction that the image is for that
architecture, not this laptop's. `buildx` will emulate amd64 from this ARM
machine so the result can run where CI and production run. The flag is not a
performance hint and it is not optional documentation of a command you already
typed; it is the difference between an image that only works on the author's
machine and an image that works on the pipeline.

## Data

Everything in `data/` is synthetic and was authored for this program. It contains
no real client data and no named clients.
