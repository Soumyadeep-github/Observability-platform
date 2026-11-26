"""Workspace-scoped records and immutable accepted evidence, in one transaction."""
import json
import sqlite3
from contextlib import contextmanager

TABLES = ('assets','schemas','checks','results','incidents','publications','edges','runs','alerts','partitions','fields','jobs')

class Store:
    def __init__(self, url):
        self.url = str(url)
        self.pg = self.url.startswith(('postgresql://','postgres://'))
        with self.transaction('schema-migrations', write=True) as con:
            for table in TABLES:
                con.execute(f'CREATE TABLE IF NOT EXISTS {table} (ws TEXT NOT NULL, id TEXT NOT NULL, asset TEXT NOT NULL, stamp TEXT NOT NULL, body TEXT NOT NULL, PRIMARY KEY(ws,id))')
                con.execute(f'CREATE INDEX IF NOT EXISTS ix_{table}_asset ON {table}(ws,asset,stamp)')
            serial = 'BIGSERIAL' if self.pg else 'INTEGER'
            con.execute(f'CREATE TABLE IF NOT EXISTS evidence (seq {serial} PRIMARY KEY, ws TEXT NOT NULL, key TEXT NOT NULL, kind TEXT NOT NULL, received TEXT NOT NULL, body TEXT NOT NULL, UNIQUE(ws,key))')
            con.execute('CREATE INDEX IF NOT EXISTS ix_evidence_time ON evidence(ws,received,seq)')

    @contextmanager
    def transaction(self, ws=None, write=False):
        if self.pg:
            import psycopg
            con = psycopg.connect(self.url)
        else:
            con = sqlite3.connect(self.url, timeout=20)
        try:
            if write:
                if self.pg:
                    con.execute('SELECT pg_advisory_xact_lock(hashtext(%s))', (ws,))
                else:
                    con.execute('BEGIN IMMEDIATE')
            yield con
            con.commit()
        finally:
            con.close()

    def sql(self, con, query, args=()):
        return con.execute(query.replace('?', '%s') if self.pg else query, args)

    def put(self, con, ws, table, key, asset, stamp, body):
        assert table in TABLES
        self.sql(con, f'INSERT INTO {table} VALUES (?,?,?,?,?) ON CONFLICT(ws,id) DO UPDATE SET asset=excluded.asset,stamp=excluded.stamp,body=excluded.body WHERE excluded.stamp >= {table}.stamp',
                 (ws,key,asset,stamp,json.dumps(body)))

    def records(self, con, ws, table, asset=None):
        assert table in TABLES
        where, args = (' AND asset=?',(ws,asset)) if asset is not None else ('',(ws,))
        return [json.loads(r[0]) for r in self.sql(con, f'SELECT body FROM {table} WHERE ws=?{where} ORDER BY stamp,id',args)]

def composite(*parts):
    return json.dumps(parts, ensure_ascii=False, separators=(',',':'))
