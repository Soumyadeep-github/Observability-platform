import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.lineage import DEMO_GRAPH, MarquezGateway, RunEventEnvelope

EVENTS = json.loads((Path(__file__).parents[1] / 'app/demo_openlineage.json').read_text())


def test_demo_graph_uses_dataset_job_dataset_objects(tmp_path):
    with TestClient(create_app(tmp_path / 'demo.sqlite3', MarquezGateway(None))) as client:
        response = client.get('/api/v1/lineage').json()
        assert response['mode'] == 'demo'
        assert len(response['graph']) == 11
        objects = {n['id']: n for n in response['graph']}
        assert sum(n['type'] == 'JOB' for n in objects.values()) == 3
        for node in objects.values():
            for edge in node['outEdges']:
                assert objects[edge['origin']]['type'] != objects[edge['destination']]['type']
        focused = client.get('/api/v1/lineage', params={'asset_id': 'orders', 'depth': 1}).json()
        assert {n['type'] for n in focused['graph']} == {'DATASET', 'JOB'}
        assert client.get('/api/v1/lineage', params={'asset_id': 'missing'}).status_code == 404
        assert client.get('/api/v1/lineage', params={'depth': 100}).status_code == 422


def test_official_sdk_event_fixtures_have_valid_envelopes():
    for event in EVENTS:
        envelope = RunEventEnvelope.model_validate(event)
        assert envelope.eventType == 'COMPLETE'
        assert len(envelope.inputs) >= 1
        assert len(envelope.outputs) == 1
        assert 'schema' in event['outputs'][0]['facets']
        assert event['schemaURL'].endswith('/OpenLineage.json#/$defs/RunEvent')


def test_no_fake_ingestion_success_without_marquez(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite3', MarquezGateway(None))) as client:
        assert client.post('/api/v1/lineage', json=EVENTS[0]).status_code == 503
        assert client.post('/api/v1/lineage', json={'job': {}}).status_code == 422
        assert client.post('/api/v1/lineage', content=b'x' * 1_000_001).status_code == 413


def test_marquez_adapter_queries_native_endpoint_and_preserves_graph(tmp_path):
    received = []
    def handler(request):
        received.append(request)
        return httpx.Response(200, json=DEMO_GRAPH)
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(handler))
    with TestClient(create_app(tmp_path / 'test.sqlite3', gateway)) as client:
        result = client.get('/api/v1/lineage', params={'asset_id': 'orders', 'depth': 4}).json()
    assert result['mode'] == 'live'
    assert received[0].url.path == '/api/v1/lineage'
    assert received[0].url.params['nodeId'] == 'dataset:analytics.commerce:fct_orders'
    assert received[0].url.params['depth'] == '4'
    assert result['graph'][0]['data']['fields'] == DEMO_GRAPH['graph'][0]['data']['fields']


def test_forwarding_preserves_unknown_facets_and_does_not_change_health(tmp_path):
    event = json.loads(json.dumps(EVENTS[0]))
    event['run']['facets']['custom_evidence'] = {'arbitrary': [1, 2], '_schemaURL': 'http://metadata.test/do-not-fetch'}
    received = []
    def handler(request):
        received.append(json.loads(request.content))
        return httpx.Response(200)
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(handler))
    with TestClient(create_app(tmp_path / 'test.sqlite3', gateway)) as client:
        original = client.get('/api/v1/assets/revenue').json()
        assert client.post('/api/v1/lineage', json=event).json()['status'] == 'forwarded'
        assert client.get('/api/v1/assets/revenue').json() == original
    assert received == [event]


@pytest.mark.parametrize('status,expected', [(500, 503), (302, 503), (400, 400), (401, 502)])
def test_marquez_failures_are_visible_without_demo_fallback(tmp_path, status, expected):
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(lambda _: httpx.Response(status)))
    with TestClient(create_app(tmp_path / 'test.sqlite3', gateway)) as client:
        assert client.get('/api/v1/lineage').status_code == expected


@pytest.mark.parametrize('payload', [{'graph': [{'id': 'bad'}]}, {'graph': []}])
def test_invalid_and_empty_upstream_graph(tmp_path, payload):
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(lambda _: httpx.Response(200, json=payload)))
    with TestClient(create_app(tmp_path / 'test.sqlite3', gateway)) as client:
        response = client.get('/api/v1/lineage')
        assert response.status_code == (200 if not payload['graph'] else 502)


def test_timeout_is_sanitized(tmp_path):
    def handler(request):
        raise httpx.ConnectError('private upstream detail', request=request)
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(handler))
    with TestClient(create_app(tmp_path / 'test.sqlite3', gateway)) as client:
        response = client.get('/api/v1/lineage')
        assert response.status_code == 503
        assert 'private upstream detail' not in response.text


def test_rejects_url_credentials():
    with pytest.raises(ValueError):
        MarquezGateway('https://user:secret@marquez.test')


