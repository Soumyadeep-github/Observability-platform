import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import AwareDatetime
from . import contracts as c
from .lineage import RunEventEnvelope
from .store import Store, composite
from .views import report, VIEWS

def timestamp(value):
    return value.astimezone(timezone.utc).isoformat(timespec='microseconds')

def live_app(db_path=None, *, clock=None, credentials=None):
    app = FastAPI(title='Data observability platform',version='1.1')
    store = Store(db_path or os.environ.get('DATABASE_URL','observability.sqlite3'))
    now = clock or (lambda: datetime.now(timezone.utc))
    keys = credentials if credentials is not None else json.loads(os.environ.get('OBS_IDENTITIES','{}'))
    mappings = json.loads(os.environ.get('OBS_ALERT_MAP','{}'))

    def caller(request: Request):
        auth = request.headers.get('authorization','')
        token = auth[7:] if auth.startswith('Bearer ') else ''
        for key, identity in keys.items():
            if identity.get('role') in ('writer','reader') and identity.get('workspace') and key and hmac.compare_digest(key.encode(), token.encode()):
                if request.method != 'GET' and request.url.path != '/mcp' and identity['role'] != 'writer':
                    raise HTTPException(403,'Write permission required')
                return identity['workspace']
        raise HTTPException(401,'Workspace bearer credential required')

    Workspace = Annotated[str, Depends(caller)]
    Key = Annotated[str, Header(alias='Idempotency-Key',min_length=1,max_length=256)]

    def apply(con, ws, kind, data, key, received):
        def put(table, ident, asset, stamp, body):
            store.put(con,ws,table,ident,asset,stamp,body)
        def ensure(asset):
            if not store.sql(con,'SELECT 1 FROM assets WHERE ws=? AND id=?',(ws,asset)).fetchone():
                put('assets',asset,asset,received,{'id':asset,'name':asset,'namespace':'','source':'unclassified','owner':'','freshnessMinutes':None})
        asset = data.get('assetId')
        if asset:
            ensure(asset)
        at = data.get('observedAt',data.get('publishedAt',received))
        if kind == 'assets':
            put(kind,data['id'],data['id'],received,data)
        elif kind == 'schemas':
            put(kind,key,asset,at,dict(data,evidenceId=key))
            for field in data['fields']:
                put('fields',composite(key,field['name']),asset,at,dict(field,schemaKey=key))
        elif kind == 'checks':
            put(kind,composite(asset,data['id']),asset,received,data)
        elif kind == 'results':
            definition=store.sql(con,'SELECT body FROM checks WHERE ws=? AND id=?',(ws,composite(asset,data['checkId']))).fetchone()
            if not definition:
                raise HTTPException(422,'Register the check before submitting a result')
            put(kind,key,asset,at,dict(data,column=json.loads(definition[0]).get('column'),evidenceId=key))
        elif kind == 'incidents':
            if store.sql(con,'SELECT 1 FROM incidents WHERE ws=? AND id=?',(ws,data['id'])).fetchone():
                raise HTTPException(409,'Incident already exists')
            put(kind,data['id'],asset,received,dict(data,state='open',evidenceId=key))
        elif kind == 'transition':
            row = store.sql(con,'SELECT body FROM incidents WHERE ws=? AND id=?',(ws,data['id'])).fetchone()
            if not row:
                raise HTTPException(404,'Unknown incident')
            item = json.loads(row[0])
            if item['state'] != data['state'] and (item['state'],data['state']) not in [('open','acknowledged'),('acknowledged','resolved')]:
                raise HTTPException(409,'Invalid incident transition')
            put('incidents',data['id'],item['assetId'],received,dict(item,state=data['state']))
        elif kind == 'alerts':
            mapped = mappings.get(ws,{}).get(data['source'],{}).get(data['alertId'])
            if mapped:
                ensure(mapped)
            put(kind,key,mapped or '',at,dict(data,assetId=mapped,evidenceId=key))
        elif kind in ('partitions','publications'):
            put(kind,key,asset,at,dict(data,evidenceId=key))
        elif kind == 'edges':
            for field in ('origin','destination'):
                ensure(data[field])
            put(kind,composite(data['origin'],data['destination'],data.get('sourceColumn'),data.get('targetColumn')),data['destination'],received,dict(data,evidenceId=key))
        elif kind == 'lineage':
            job = data['job']
            job_id = composite(job['namespace'],job['name'])
            put('jobs',job_id,'',received,job)
            run_id = data['run']['runId']
            put('runs',key,'',data['eventTime'],dict(outputs=[{'namespace':d['namespace'],'name':d['name']} for d in data['outputs']],datasets=[{'namespace':d['namespace'],'name':d['name']} for d in data['inputs']+data['outputs']],job=job['name'],namespace=job['namespace'],runId=run_id,status=data['eventType'],observedAt=data['eventTime'],evidenceId=key))
            def identify(ds):
                ns,name = ds['namespace'],ds['name']
                matches = [a for a in store.records(con,ws,'assets') if (a['namespace'],a['name'])==(ns,name)]
                if matches:
                    return matches[0]['id']
                ident = 'ds-'+hashlib.sha256(composite(ns,name).encode()).hexdigest()
                put('assets',ident,ident,received,dict(id=ident,name=name,namespace=ns,source='run event',owner='',freshnessMinutes=None))
                return ident
            inputs = [identify(ds) for ds in data['inputs']]
            for ds in data['outputs']:
                dest = identify(ds)
                for origin in inputs:
                    apply(con,ws,'edges',c.Edge(origin=origin,destination=dest,provenance='inferred').model_dump(),key,received)
                for target,detail in ds.get('facets',{}).get('columnLineage',{}).get('fields',{}).items():
                    for source in detail['inputFields']:
                        transforms = source.get('transformations') or detail.get('transformationDescription')
                        edge = c.Edge(origin=identify(source),destination=dest,sourceColumn=source['field'],targetColumn=target,provenance='declared',transformation=json.dumps(transforms) if transforms else None)
                        apply(con,ws,'edges',edge.model_dump(),key,received)

    def ingest(ws,kind,item,key):
        data = item.model_dump(mode='json')
        for field in ('observedAt','openedAt','publishedAt','eventTime'):
            if field in data:
                value = getattr(item,field)
                if value > now():
                    raise HTTPException(422,'Observation time exceeds server time')
                data[field] = timestamp(value)
        body = json.dumps(data,sort_keys=True,separators=(',',':'))
        received = timestamp(now())
        with store.transaction(ws,write=True) as con:
            row = store.sql(con,'SELECT kind,body FROM evidence WHERE ws=? AND key=?',(ws,key)).fetchone()
            if row and tuple(row) != (kind,body):
                raise HTTPException(409,'Idempotency key already used for different content')
            if not row:
                try:
                    apply(con,ws,kind,data,key,received)
                except (ValueError,TypeError,KeyError,AttributeError) as exc:
                    raise HTTPException(422,'Malformed evidence or lineage facet') from exc
                store.sql(con,'INSERT INTO evidence(ws,key,kind,received,body) VALUES (?,?,?,?,?)',(ws,key,kind,received,body))
        return {'eventId':key,'duplicate':bool(row)}

    def register(kind,model):
        def submit(item: model, ws: Workspace, key: Key):
            return ingest(ws,kind,item,key)
        app.add_api_route('/api/v1/'+kind,submit,methods=['POST'],name='ingest_'+kind)
    for kind,model in [('assets',c.Asset),('schemas',c.Schema),('checks',c.Check),('results',c.Result),('incidents',c.Incident),('edges',c.Edge),('alerts',c.Alert),('partitions',c.Partition),('lineage',RunEventEnvelope)]:
        register(kind,model)

    @app.post('/api/v1/publications')
    def publish(item: c.Publication,ws: Workspace, idempotency_key: Annotated[str|None,Header(max_length=256)]=None):
        if idempotency_key is not None and idempotency_key != item.eventId:
            raise HTTPException(422,'Use the eventId as the idempotency key')
        return ingest(ws,'publications',item,item.eventId)

    class Change(c.Transition):
        id: c.Id
    @app.patch('/api/v1/incidents/{ident}')
    def transition(ident:str,item:c.Transition,ws:Workspace,key:Key):
        return ingest(ws,'transition',Change(id=ident,state=item.state),key)

    @app.get('/api/v1/evidence')
    def evidence(key:str,ws:Workspace):
        with store.transaction() as con:
            row=store.sql(con,'SELECT kind,received,body FROM evidence WHERE ws=? AND key=?',(ws,key)).fetchone()
            if not row:
                raise HTTPException(404,'Unknown evidence')
            return {'kind':row[0],'receivedAt':row[1],'data':json.loads(row[2])}

    @app.get('/api/v1/health')
    def health():
        with store.transaction() as con:
            con.execute('SELECT 1')
        return {'status':'ok','mode':'live'}

    from .views import Filters
    def render(name,ws,args):
        if name not in VIEWS:
            raise HTTPException(404,'Unknown view')
        with store.transaction() as con:
            return report(store,con,ws,name,args,timestamp(now()))
    @app.get('/api/v1/views')
    def catalog(ws:Workspace):
        return list(VIEWS)
    @app.get('/api/v1/views/{name}')
    def view(name:str,ws:Workspace,filters:Annotated[Filters,Query()]):
        return render(name,ws,filters)
    @app.get('/api/v1/lineage')
    @app.get('/api/v1/column-lineage')
    def graph(ws:Workspace,filters:Annotated[Filters,Query()]):
        return render('lineage',ws,filters)
    @app.get('/api/v1/assets')
    def assets(ws:Workspace,filters:Annotated[Filters,Query()]):
        return render('assets',ws,filters)
    @app.get('/api/v1/assets/{ident}')
    def asset_detail(ident:str,ws:Workspace):
        with store.transaction() as con:
            row=store.sql(con,'SELECT body FROM assets WHERE ws=? AND id=?',(ws,ident)).fetchone()
            if not row:
                raise HTTPException(404,'Unknown asset')
            return json.loads(row[0])

    from .webhooks import attach_webhooks
    attach_webhooks(app,caller,ingest)
    from .views import attach_mcp
    attach_mcp(app,caller,render)
    @app.get('/',include_in_schema=False)
    def home():
        return FileResponse(Path(__file__).with_name('live.html'))
    return app
