import json
from copy import deepcopy
import sqlite3

from fastapi.testclient import TestClient
from app.main import create_app, SEED
from app.columns import project_columns


def test_column_health_does_not_inherit_table_freshness_or_alerts(tmp_path):
    with TestClient(create_app(tmp_path / 'columns.sqlite3')) as client:
        result = client.get('/api/v1/columns').json()
        rows = {c['id']: c for c in result['columns']}
        assert len(rows) == 32
        assert rows['orders:amount']['health'] == 'critical'
        assert rows['sessions:amount']['health'] == 'warning'
        assert rows['orders:created_at']['health'] == 'unknown'
        assert rows['inventory:id']['health'] == 'unknown'
        assert rows['revenue:amount']['health'] == 'healthy'
        assert client.get('/api/v1/assets/revenue').json()['health'] == 'critical'
        assert [i['id'] for i in rows['orders:amount']['alerts']] == ['INC-1041']
        assert rows['orders:id']['alerts'] == []
        assert rows['revenue:amount']['alerts'] == []


def test_filters_and_triage_preserve_quality_health(tmp_path):
    with TestClient(create_app(tmp_path / 'triage.sqlite3')) as client:
        only_alerts = client.get('/api/v1/columns', params={'alerts_only': True}).json()['columns']
        assert {c['id'] for c in only_alerts} == {'orders:amount', 'sessions:amount'}
        client.patch('/api/v1/incidents/INC-1041', json={'state':'acknowledged'})
        result = client.get('/api/v1/columns', params={'q':'fct_orders amount'}).json()['columns']
        assert len(result) == 1
        assert result[0]['alerts'][0]['state'] == 'acknowledged'
        client.patch('/api/v1/incidents/INC-1041', json={'state':'resolved'})
        result = client.get('/api/v1/columns', params={'status':'critical'}).json()['columns']
        assert result[0]['health'] == 'critical'
        assert result[0]['alerts'] == []
        assert client.get('/api/v1/columns', params={'status':'invented'}).status_code == 422


def test_no_evaluated_checks_and_monitor_errors_are_distinct():
    state = deepcopy(SEED)
    state['assets'][0]['checks'] = [{'id':'one','name':'one','column':'amount','status':'SKIPPED','value':'Skipped'}]
    rows = {c['id']: c for c in project_columns(state)}
    assert rows['orders:amount']['health'] == 'unknown'
    state['assets'][0]['checks'][0]['status'] = 'ERROR'
    rows = {c['id']: c for c in project_columns(state)}
    assert rows['orders:amount']['health'] == 'warning'
    state['assets'][0]['checks'][0]['status'] = 'FAIL'
    rows = {c['id']: c for c in project_columns(state)}
    assert rows['orders:amount']['health'] == 'critical'


def test_older_demo_store_gains_explicit_scope_without_resetting_triage(tmp_path):
    path = tmp_path / 'old.sqlite3'
    create_app(path)
    state = deepcopy(SEED)
    for incident in state['incidents']:
        incident.pop('column', None)
        if incident['id'] == 'INC-1041': incident['state'] = 'acknowledged'
    with sqlite3.connect(path) as connection:
        connection.execute('UPDATE state SET document=? WHERE id=1', (json.dumps(state),))
    with TestClient(create_app(path)) as client:
        column = next(c for c in client.get('/api/v1/columns').json()['columns'] if c['id'] == 'orders:amount')
        assert column['alerts'][0]['state'] == 'acknowledged'
        assert column['alerts'][0]['column'] == 'amount'
