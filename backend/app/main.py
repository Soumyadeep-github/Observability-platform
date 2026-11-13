"""Local proof of concept. Python owns health, transitions and durable evidence.

SQLite and a fixed demo clock deliberately replace the production PostgreSQL
queue and scheduler. No connectors or production authentication are implemented.
"""
import json
import os
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from .columns import project_columns
from .lineage import DEMO_GRAPH, DEMO_COLUMNS, MarquezGateway, RunEventEnvelope
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

SEED = json.loads(Path(__file__).with_name("demo_seed.json").read_text())


def parse_time(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def health(asset, now):
    if not asset["monitorAvailable"] or not asset["publishedAt"]:
        return "unknown"
    age = (parse_time(now) - parse_time(asset["publishedAt"])).total_seconds()
    if age < 0:
        return "unknown"
    if age > asset["freshnessMinutes"] * 60 or any(c["status"] == "FAIL" for c in asset["checks"]):
        return "critical"
    if age > asset["freshnessMinutes"] * 48 or any(c["status"] == "ERROR" for c in asset["checks"]):
        return "warning"
    return "healthy"


class Publication(BaseModel):
    model_config = ConfigDict(extra="forbid")
    eventId: str = Field(min_length=1, max_length=128, pattern=r"^[a-zA-Z0-9_.:-]+$")
    assetId: str = Field(min_length=1, max_length=128)
    publishedAt: AwareDatetime
    evidenceKind: Literal["sink_commit"]


class IncidentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: Literal["acknowledged", "resolved"]


def create_app(db_path=None, marquez_gateway=None):
    app = FastAPI(title="Signal Observability POC", version="1.0.0",
                  description="Local demo: fixed clock, SQLite persistence, no live connectors or authentication.")
    path = str(db_path or os.environ.get("OBSERVABILITY_DB", Path(__file__).parents[1] / "demo.sqlite3"))

    gateway = marquez_gateway or MarquezGateway(os.environ.get("MARQUEZ_URL"))

    def connect():
        conn = sqlite3.connect(path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    with closing(connect()) as conn, conn:
        conn.executescript("""
          CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), document TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS publications (event_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
          CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL);
        """)
        conn.execute("INSERT OR IGNORE INTO state VALUES (1, ?)", (json.dumps(SEED),))

    def read(conn):
        state = json.loads(conn.execute("SELECT document FROM state WHERE id=1").fetchone()[0])
        # Add explicit fixture scope to pre-existing demo stores, retaining triage state.
        definitions = {i['id']: i for i in SEED['incidents']}
        for incident in state['incidents']:
            scope = definitions.get(incident['id'], {}).get('column')
            if scope and 'column' not in incident:
                incident['column'] = scope
        return state

    def save(conn, state):
        conn.execute("UPDATE state SET document=? WHERE id=1", (json.dumps(state),))

    def present(state):
        for asset in state["assets"]:
            asset["health"] = health(asset, state["now"])
        state["mode"] = "demo"
        return state

    @app.get("/api/v1/health")
    def readiness():
        with closing(connect()) as conn:
            conn.execute("SELECT 1 FROM state").fetchone()
        return {"status": "ok", "mode": "demo"}

    @app.get("/api/v1/state")
    def get_state():
        with closing(connect()) as conn:
            return present(read(conn))

    @app.get("/api/v1/assets")
    def list_assets(q: str = Query("", max_length=200), status: Literal["all", "healthy", "warning", "critical", "unknown"] = "all"):
        state = get_state()
        return [a for a in state["assets"] if (status == "all" or a["health"] == status)
                and q.strip().lower() in (a["name"] + " " + a["namespace"] + " " + a["owner"]).lower()]

    @app.get("/api/v1/columns")
    def list_columns(q: str = Query("", max_length=200), status: Literal["all", "healthy", "warning", "critical", "unknown"] = "all", alerts_only: bool = False):
        rows = project_columns(get_state())
        query = q.strip().lower()
        rows = [c for c in rows if query in (c['namespace'] + ' ' + c['dataset'] + ' ' + c['name'] + ' ' + c['owner']).lower()
                and (status == 'all' or c['health'] == status) and (not alerts_only or c['alerts'])]
        return {'columns': rows, 'mode': 'demo', 'coverage': 'Quality health uses explicitly scoped sample checks; table freshness is not inherited'}

    @app.get("/api/v1/assets/{asset_id}")
    def get_asset(asset_id: str):
        asset = next((a for a in get_state()["assets"] if a["id"] == asset_id), None)
        if not asset:
            raise HTTPException(404, "Asset not found")
        return asset

    @app.post("/api/v1/publications")
    def publish(event: Publication):
        payload = event.model_dump(mode="json")
        payload["publishedAt"] = event.publishedAt.astimezone(timezone.utc).isoformat()
        canonical = json.dumps(payload, sort_keys=True)
        with closing(connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            state = read(conn)
            asset = next((a for a in state["assets"] if a["id"] == event.assetId), None)
            if not asset:
                raise HTTPException(404, "Asset not found")
            if event.publishedAt > parse_time(state["now"]):
                raise HTTPException(422, "Publication cannot be after the fixed demo clock")
            previous = conn.execute("SELECT payload FROM publications WHERE event_id=?", (event.eventId,)).fetchone()
            if previous:
                if previous["payload"] != canonical:
                    raise HTTPException(409, "Event ID already used with different evidence")
                return {"eventId": event.eventId, "duplicate": True, "state": present(state)}
            conn.execute("INSERT INTO publications VALUES (?, ?)", (event.eventId, canonical))
            conn.execute("INSERT INTO history(kind, payload) VALUES ('publication', ?)", (canonical,))
            if not asset["publishedAt"] or event.publishedAt >= parse_time(asset["publishedAt"]):
                asset["publishedAt"] = payload["publishedAt"]
                asset["monitorAvailable"] = True
            save(conn, state)
            return {"eventId": event.eventId, "duplicate": False, "state": present(state)}

    @app.patch("/api/v1/incidents/{incident_id}")
    def update_incident(incident_id: str, update: IncidentUpdate):
        with closing(connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            state = read(conn)
            incident = next((i for i in state["incidents"] if i["id"] == incident_id), None)
            if not incident:
                raise HTTPException(404, "Incident not found")
            if incident["state"] == update.state:
                return present(state)
            if (incident["state"], update.state) not in [("open", "acknowledged"), ("acknowledged", "resolved")]:
                raise HTTPException(409, "Acknowledge an open incident before resolving it; resolved incidents are final")
            incident["state"] = update.state
            conn.execute("INSERT INTO history(kind, payload) VALUES ('incident', ?)", (json.dumps({"id": incident_id, "state": update.state}),))
            save(conn, state)
            return present(state)

    @app.get("/api/v1/lineage")
    def lineage(asset_id: str = Query("", max_length=128), depth: int = Query(6, ge=1, le=10)):
        state = get_state()
        asset = next((a for a in state["assets"] if a["id"] == (asset_id or "dashboard")), None)
        if not asset:
            raise HTTPException(404, "Asset not found")
        if gateway.configured:
            node_id = "dataset:" + asset["namespace"] + ":" + asset["name"]
            result = gateway.graph(node_id, depth)
            return {**result, "mode": "live", "provider": "Marquez", "coverage": "Run-derived table lineage; completeness depends on producers", "focusId": node_id}
        # Offline graph fixture only. Never build a second lineage store here.
        result = json.loads(json.dumps(DEMO_GRAPH))
        if asset_id:
            node_id = "dataset:" + asset["namespace"] + ":" + asset["name"]
            visited = {node_id}
            edges = [e for n in result["graph"] for e in n["outEdges"]]
            for _ in range(depth):
                neighbors = {e["origin"] for e in edges if e["destination"] in visited} | {e["destination"] for e in edges if e["origin"] in visited}
                visited |= neighbors
            result["graph"] = [n for n in result["graph"] if n["id"] in visited]
        return {**result, "mode": "demo", "provider": "Marquez graph fixture", "coverage": "Sample RunEvents generated with the OpenLineage Python SDK; not live ingestion"}

    @app.get("/api/v1/dataset-details")
    def dataset_details(namespace: str = Query(..., min_length=1, max_length=1024), name: str = Query(..., min_length=1, max_length=1024)):
        if gateway.configured:
            return {**gateway.dataset(namespace, name), "mode": "live", "provider": "Marquez"}
        asset = next((a for a in get_state()['assets'] if a['namespace'] == namespace and a['name'] == name), None)
        if not asset:
            raise HTTPException(404, "Dataset not found")
        return {"namespace": namespace, "name": name, "description": asset['description'], "fields": asset['columns'], "mode": "demo", "provider": "Sample schema"}

    @app.get("/api/v1/column-lineage")
    def column_lineage(namespace: str = Query(..., min_length=1, max_length=1024), name: str = Query(..., min_length=1, max_length=1024), field: str = Query("", max_length=1024), depth: int = Query(6, ge=1, le=10)):
        if gateway.configured:
            root = f"datasetField:{namespace}:{name}:{field}" if field else f"dataset:{namespace}:{name}"
            return {**gateway.column_graph(root, depth), "mode": "live", "provider": "Marquez", "coverage": "Column mappings reported by producers; absence of edges does not imply no dependency"}
        dataset = dataset_details(namespace, name)
        if field and not any(c['name'] == field for c in dataset['fields']):
            raise HTTPException(404, "Column not found")
        graph = json.loads(json.dumps(DEMO_COLUMNS))
        visited = {n['id'] for n in graph['graph'] if n['data']['namespace'] == namespace and n['data']['dataset'] == name and (not field or n['data']['field'] == field)}
        edges = [e for n in graph['graph'] for e in n['outEdges']]
        for _ in range(depth):
            visited |= {e['origin'] for e in edges if e['destination'] in visited} | {e['destination'] for e in edges if e['origin'] in visited}
        graph['graph'] = [n for n in graph['graph'] if n['id'] in visited]
        return {**graph, "mode": "demo", "provider": "Explicit OpenLineage columnLineage facet fixtures", "coverage": "Illustrative column mappings from SDK-generated facets; not discovered from real queries"}

    @app.post("/api/v1/lineage")
    async def ingest_lineage(request: Request):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1_000_000:
                raise HTTPException(413, "OpenLineage event exceeds the POC limit")
        try:
            payload = json.loads(body)
            RunEventEnvelope.model_validate(payload)
        except (ValueError, TypeError) as exc:
            raise HTTPException(422, "Expected an OpenLineage RunEvent envelope") from exc
        # Acknowledgment follows the upstream Marquez response; no invented local receipt.
        await run_in_threadpool(gateway.request, "POST", payload=payload)
        return {"status": "forwarded", "provider": "Marquez"}

    @app.get("/api/v1/history")
    def history(limit: int = Query(50, ge=1, le=100)):
        with closing(connect()) as conn:
            return [{"id": r["id"], "kind": r["kind"], "data": json.loads(r["payload"])}
                    for r in conn.execute("SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,))]

    @app.post("/api/v1/demo/reset")
    def reset():
        with closing(connect()) as conn, conn:
            conn.execute("BEGIN IMMEDIATE")
            save(conn, SEED)
            conn.execute("DELETE FROM publications")
            conn.execute("DELETE FROM history")
        return present(json.loads(json.dumps(SEED)))

    frontend_dist = Path(__file__).parents[2] / "frontend" / "dist"
    if frontend_dist.is_dir():
        app.mount("/assets", StaticFiles(directory=frontend_dist / "assets"), name="frontend-assets")

        @app.get("/", include_in_schema=False)
        def frontend():
            return FileResponse(frontend_dist / "index.html")

    return app
