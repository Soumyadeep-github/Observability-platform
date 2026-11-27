"""Submit a synthetic reference chain through the public ingestion API."""
from datetime import datetime, timedelta, timezone
import os
import uuid
import httpx

def records(now):
    t=lambda minutes:(now-timedelta(minutes=minutes)).isoformat()
    for ident,source in [('landing','object storage'),('summary','warehouse'),('pending','warehouse')]:
        yield 'assets',dict(id=ident,name=ident,namespace='reference',owner='data operations',source=source,freshnessMinutes=60)
    yield 'partitions',dict(assetId='landing',partition=now.date().isoformat(),objectCount=4,bytes=2048,observedAt=t(31))
    yield 'lineage',dict(eventType='COMPLETE',eventTime=t(27),producer='urn:reference:batch',schemaURL='https://openlineage.io/spec/2-0-2/OpenLineage.json#/$defs/RunEvent',run={'runId':str(uuid.uuid5(uuid.NAMESPACE_URL,t(27)))},job={'namespace':'reference','name':'summarize'},inputs=[dict(namespace='reference',name='landing')],outputs=[dict(namespace='reference',name='summary')])
    yield 'publications',dict(assetId='summary',eventId='published-'+t(24),publishedAt=t(24),rows=840,evidenceKind='sink_commit')
    yield 'checks',dict(id='volume',assetId='summary',name='Minimum batch volume',severity='warning')
    for ago,status,value in [(1440,'PASS',1020),(23,'FAIL',840)]:
        yield 'results',dict(assetId='summary',checkId='volume',observedAt=t(ago),status=status,value=value)
    yield 'incidents',dict(id='low-volume-'+t(22),assetId='summary',title='Published batch below expected volume',severity='warning',openedAt=t(22))
    for asset,field in [('landing','amount'),('summary','total')]:
        yield 'schemas',dict(assetId=asset,fields=[dict(name=field,type='decimal',nullable=True)],observedAt=t(30))
    yield 'edges',dict(origin='landing',destination='summary',sourceColumn='amount',targetColumn='total',provenance='declared',transformation='sum(amount)')

if __name__=='__main__':
    import hashlib,json
    with httpx.Client(base_url=os.environ['OBS_API'].rstrip('/')+'/api/v1/',headers={'Authorization':'Bearer '+os.environ['OBS_TOKEN']}) as client:
        for endpoint,data in records(datetime.now(timezone.utc).replace(microsecond=0)):
            key=data.get('eventId') or hashlib.sha256(json.dumps([endpoint,data],sort_keys=True).encode()).hexdigest()
            client.post(endpoint,json=data,headers={'Idempotency-Key':key}).raise_for_status()
