"""The dashboard and read-only MCP tools use the same evidence projections."""
import json
import os
from .policies import evaluate
from datetime import datetime
from typing import Annotated, Literal
from fastapi import Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError

VIEWS = {
 'assets':'id name namespace owner source','lineage':'origin sourceColumn destination targetColumn provenance transformation evidenceId',
 'schema_diff':'assetId field before after observedAt evidenceId','freshness':'assetId status publishedAt ageMinutes freshnessMinutes lastRun quality gates evidenceId',
 'volume':'assetId partition rows objectCount bytes observedAt evidenceId','quality':'assetId checkId column status value observedAt evidenceId',
 'runs':'namespace job runId status observedAt evidenceId','root_cause':'assetId source instanceId title status severity observedAt impactedAssets lineageCoverage url evidenceId',
 'point_in_time':'receivedAt kind evidenceId data','coverage':'assetId publication quality lineage',
}
VIEWS = {name:fields.split() for name,fields in VIEWS.items()}

class Filters(BaseModel):
    model_config = ConfigDict(extra='forbid')
    asset_id: str = ''
    field: str = ''
    direction: Literal['upstream','downstream']='upstream'
    depth: int = Field(6,ge=1,le=20)
    q: str = Field('',max_length=256)
    limit: int = Field(50,ge=1,le=200)
    offset: int = Field(0,ge=0)
    as_of: AwareDatetime|None = None

def trace(edges,root,field,direction,depth):
    start,end = ('destination','origin') if direction=='upstream' else ('origin','destination')
    a,b = ('targetColumn','sourceColumn') if direction=='upstream' else ('sourceColumn','targetColumn')
    frontier,seen,selected = {(root,field)},set(),{}
    for _ in range(depth):
        following=set()
        for e in edges:
            if (e[start], e.get(a) if field else '') in frontier:
                selected[(e['origin'],e['destination'],e.get(a),e.get(b))]=e
                following.add((e[end],e.get(b) if field else ''))
        seen |= frontier
        frontier=following-seen
        if not frontier:
            break
    return list(selected.values())