def test_dataset_schema_and_explicit_column_chain(tmp_path):
    with TestClient(create_app(tmp_path / 'schema.sqlite3', MarquezGateway(None))) as client:
        identity = {'namespace': 'analytics.finance', 'name': 'daily_revenue'}
        schema = client.get('/api/v1/dataset-details', params=identity).json()
        assert schema['fields'][0] == {'name': 'id', 'type': 'STRING', 'nullable': False}
        graph = client.get('/api/v1/column-lineage', params={**identity, 'field': 'amount'}).json()
        assert {n['data']['field'] for n in graph['graph']} == {'amount'}
        assert {n['data']['dataset'] for n in graph['graph']} == {'fct_orders', 'daily_revenue', 'executive_metrics'}
        assert len([e for n in graph['graph'] for e in n['outEdges']]) == 2
        revenue = next(n for n in graph['graph'] if n['data']['dataset'] == 'daily_revenue')
        assert revenue['data']['transformationDescription'] == 'SUM(amount)'
        assert client.get('/api/v1/column-lineage', params={**identity, 'field': 'not_a_column'}).status_code == 404
        assert client.get('/api/v1/dataset-details', params={**identity, 'name': 'missing'}).status_code == 404


def test_explicit_multi_input_column_and_unrelated_same_named_columns(tmp_path):
    with TestClient(create_app(tmp_path / 'multi.sqlite3', MarquezGateway(None))) as client:
        result = client.get('/api/v1/column-lineage', params={'namespace': 'analytics.reporting', 'name': 'executive_metrics', 'field': 'region'}).json()
        target = next(n for n in result['graph'] if n['data']['dataset'] == 'executive_metrics')
        assert len(target['inEdges']) == 2
        assert 'dim_customers' in {n['data']['dataset'] for n in result['graph']}
        assert 'payments' not in {n['data']['dataset'] for n in result['graph']}
        isolated = client.get('/api/v1/column-lineage', params={'namespace': 'supply_chain.public', 'name': 'inventory_snapshot', 'field': 'amount'}).json()
        assert len(isolated['graph']) == 1
        assert isolated['graph'][0]['outEdges'] == []


def test_fixture_column_edges_are_from_official_openlineage_facets():
    from app.lineage import DEMO_COLUMNS
    expected = set()
    for event in EVENTS:
        for output in event['outputs']:
            for field, mapping in output['facets']['columnLineage']['fields'].items():
                for source in mapping['inputFields']:
                    expected.add((f"datasetField:{source['namespace']}:{source['name']}:{source['field']}", f"datasetField:{output['namespace']}:{output['name']}:{field}"))
    actual = {(e['origin'], e['destination']) for n in DEMO_COLUMNS['graph'] for e in n['outEdges']}
    assert actual == expected
    assert len(actual) == 13


def test_live_schema_supports_datasets_outside_local_catalog(tmp_path):
    received = []
    def handler(request):
        received.append(request)
        return httpx.Response(200, json={'namespace': 'external', 'name': 'uncatalogued/orders', 'fields': [{'name': 'customer_id', 'type': None}]})
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(handler))
    with TestClient(create_app(tmp_path / 'live.sqlite3', gateway)) as client:
        result = client.get('/api/v1/dataset-details', params={'namespace': 'external', 'name': 'uncatalogued/orders'}).json()
    assert result['mode'] == 'live'
    assert result['fields'][0]['nullable'] is None
    assert received[0].url.raw_path.endswith(b'/datasets/uncatalogued%2Forders')


def test_live_column_adapter_uses_native_endpoint_and_downstream_parameter(tmp_path):
    from app.lineage import DEMO_COLUMNS
    received = []
    def handler(request):
        received.append(request)
        return httpx.Response(200, json=DEMO_COLUMNS)
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(handler))
    with TestClient(create_app(tmp_path / 'livecol.sqlite3', gateway)) as client:
        response = client.get('/api/v1/column-lineage', params={'namespace': 'external', 'name': 'new.table', 'field': 'total', 'depth': 3})
    assert response.status_code == 200
    assert received[0].url.path == '/api/v1/column-lineage'
    assert received[0].url.params['nodeId'] == 'datasetField:external:new.table:total'
    assert received[0].url.params['withDownstream'] == 'true'
    assert received[0].url.params['depth'] == '3'
    assert response.json()['mode'] == 'live'


@pytest.mark.parametrize('route', ['/api/v1/dataset-details', '/api/v1/column-lineage'])
def test_live_dataset_explorer_failures_do_not_fall_back(tmp_path, route):
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(lambda _: httpx.Response(500)))
    with TestClient(create_app(tmp_path / 'failed.sqlite3', gateway)) as client:
        result = client.get(route, params={'namespace': 'analytics.finance', 'name': 'daily_revenue'})
        assert result.status_code == 503


def test_invalid_live_column_response_is_rejected(tmp_path):
    gateway = MarquezGateway('http://marquez.test', httpx.MockTransport(lambda _: httpx.Response(200, json={'graph': [{'id': 'malformed'}]})))
    with TestClient(create_app(tmp_path / 'invalid.sqlite3', gateway)) as client:
        assert client.get('/api/v1/column-lineage', params={'namespace': 'n', 'name': 'd'}).status_code == 502
