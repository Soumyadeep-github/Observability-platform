# Marquez and OpenLineage integration

The TypeScript UI renders a flow of **dataset → job → dataset**, preserving Marquez IDs and edges. Jobs are explicit objects. Edges come only from the returned graph. Layout and routed edge coordinates reuse Marquez's Apache-2.0 `useLayout` module (0.50.0, commit `4984ca939b3a6f59e1092c6397702eb1e53ff1cc`) with ELK; D3 provides zoom/pan. Rendering cards and integration controls belong to this project. This is not a fork of the full Marquez web application.

Upstream code and local modifications are documented in `frontend/src/vendor/marquez/NOTICE.md`, alongside the original license.

## Modes

**Without `MARQUEZ_URL`:** an explicitly labeled offline graph fixture is returned. Three standard RunEvents are generated with the official `openlineage-python==1.30.0` SDK, including schema facets. `scripts/generate_lineage_demo.py` generates those events and the corresponding offline graph fixture from the seed assets. This fixture is not evidence that Marquez ingested anything. Demo jobs are illustrative transformations, not real pipeline executions. Isolated datasets have no invented relationships.

**With `MARQUEZ_URL`:** Python reads the real Marquez `/api/v1/lineage?nodeId=dataset:<namespace>:<name>&depth=N` endpoint. The UI focus selector maps the POC's asset identities to Marquez IDs. The default root is `executive_metrics`. A missing graph or unavailable service remains empty/an error; it never falls back to the demo fixture. Producer identities must match the asset namespace and name. This version queries only assets already in the POC catalog; it does not discover arbitrary Marquez datasets into that catalog.

`POST /api/v1/lineage` forwards a native OpenLineage RunEvent unchanged to Marquez. The Python envelope check validates basic identity, UUID, timestamp and array bounds; Marquez validates and processes the full specification. Unknown facets survive forwarding and schema URLs are never fetched by the application. No success is returned unless Marquez responds successfully. With no Marquez configuration, ingestion returns 503. This ingress does not implement DatasetEvent/JobEvent, a local durable inbox, producer authentication or tenant authorization. The local application server must not be exposed as a production ingest endpoint.

Marquez is the optional upstream lineage store; this application does not add its own lineage database or graph traversal engine for live data. Existing SQLite publication/incident state stays separate: an OpenLineage COMPLETE event does not automatically constitute committed-publication evidence.

## Optional local upstream stack

Docker is not installed on the development machine, so this compose profile has **not been run or integration-verified** here. Adapter contract tests use HTTPX MockTransport. Image/platform availability and real source instrumentation must be validated before claiming end-to-end compatibility.

On a Docker-capable machine, from the repository root:

```sh
docker compose -f deploy/compose.marquez.yml up -d
# Wait for the Marquez admin health check to succeed:
curl --fail http://127.0.0.1:5003/healthcheck
MARQUEZ_URL=http://127.0.0.1:5002 .venv/bin/python scripts/seed_marquez.py
# Stop any existing local POC server first, then start with live lineage:
MARQUEZ_URL=http://127.0.0.1:5002 python3 scripts/serve.py
```

- POC UI: http://127.0.0.1:8000 → Lineage
- Marquez's full native web UI (also reused through its official image): http://127.0.0.1:3000
- Marquez API: http://127.0.0.1:5002
- Marquez admin: http://127.0.0.1:5003

All host ports are loopback-only. Credentials in the compose profile are disposable local-demo credentials. The upstream Marquez API has no authentication by default. The PostgreSQL volume survives container restart; `docker compose -f deploy/compose.marquez.yml down` keeps that volume. Do not add `-v` unless intentionally deleting the sample lineage store.

Only the lineage panel becomes live with this configuration. Overview metrics, freshness, quality and connector cards remain the POC's sample data and are not automatically reconciled from Marquez.

## Reuse boundaries and references

- Marquez graph module: https://github.com/MarquezProject/marquez/tree/0.50.0/web/libs/graph
- Marquez native graph/ingress API contract: https://github.com/MarquezProject/marquez/blob/0.50.0/spec/openapi.yml
- Marquez deployment: https://marquezproject.ai/docs/deployment/
- Official OpenLineage Python client: https://openlineage.io/docs/client/python/

Dataset headers on Lineage now expand schema fields directly inside their graph nodes, including datasets returned by Marquez that are outside the local catalog. The explorer reads `GET /api/v1/dataset-details?namespace=…&name=…`, which queries the native Marquez dataset endpoint in live mode. Missing types and nullability are shown as unknown/not reported rather than inferred.

The **Column lineage** tab and per-field **Trace column** actions read `GET /api/v1/column-lineage?namespace=…&name=…&field=…&depth=6`. In live mode, this delegates to Marquez `/api/v1/column-lineage` with a native dataset/datasetField ID and `withDownstream=true`. The visual field graph preserves upstream IDs and edges, and displays reported transformation descriptions/types. Schema and column errors remain visible; they never use a sample-data fallback for a configured live service.

The offline demo includes 13 explicit mapping edges generated from OpenLineage `columnLineage` output facets, including SUM and timestamp transformations and a two-input COALESCE example. These are illustrative mappings, not query-derived evidence. Identically named unrelated columns are never connected automatically. No-mapping cases are shown explicitly. Real service compatibility is still pending Docker-based verification. Live history, column mappings and producer coverage depend on actual upstream instrumentation. The Marquez baseline is pinned for reproducibility; upgrading is a separate compatibility and dependency-review step.


## Retained column health API

There is no standalone Columns page or navigation tab. Asset schema trace actions and column-scoped incident links focus the dataset and selected field on Lineage. The backend `GET /api/v1/columns` projection is retained for future health/alert integration; it does not create a separate UI workflow. Its sample quality health remains independent of dataset freshness, and only explicitly scoped incidents count as column alerts. Alert rule configuration and live column health collection remain future work.

## In-graph exploration

On **Lineage**, click a dataset header to expand its schema inside the graph node. Several datasets can remain expanded; large schemas scroll within their card. Clicking the header again collapses it. Schema errors and retry controls stay inside that node.

Selecting a column keeps the current graph in place. The UI queries its reported column mappings and traverses input and output edges separately. Upstream datasets are green, downstream datasets blue, the selected dataset purple, and datasets participating in both directions have a separate legend color. Unrelated datasets fade. Jobs and edges provide connecting graph context; they are not additional field-level provenance claims. Related upstream and downstream datasets expand automatically when a column is selected. Every matching field row receives a directional highlight; collapsing and reopening a dataset preserves it. Long schemas scroll the first highlighted field into view. The camera waits for schema expansion before fitting the relevant path, while preserving the current view during loading. Manual zoom and pan remain available.

A co-input to a downstream join is not treated as downstream impact of the selected field. Node IDs and full namespace/dataset/field identities are preserved, traversal terminates on cycles, missing mappings stay explicitly unknown, and stale asynchronous responses cannot replace a newer selection. Selecting a field does not open a dataset dialog or leave the graph. Connectors use a single cubic Bézier sweep between ports, with wider spacing between graph layers and small open arrowheads whose size does not grow with stroke thickness. Aligned links remain straight; offset links turn gradually instead of following tight orthogonal elbows.
