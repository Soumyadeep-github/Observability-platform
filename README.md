# Data observability platform

Open the delivery board to see which assets published on time, which upstream partition is outstanding, and what evidence supports each conclusion. The board refreshes every 15 seconds while visible. Each workspace starts empty. Register a workload using the ingestion API or load the synthetic reference chain below.

## Run locally

From the repository root with Python 3.12, create a new workspace credential and run the service.

```sh
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements-live.txt
export OBS_TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export OBS_IDENTITIES="$(.venv/bin/python -c 'import json,os;print(json.dumps({os.environ["OBS_TOKEN"]:{"workspace":"sandbox","role":"writer"}}))')"
export OBS_API=http://127.0.0.1:8000
.venv/bin/python scripts/serve.py
```

Open the board at `http://127.0.0.1:8000` and paste the token from your local shell. The board retains it in page memory. Interactive ingestion schemas are at `/docs`. To load the example, run `.venv/bin/python scripts/load_reference.py` in a shell with the same `OBS_TOKEN` and `OBS_API`. It creates an observed landing partition, a completed job, a published warehouse asset with a failed volume check, an incident, and a separate asset awaiting evidence.

## Containers and Kubernetes

```sh
docker build -t observability:local .
docker volume create observability-data
docker run --rm -p 127.0.0.1:8000:8000 -e OBS_IDENTITIES -v observability-data:/data observability:local
```

For Kubernetes, point `DATABASE_URL` at a reachable PostgreSQL database with TLS and a user allowed to create application tables. Provision the target database first. Use a managed or replicated database and replicas on independent nodes for production availability. The local volume example uses SQLite for a single process.

```sh
kind load docker-image observability:local
kubectl create secret generic observability-config --from-literal=DATABASE_URL="$DATABASE_URL" --from-literal=OBS_IDENTITIES="$OBS_IDENTITIES"
kubectl apply -f deploy/live.yaml
kubectl port-forward svc/observability 8000:8000
```

Use a registry image reference when deploying beyond a local cluster. Configure TLS at the ingress. The host and port default to loopback and 8000 for the local launcher and all interfaces and 8000 for the image. Override with `OBS_HOST` and `OBS_PORT`.

## Ingest and inspect

Send a workspace writer bearer token and a stable `Idempotency-Key` on writes. Matching retries have one effect, and reusing a key with different content returns 409. Assets and checks upsert by identity. Schema snapshots and results append observations. Submit corrections as new observations and retain the originals. Publications use their required `eventId` as the key. Unknown assets acquire a provisional identity. Register an asset with the same ID to supply its namespace, owner, and freshness target.

| POST path under `/api/v1` | Observable fact |
|---|---|
| assets, schemas | Asset identity and versioned schema |
| checks, results | Dataset or column check definitions and timestamped outcomes |
| publications, partitions | Committed output or observed object inventory |
| lineage, edges | Native run events, directed dependencies and column transformations |
| incidents, alerts | Open an incident or receive an external alert observation |

Use `PATCH /api/v1/incidents/{id}` for acknowledge and resolve. Severity is `info` for context, `warning` for investigation and `critical` for urgent response. Read through `/api/v1/views/{name}` or the corresponding MCP tool. All ten views support search and paging. Lineage supports asset, column, depth and direction. Point-in-time shows the evidence received through an explicit timestamp. The OpenAPI contract documents inputs.

- [Release scope, integrations, indicators and capacity](docs/design/release1_design.md)
- [Caller identity and agent access](docs/design/security_design.md)
- [Editable diagram](docs/design/diagrams/release1_architecture.drawio) and [offline browser viewer](docs/design/diagrams/release1_viewer.html)
- [Contributors](CONTRIBUTORS.md) and [license](LICENSE)

The historical seeded POC is selectable in a separate local process with `OBS_MODE=demo` and the legacy UI build. Keep that unauthenticated demonstration bound to loopback. Its data file and the live database are separate. See the [historical POC guide](docs/releases/demo-guide.md).
