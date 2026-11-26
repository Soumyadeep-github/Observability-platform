"""Collectors submit through the same HTTP contracts as external producers."""
import hashlib
import importlib.metadata
import json
import os
import sys
from datetime import datetime,timezone
import httpx

def object_store(config):
    import boto3
    client=boto3.client('s3',endpoint_url=config.get('endpoint'))
    for part in config['partitions']:
        count=size=0
        for page in client.get_paginator('list_objects_v2').paginate(Bucket=config['bucket'],Prefix=part['prefix']):
            for obj in page.get('Contents',[]):
                if not obj['Key'].endswith('/'):
                    count+=1
                    size+=obj['Size']
        yield 'partitions',dict(assetId=config['assetId'],partition=part['id'],objectCount=count,bytes=size,observedAt=config['observedAt'])

def warehouse(config):
    import psycopg
    with psycopg.connect(os.environ[config['dsnEnv']]) as db:
        rows=db.execute('SELECT column_name,data_type,is_nullable FROM information_schema.columns WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position',(config['schema'],config['table'])).fetchall()
    if not rows:
        raise ValueError('Warehouse table absent or not visible')
    types={'character varying':'string','text':'string','bigint':'integer','integer':'integer','numeric':'decimal','boolean':'boolean','date':'date','ARRAY':'array','timestamp with time zone':'timestamp','timestamp without time zone':'timestamp'}
    yield 'schemas',dict(assetId=config['assetId'],observedAt=config['observedAt'],fields=[dict(name=n,type=types.get(t,'unknown'),nullable=null=='YES') for n,t,null in rows])

def run(config):
    plugins={'object-store':object_store,'warehouse':warehouse}
    plugins.update({e.name:e.load() for e in importlib.metadata.entry_points(group='observability.collectors')})
    config.setdefault('observedAt',datetime.now(timezone.utc).replace(second=0,microsecond=0).isoformat())
    with httpx.Client(base_url=os.environ['OBS_API'].rstrip('/')+'/api/v1/',headers={'Authorization':'Bearer '+os.environ['OBS_TOKEN']}) as client:
        for endpoint,data in plugins[config['type']](config):
            key=hashlib.sha256(json.dumps([endpoint,data],sort_keys=True).encode()).hexdigest()
            client.post(endpoint,json=data,headers={'Idempotency-Key':key}).raise_for_status()

if __name__=='__main__':
    run(json.loads(open(sys.argv[1]).read()))
