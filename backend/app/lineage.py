"""Marquez HTTP adapter. Marquez owns OpenLineage validation, storage and graph traversal."""
import json
from pathlib import Path
from typing import Literal, Optional
from urllib.parse import urlsplit, quote
from uuid import UUID

import httpx
from fastapi import HTTPException
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field


class Identity(BaseModel):
    model_config = ConfigDict(extra='allow')
    namespace: str = Field(min_length=1, max_length=1024)
    name: str = Field(min_length=1, max_length=1024)


class RunIdentity(BaseModel):
    model_config = ConfigDict(extra='allow')
    runId: UUID


class RunEventEnvelope(BaseModel):
    """Bounded RunEvent envelope only; Marquez validates the full specification.

    Extra facets/extensions survive forwarding. Schema URLs are metadata and are
    never fetched by this application. DatasetEvent/JobEvent are not supported by
    this POC ingress; it intentionally accepts RunEvents only.
    """
    model_config = ConfigDict(extra='allow')
    eventType: Literal['START', 'RUNNING', 'COMPLETE', 'ABORT', 'FAIL', 'OTHER']
    eventTime: AwareDatetime
    producer: str = Field(min_length=1, max_length=2048)
    schemaURL: str = Field(min_length=1, max_length=2048)
    run: RunIdentity
    job: Identity
    inputs: list[Identity] = Field(default_factory=list, max_length=100)
    outputs: list[Identity] = Field(default_factory=list, max_length=100)


class GraphEdge(BaseModel):
    model_config = ConfigDict(extra='allow')
    origin: str
    destination: str


class GraphObject(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    type: Literal['DATASET', 'JOB']
    data: Identity
    inEdges: list[GraphEdge]
    outEdges: list[GraphEdge]


class MarquezGraph(BaseModel):
    model_config = ConfigDict(extra='allow')
    graph: list[GraphObject] = Field(max_length=200)


class SchemaField(BaseModel):
    model_config = ConfigDict(extra='allow')
    name: str = Field(min_length=1)
    type: Optional[str] = None
    description: Optional[str] = None
    nullable: Optional[bool] = None


class DatasetDetails(Identity):
    fields: list[SchemaField] = Field(default_factory=list, max_length=500)
    description: Optional[str] = None


class ColumnData(BaseModel):
    model_config = ConfigDict(extra='allow')
    namespace: str
    dataset: str
    field: str
    fieldType: Optional[str] = None
    transformationType: Optional[str] = None
    transformationDescription: Optional[str] = None


class ColumnObject(BaseModel):
    model_config = ConfigDict(extra='allow')
    id: str
    type: str
    data: ColumnData
    inEdges: list[GraphEdge]
    outEdges: list[GraphEdge]


class ColumnGraph(BaseModel):
    graph: list[ColumnObject] = Field(max_length=200)


class MarquezGateway:
    def __init__(self, base_url: Optional[str], transport=None):
        self.base_url = base_url.rstrip('/') if base_url else None
        if self.base_url:
            parts = urlsplit(self.base_url)
            if parts.scheme not in {'http', 'https'} or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                raise ValueError('MARQUEZ_URL must be an HTTP(S) service URL without credentials, query or fragment')
        self.transport = transport

    @property
    def configured(self):
        return self.base_url is not None

    def request(self, method, *, params=None, payload=None, path="/api/v1/lineage"):
        if not self.configured:
            raise HTTPException(503, 'Marquez is not configured. Set MARQUEZ_URL to ingest OpenLineage RunEvents.')
        try:
            with httpx.Client(transport=self.transport, timeout=10, follow_redirects=False, trust_env=False) as client:
                with client.stream(method, self.base_url + path, params=params, json=payload) as response:
                    if response.status_code >= 500 or 300 <= response.status_code < 400:
                        raise HTTPException(503, 'Marquez is unavailable; no demo fallback was substituted')
                    if response.status_code >= 400:
                        status = response.status_code if response.status_code in {400, 404, 409, 413, 422, 429} else 502
                        raise HTTPException(status, 'Marquez rejected the lineage request')
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 2_000_000:
                            raise HTTPException(502, 'Marquez response exceeds the POC limit')
                    return json.loads(body) if body else {}
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(503, 'Could not read Marquez lineage') from exc

    def dataset(self, namespace, name):
        value = self.request('GET', path='/api/v1/namespaces/' + quote(namespace, safe='') + '/datasets/' + quote(name, safe=''))
        try:
            return DatasetDetails.model_validate(value).model_dump(mode='json')
        except ValueError as exc:
            raise HTTPException(502, 'Marquez returned an invalid dataset schema') from exc

    def column_graph(self, node_id, depth):
        value = self.request('GET', path='/api/v1/column-lineage', params={'nodeId': node_id, 'depth': depth, 'withDownstream': 'true'})
        try:
            graph = ColumnGraph.model_validate(value)
            if len({n.id for n in graph.graph}) != len(graph.graph):
                raise ValueError('Duplicate column IDs')
            return graph.model_dump(mode='json')
        except ValueError as exc:
            raise HTTPException(502, 'Marquez returned an invalid column lineage graph') from exc

    def graph(self, node_id, depth):
        value = self.request('GET', params={'nodeId': node_id, 'depth': depth})
        try:
            graph = MarquezGraph.model_validate(value)
            ids = {n.id for n in graph.graph}
            if len(ids) != len(graph.graph):
                raise ValueError('Duplicate graph IDs')
            # Boundary edges are allowed by upstream; the renderer includes only returned endpoints.
            return graph.model_dump(mode='json')
        except ValueError as exc:
            raise HTTPException(502, 'Marquez returned an unsupported graph response') from exc


DEMO_GRAPH = json.loads(Path(__file__).with_name('demo_lineage.json').read_text())

DEMO_COLUMNS = json.loads(Path(__file__).with_name('demo_columns.json').read_text())
