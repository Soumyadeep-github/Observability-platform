from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from app.main import create_app, health, SEED

@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'test.sqlite3')) as client:
        yield client

def publication(**overrides):
    return {"eventId": "commit-1", "assetId": "orders", "publishedAt": SEED["now"], "evidenceKind": "sink_commit", **overrides}

def test_seed_and_readiness(client):
    assert client.get('/api/v1/health').json() == {"status": "ok", "mode": "demo"}
    state = client.get('/api/v1/state').json()
    assert len(state['assets']) == 8
    assert {a['id']: a['health'] for a in state['assets']} == {'orders': 'critical', 'revenue': 'critical', 'customers': 'healthy', 'events': 'healthy', 'payments': 'healthy', 'sessions': 'warning', 'inventory': 'unknown', 'dashboard': 'healthy'}

def test_filtering_and_missing_asset(client):
    assets = client.get('/api/v1/assets', params={'q': 'finance', 'status': 'critical'}).json()
    assert [a['id'] for a in assets] == ['revenue']
    assert client.get('/api/v1/assets/missing').status_code == 404
    assert client.get('/api/v1/assets', params={'status': 'invented'}).status_code == 422

def test_freshness_does_not_clear_quality_failure(client):
    assert client.post('/api/v1/publications', json=publication()).status_code == 200
    asset = client.get('/api/v1/assets/orders').json()
    assert asset['health'] == 'critical'
    assert asset['publishedAt'] == '2026-11-01T12:00:00+00:00'
    result = client.post('/api/v1/publications', json=publication(eventId='commit-2', assetId='revenue')).json()
    assert next(a for a in result['state']['assets'] if a['id'] == 'revenue')['health'] == 'healthy'

def test_duplicate_and_conflicting_evidence(client):
    assert not client.post('/api/v1/publications', json=publication()).json()['duplicate']
    assert client.post('/api/v1/publications', json=publication()).json()['duplicate']
    assert client.post('/api/v1/publications', json=publication(assetId='revenue')).status_code == 409
    assert len(client.get('/api/v1/history').json()) == 1

def test_equivalent_timezone_retry(client):
    client.post('/api/v1/publications', json=publication())
    assert client.post('/api/v1/publications', json=publication(publishedAt='2026-11-01T21:00:00+09:00')).json()['duplicate']

def test_old_evidence_does_not_regress_current_state(client):
    client.post('/api/v1/publications', json=publication())
    client.post('/api/v1/publications', json=publication(eventId='old', publishedAt='2026-11-01T10:00:00Z'))
    assert client.get('/api/v1/assets/orders').json()['publishedAt'] == '2026-11-01T12:00:00+00:00'
    assert len(client.get('/api/v1/history').json()) == 2

@pytest.mark.parametrize('override', [{'publishedAt': 'tomorrow'}, {'publishedAt': '2026-11-01T12:00:00'}, {'publishedAt': '2027-01-01T00:00:00Z'}, {'evidenceKind': 'job_success'}, {'eventId': ''}, {'extra': 'unrecognized'}])
def test_invalid_evidence_is_atomic(client, override):
    assert client.post('/api/v1/publications', json=publication(**override)).status_code == 422
    assert client.get('/api/v1/history').json() == []

def test_unknown_asset(client):
    assert client.post('/api/v1/publications', json=publication(assetId='missing')).status_code == 404

def test_incident_transitions_do_not_modify_evidence(client):
    url = '/api/v1/incidents/INC-1042'
    assert client.patch(url, json={'state': 'resolved'}).status_code == 409
    assert client.patch(url, json={'state': 'acknowledged'}).status_code == 200
    assert client.patch(url, json={'state': 'acknowledged'}).status_code == 200
    assert client.patch(url, json={'state': 'resolved'}).status_code == 200
    assert client.patch(url, json={'state': 'acknowledged'}).status_code == 409
    assert client.get('/api/v1/assets/orders').json()['health'] == 'critical'
    assert len(client.get('/api/v1/history').json()) == 2
    assert client.patch('/api/v1/incidents/nope', json={'state': 'resolved'}).status_code == 404

def test_persistence_across_restarts(tmp_path):
    path = tmp_path / 'persistent.sqlite3'
    with TestClient(create_app(path)) as first:
        first.post('/api/v1/publications', json=publication())
        first.patch('/api/v1/incidents/INC-1042', json={'state': 'acknowledged'})
    with TestClient(create_app(path)) as second:
        assert second.get('/api/v1/assets/orders').json()['publishedAt'].endswith('+00:00')
        assert second.get('/api/v1/state').json()['incidents'][0]['state'] == 'acknowledged'
        assert second.post('/api/v1/publications', json=publication()).json()['duplicate']

def test_parallel_retries_have_one_effect(client):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post('/api/v1/publications', json=publication()).json(), range(8)))
    assert sum(not r['duplicate'] for r in results) == 1
    assert len(client.get('/api/v1/history').json()) == 1

def test_reset(client):
    client.post('/api/v1/publications', json=publication())
    client.patch('/api/v1/incidents/INC-1042', json={'state': 'acknowledged'})
    assert client.post('/api/v1/demo/reset').json()['incidents'][0]['state'] == 'open'
    assert client.get('/api/v1/history').json() == []
    assert not client.post('/api/v1/publications', json=publication()).json()['duplicate']

def test_unknown_monitor_and_check_error():
    asset = deepcopy(SEED['assets'][2])
    asset['monitorAvailable'] = False
    assert health(asset, SEED['now']) == 'unknown'
    asset['monitorAvailable'] = True
    asset['checks'][0]['status'] = 'ERROR'
    assert health(asset, SEED['now']) == 'warning'
    asset['checks'][0]['status'] = 'SKIPPED'
    assert health(asset, SEED['now']) == 'healthy'

def test_exact_freshness_boundary():
    asset = deepcopy(SEED['assets'][2])
    asset['freshnessMinutes'] = 12
    assert health(asset, SEED['now']) == 'warning'
    asset['publishedAt'] = '2026-11-01T11:47:59Z'
    assert health(asset, SEED['now']) == 'critical'
