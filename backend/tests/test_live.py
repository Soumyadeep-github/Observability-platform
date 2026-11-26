import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from fastapi.testclient import TestClient
from app.live import live_app
from app.views import VIEWS
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'scripts'))
from load_reference import records

class LiveWorkload(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.now=datetime(2026,11,1,7,tzinfo=timezone.utc)
        self.db=Path(self.tmp.name)/'local.db'
        keys={'a':dict(workspace='a',role='writer'),'b':dict(workspace='b',role='reader')}
        self.app=lambda:live_app(self.db,clock=lambda:self.now,credentials=keys)
        self.client=TestClient(self.app(),headers={'Authorization':'Bearer a'})
    def submit(self,route,data,key):
        return self.client.post('/api/v1/'+route,json=data,headers={'Idempotency-Key':key})
    def test_workload_and_contract(self):
        for i,(route,data) in enumerate(records(self.now)):
            key=data.get('eventId',str(i))
            self.assertEqual(self.submit(route,data,key).status_code,200,route)
            self.assertTrue(self.submit(route,data,key).json()['duplicate'])
        self.client=TestClient(self.app(),headers={'Authorization':'Bearer a'})
        for name,fields in VIEWS.items():
            query={'asset_id':'summary'} if name=='lineage' else {}
            payload=self.client.get('/api/v1/views/'+name,params=query).json()
            self.assertTrue(payload['rows'],name)
            response=self.client.post('/mcp',json=dict(jsonrpc='2.0',id=1,method='tools/call',params=dict(name=name,arguments=query))).json()['result']['structuredContent']
            self.assertEqual(payload,response)
            for row in response['rows']:
                self.assertTrue(set(payload['fields']).issubset(row))
        self.assertEqual(self.client.get('/api/v1/views/assets',headers={'Authorization':'Bearer b'}).json()['rows'],[])
        self.assertEqual(self.client.post('/api/v1/assets',headers={'Authorization':'Bearer b'}).status_code,403)
    def test_edge_direction(self):
        for i,target in enumerate(['target','sibling']):
            self.submit('edges',dict(origin='raw',destination=target,sourceColumn='x',targetColumn='y',provenance='declared',transformation=target),str(i)).raise_for_status()
        rows=self.client.get('/api/v1/column-lineage',params=dict(asset_id='target',field='y')).json()['rows']
        self.assertEqual([r['destination'] for r in rows],['target'])
    def test_publication_and_conflict(self):
        p=dict(assetId='new',eventId='commit',publishedAt=self.now.isoformat(),evidenceKind='sink_commit')
        self.submit('publications',p,'commit').raise_for_status()
        self.assertEqual(self.submit('publications',dict(p,assetId='other'),'commit').status_code,409)
        self.assertEqual(self.client.get('/api/v1/assets/other').status_code,404)

if __name__=='__main__':
    unittest.main()

class Integrations(unittest.TestCase):
    def test_gates_at_clock_changes(self):
        from app.policies import evaluate
        rules=[dict(assetId='sink',timezone='America/New_York',requires=dict(assetId='raw',unit='hour',offset=-1))]
        for at,expected in [('2026-11-01T06:15:00+00:00','2026-11-01T01:00-04:00'),('2026-03-08T07:15:00+00:00','2026-03-08T01:00-05:00')]:
            self.assertEqual(evaluate(rules,datetime.fromisoformat(at),[],[])[0]['period'],expected)

    def test_notification_mapping(self):
        import os,hmac,hashlib
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'OBS_ALERT_MAP':'{"w":{"monitor":{"lag":"raw"},"pager":{"svc":"raw"}}}','OBS_PAGER_SUBSCRIPTIONS':'{"test":{"workspace":"w","secret":"test-secret"}}'}):
            client=TestClient(live_app(Path(tmp)/'state',credentials={'test':dict(workspace='w',role='writer')}),headers={'Authorization':'Bearer test'})
            a=dict(status='firing',labels={'alertname':'lag'},fingerprint='abc',startsAt='2020-01-01T01:00:00Z',generatorURL='https://example.org/alert')
            self.assertEqual(client.post('/integrations/monitor',json={'alerts':[a]}).status_code,200)
            payload=json.dumps({'event':dict(id='a1',event_type='incident.acknowledged',occurred_at='2020-01-01T02:00:00Z',data=dict(service={'id':'svc'},id='instance',html_url='https://example.org/incident'))}).encode()
            self.assertEqual(client.post('/integrations/pager/test',content=payload).status_code,401)
            signature='v1='+hmac.new(b'test-secret',payload,hashlib.sha256).hexdigest()
            self.assertEqual(client.post('/integrations/pager/test',content=payload,headers={'X-PagerDuty-Signature':signature}).status_code,200)
            rows=client.get('/api/v1/views/root_cause').json()['rows']
            self.assertEqual([(r['assetId'],r['status']) for r in rows],[('raw','acknowledged'),('raw','triggered')])

class PostgresIntegration(unittest.TestCase):
    def test_postgres_reference(self):
        import os,uuid
        url=os.getenv('TEST_DATABASE_URL')
        if not url:
            self.skipTest('Supply TEST_DATABASE_URL for PostgreSQL integration')
        ws=str(uuid.uuid4())
        clock=datetime(2026,1,1,tzinfo=timezone.utc)
        app=live_app(url,clock=lambda:clock,credentials={'test':dict(workspace=ws,role='writer')})
        client=TestClient(app,headers={'Authorization':'Bearer test'})
        for i,(kind,data) in enumerate(records(clock)):
            client.post('/api/v1/'+kind,headers={'Idempotency-Key':data.get('eventId',str(i))},json=data).raise_for_status()
        self.assertEqual(client.get('/api/v1/views/assets').json()['total'],3)