def report(store,con,ws,name,f,now):
    def records(table):
        return store.records(con,ws,table,f.asset_id or None)
    fields=VIEWS[name]
    if name=='assets':
        rows=records('assets')
    elif name=='lineage':
        assets=store.records(con,ws,'assets')
        root=f.asset_id or (assets[0]['id'] if assets else '')
        rows=trace(store.records(con,ws,'edges'),root,f.field,f.direction,f.depth)
    elif name in ('freshness','coverage'):
        latest={v['assetId']:v for v in records('publications')}
        runs={ (d['namespace'],d['name']):r['status'] for r in store.records(con,ws,'runs') for d in r.get('outputs',[]) }
        latest_checks={(r['assetId'],r['checkId']):r['status'] for r in records('results')}
        tested={v['assetId'] for v in records('results') if v['status'] in ('PASS','FAIL')}
        linked={v['destination'] for v in records('edges')}
        rules=json.loads(os.environ.get('OBS_GATES','{}')).get(ws,[])
        gates=evaluate(rules,datetime.fromisoformat(now),store.records(con,ws,'publications'),store.records(con,ws,'partitions')) if rules else []
        rows=[]
        for a in records('assets'):
            ident=a['id']
            p=latest.get(ident,{})
            when=p.get('publishedAt')
            age=(datetime.fromisoformat(now)-datetime.fromisoformat(when)).total_seconds()/60 if when else None
            window=a.get('freshnessMinutes')
            status='unknown' if age is None or window is None else 'late' if age>window else 'fresh'
            required=[g for g in gates if g['assetId']==ident]
            if status=='fresh' and any(g['status']=='unknown' for g in required):
                status='waiting'
            statuses={s for (asset,_),s in latest_checks.items() if asset==ident}
            quality=next((s for s in ['FAIL','ERROR','SKIPPED','PASS'] if s in statuses),'unknown')
            rows.append(dict(assetId=ident,lastRun=runs.get((a['namespace'],a['name']),'unknown'),gates=required,status=status,publishedAt=when,ageMinutes=round(age,1) if age is not None else None,freshnessMinutes=window,evidenceId=p.get('evidenceId'),publication='observed' if when else 'unknown',quality=quality if name=='freshness' else ('observed' if ident in tested else 'unknown'),lineage='partial' if ident in linked else 'unknown'))
    elif name=='volume':
        rows=[dict(v,observedAt=v['publishedAt']) for v in records('publications') if v.get('rows') is not None]+records('partitions')
        rows.sort(key=lambda v:v['observedAt'],reverse=True)
    elif name=='quality':
        rows=list(reversed(records('results')))
    elif name=='runs':
        rows=list(reversed(store.records(con,ws,'runs')))
        if f.asset_id:
            identities={(a['namespace'],a['name']) for a in records('assets')}
            rows=[r for r in rows if any((d['namespace'],d['name']) in identities for d in r['datasets'])]
    elif name=='root_cause':
        rows=[dict(v,title=v['alertId']) for v in records('alerts')]+[dict(v,status=v['state'],observedAt=v['openedAt']) for v in records('incidents')]
        edges=store.records(con,ws,'edges')
        for row in rows:
            reach=trace(edges,row['assetId'],'','downstream',f.depth) if row.get('assetId') else []
            row['impactedAssets']=sorted({edge['destination'] for edge in reach if edge['destination']!=row['assetId']})
            row['lineageCoverage']='partial' if reach else 'unknown'
        rows.sort(key=lambda v:v['observedAt'],reverse=True)
    elif name=='schema_diff':
        previous,rows={},[]
        def flatten(columns,prefix=()):
            result={}
            for col in columns:
                path=prefix+(col['name'],)
                result[path]=(col['type']+('?' if col['nullable'] else ''))
                result.update(flatten(col['children'],path))
            return result
        for v in records('schemas'):
            ident=v['assetId']
            old=previous.get(ident,{})
            new=flatten(v['fields'])
            for col in sorted(set(old)|set(new)):
                if old.get(col)!=new.get(col):
                    rows.append(dict(assetId=ident,field='.'.join(col),before=old.get(col),after=new.get(col),observedAt=v['observedAt'],evidenceId=v.get('evidenceId')))
            previous[ident]=new
        rows.reverse()
    else:
        cutoff=f.as_of.astimezone(datetime.fromisoformat(now).tzinfo).isoformat(timespec='microseconds') if f.as_of else now
        where='ws=? AND received<=?'
        args=[ws,cutoff]
        if not f.q and not f.asset_id:
            count=store.sql(con,'SELECT count(*) FROM evidence WHERE '+where,args).fetchone()[0]
            ev=store.sql(con,'SELECT key,kind,received,body FROM evidence WHERE '+where+' ORDER BY received DESC,seq DESC LIMIT ? OFFSET ?',(*args,f.limit,f.offset))
            rows=[dict(evidenceId=k,kind=t,receivedAt=s,data=json.loads(body)) for k,t,s,body in ev]
            return dict(metrics=[],view=name,asOf=cutoff,fields=fields,total=count,offset=f.offset,rows=rows,coverage='partial' if count else 'unknown')
        rows=[dict(evidenceId=k,kind=t,receivedAt=s,data=json.loads(body)) for k,t,s,body in store.sql(con,'SELECT key,kind,received,body FROM evidence WHERE '+where+' ORDER BY received DESC,seq DESC',args)]
        if f.asset_id:
            rows=[v for v in rows if f.asset_id in (v['data'].get('assetId'),v['data'].get('id'),v['data'].get('origin'),v['data'].get('destination'))]
    if f.q:
        rows=[r for r in rows if f.q.casefold() in json.dumps(r,ensure_ascii=False).casefold()]
    metrics=[]
    if name=='freshness':
        assessed=[r for r in rows if r['status'] in ('fresh','late')]
        metrics=[dict(label='Within freshness target',value=f"{sum(r['status']=='fresh' for r in assessed)} / {len(assessed)} assessed"),
                 dict(label='Waiting on a dependency',value=sum(r['status']=='waiting' for r in rows)),
                 dict(label='Unknown freshness',value=sum(r['status']=='unknown' for r in rows))]
    elif name=='root_cause':
        instances={}
        for row in rows:
            if row.get('source') and row.get('instanceId'):
                group=instances.setdefault((row['source'],row['instanceId']),[])
                group.append(row)
        mapped=sum(any(r.get('assetId') for r in group) for group in instances.values())
        metrics=[dict(label='Alert instances linked to an asset',value=f'{mapped} / {len(instances)}')]
    return dict(metrics=metrics,view=name,asOf=now,fields=fields,total=len(rows),offset=f.offset,rows=[{k:r.get(k) for k in fields} for r in rows[f.offset:f.offset+f.limit]],coverage='partial' if rows else 'unknown')

def attach_mcp(app,caller,render):
    @app.post('/mcp')
    async def mcp(request:Request,ws:Annotated[str,Depends(caller)]):
        try:
            msg=await request.json()
        except ValueError:
            raise HTTPException(400,'Invalid JSON')
        if not isinstance(msg,dict) or msg.get('jsonrpc')!='2.0':
            raise HTTPException(400,'Expected JSON-RPC 2.0')
        op=msg.get('method')
        reply={'jsonrpc':'2.0','id':msg.get('id')}
        if op=='notifications/initialized':
            return Response(status_code=202)
        if op=='initialize':
            result=dict(protocolVersion='2025-06-18',capabilities={'tools':{}},serverInfo={'name':'observability','version':'1.1'})
        elif op=='ping':
            result={}
        elif op=='tools/list':
            result={'tools':[dict(name=v,description='Read workspace '+v,inputSchema=Filters.model_json_schema(),annotations={'readOnlyHint':True}) for v in VIEWS]}
        elif op=='tools/call':
            try:
                params=msg['params']
                data=render(params['name'],ws,Filters.model_validate(params.get('arguments',{})))
            except (KeyError,ValueError,TypeError,HTTPException):
                return dict(reply,error={'code':-32602,'message':'Invalid tool or arguments'})
            result={'content':[{'type':'text','text':json.dumps(data)}],'structuredContent':data}
        else:
            return dict(reply,error={'code':-32601,'message':'Unknown method'})
        return dict(reply,result=result)
