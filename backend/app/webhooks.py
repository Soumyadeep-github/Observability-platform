"""Translate inbound monitor and pager notifications to the versioned alert contract."""
import hashlib
import hmac
import json
import os
from fastapi import Depends, HTTPException, Request
from .contracts import Alert

async def read_body(request):
    body=bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body)>1_000_000:
            raise HTTPException(413,'Notification exceeds 1 MB')
    return bytes(body)

def attach_webhooks(app,caller,ingest):
    @app.post('/integrations/monitor')
    async def monitor(request:Request,ws=Depends(caller)):
        try:
            payload=json.loads(await read_body(request))
            observations=[]
            for a in payload['alerts']:
                status={'firing':'triggered','resolved':'resolved'}[a['status']]
                at=a['endsAt'] if status=='resolved' else a['startsAt']
                item=Alert(version=1,source='monitor',instanceId=a['fingerprint'],alertId=a['labels']['alertname'],observedAt=at,status=status,severity=a['labels'].get('severity','warning'),url=a.get('dashboardURL') or a['generatorURL'])
                fingerprint=json.dumps([a['fingerprint'],at,status])
                observations.append((item,'monitor-'+hashlib.sha256(fingerprint.encode()).hexdigest()))
        except (ValueError,TypeError,KeyError,AttributeError) as exc:
            raise HTTPException(422,'Invalid monitor notification') from exc
        return [ingest(ws,'alerts',item,key) for item,key in observations]

    @app.post('/integrations/pager/{subscription}')
    async def pager(subscription:str,request:Request):
        config=json.loads(os.environ.get('OBS_PAGER_SUBSCRIPTIONS','{}')).get(subscription)
        body=await read_body(request)
        if not config or not config.get('secret'):
            raise HTTPException(401,'Unknown subscription')
        expected='v1='+hmac.new(config['secret'].encode(),body,hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected.encode(),s.strip().encode()) for s in request.headers.get('X-PagerDuty-Signature','').split(',')):
            raise HTTPException(401,'Invalid signature')
        try:
            event=json.loads(body)['event']
            status={'incident.triggered':'triggered','incident.acknowledged':'acknowledged','incident.resolved':'resolved'}[event['event_type']]
            incident=event['data']
            item=Alert(version=1,source='pager',alertId=incident['service']['id'],instanceId=incident['id'],observedAt=event['occurred_at'],status=status,severity='critical' if incident.get('urgency')=='high' else 'warning',url=incident['html_url'])
            return ingest(config['workspace'],'alerts',item,'pager-'+event['id'])
        except (ValueError,TypeError,KeyError) as exc:
            raise HTTPException(422,'Unsupported pager notification') from exc
