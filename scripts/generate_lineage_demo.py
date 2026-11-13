#!/usr/bin/env python3
"""Generate reproducible OpenLineage RunEvents with the official Python SDK.

The Marquez-shaped graph is an offline fixture, not a lineage processing engine.
To exercise real ingestion, send these events to Marquez with seed_marquez.py.
"""
import json
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from openlineage.client.event_v2 import RunState, InputDataset, Job, OutputDataset, Run, RunEvent
from openlineage.client.facet_v2 import schema_dataset, column_lineage_dataset as cl
SchemaDatasetFacet = schema_dataset.SchemaDatasetFacet
SchemaDatasetFacetFields = schema_dataset.SchemaDatasetFacetFields
from openlineage.client.serde import Serde

ROOT = Path(__file__).resolve().parents[1]
PRODUCER = 'https://github.com/Soumyadeep-github/Observability-platform'


def generate():
    seed = json.loads((ROOT / 'backend/app/demo_seed.json').read_text())
    by_id = {a['id']: a for a in seed['assets']}
    nodes = {}
    def dataset_id(a):
        return f"dataset:{a['namespace']}:{a['name']}"
    for a in seed['assets']:
        key = dataset_id(a)
        nodes[key] = {'id': key, 'type': 'DATASET', 'data': {
            'id': {'namespace': a['namespace'], 'name': a['name']},
            'namespace': a['namespace'], 'name': a['name'],
            'fields': [{'name': c['name'], 'type': c['type']} for c in a['columns']],
            'description': a['description'], 'sourceName': a['source'],
        }, 'inEdges': [], 'outEdges': []}
    events = []
    def facets(a):
        return {'schema': SchemaDatasetFacet(producer=PRODUCER, fields=[SchemaDatasetFacetFields(name=c['name'], type=c['type']) for c in a['columns']])}
    # Explicit illustrative mappings: never infer lineage from matching column names.
    mappings = {
        'revenue': {
            'id': [('orders', 'id', 'IDENTITY', 'Copy order identifier')],
            'created_at': [('orders', 'created_at', 'TRANSFORMATION', 'TIMESTAMP_TRUNC(created_at, DAY)')],
            'amount': [('orders', 'amount', 'AGGREGATION', 'SUM(amount)')],
            'region': [('orders', 'region', 'IDENTITY', 'Group by region')],
        },
        'sessions': {
            'id': [('events', 'id', 'IDENTITY', 'Copy event identifier')],
            'created_at': [('events', 'created_at', 'TRANSFORMATION', 'Session start timestamp')],
            'amount': [('events', 'amount', 'AGGREGATION', 'SUM(amount) per session')],
            'region': [('events', 'region', 'IDENTITY', 'Copy event region')],
        },
        'dashboard': {
            'id': [('revenue', 'id', 'IDENTITY', 'Copy reporting identifier')],
            'created_at': [('revenue', 'created_at', 'IDENTITY', 'Copy reporting timestamp')],
            'amount': [('revenue', 'amount', 'AGGREGATION', 'SUM(daily_revenue.amount)')],
            'region': [('revenue', 'region', 'TRANSFORMATION', 'COALESCE(daily_revenue.region, dim_customers.region)'),
                       ('customers', 'region', 'TRANSFORMATION', 'COALESCE(daily_revenue.region, dim_customers.region)')],
        },
    }
    def output_facets(a):
        result = facets(a)
        fields = {}
        for output, sources in mappings[a['id']].items():
            fields[output] = cl.Fields(inputFields=[cl.InputField(namespace=by_id[source]['namespace'], name=by_id[source]['name'], field=field) for source, field, _, _ in sources],
                                       transformationType=sources[0][2], transformationDescription=sources[0][3])
        result['columnLineage'] = cl.ColumnLineageDatasetFacet(producer=PRODUCER, fields=fields)
        return result
    for a in seed['assets']:
        if not a['upstream']:
            continue
        name = f"build_{a['name']}"
        key = f'job:signal.demo:{name}'
        inputs = [by_id[i] for i in a['upstream']]
        event = RunEvent(eventTime=seed['now'], producer=PRODUCER, eventType=RunState.COMPLETE,
                         run=Run(runId=str(uuid5(NAMESPACE_URL, key))),
                         job=Job(namespace='signal.demo', name=name),
                         inputs=[InputDataset(namespace=i['namespace'], name=i['name'], facets=facets(i)) for i in inputs],
                         outputs=[OutputDataset(namespace=a['namespace'], name=a['name'], facets=output_facets(a))])
        events.append(json.loads(Serde.to_json(event)))
        nodes[key] = {'id': key, 'type': 'JOB', 'data': {
            'id': {'namespace': 'signal.demo', 'name': name}, 'namespace': 'signal.demo',
            'name': name, 'description': 'Sample transformation generated with the OpenLineage Python SDK.',
            'latestRun': {'id': event.run.runId, 'state': 'COMPLETED'},
        }, 'inEdges': [], 'outEdges': []}
        for source, target in [(dataset_id(i), key) for i in inputs] + [(key, dataset_id(a))]:
            edge = {'origin': source, 'destination': target}
            nodes[source]['outEdges'].append(edge)
            nodes[target]['inEdges'].append(edge)
    column_nodes = {}
    def column_id(namespace, dataset, field):
        return f'datasetField:{namespace}:{dataset}:{field}'
    for a in seed['assets']:
        for c in a['columns']:
            key = column_id(a['namespace'], a['name'], c['name'])
            column_nodes[key] = {'id': key, 'type': 'DATASET_FIELD', 'data': {'namespace': a['namespace'], 'dataset': a['name'], 'field': c['name'], 'fieldType': c['type'], 'transformationType': None, 'transformationDescription': None}, 'inEdges': [], 'outEdges': []}
    for event in events:
        for output in event['outputs']:
            for field, mapping in output['facets']['columnLineage']['fields'].items():
                target = column_id(output['namespace'], output['name'], field)
                column_nodes[target]['data'].update({k: mapping[k] for k in ['transformationType', 'transformationDescription']})
                for source in mapping['inputFields']:
                    origin = column_id(source['namespace'], source['name'], source['field'])
                    edge = {'origin': origin, 'destination': target}
                    column_nodes[origin]['outEdges'].append(edge)
                    column_nodes[target]['inEdges'].append(edge)
    (ROOT / 'backend/app/demo_columns.json').write_text(json.dumps({'graph': list(column_nodes.values())}, indent=2) + '\n')
    (ROOT / 'backend/app/demo_lineage.json').write_text(json.dumps({'graph': list(nodes.values())}, indent=2) + '\n')
    (ROOT / 'backend/app/demo_openlineage.json').write_text(json.dumps(events, indent=2) + '\n')
    print(f'Generated {len(events)} official SDK RunEvents and {len(nodes)} fixture graph objects.')


if __name__ == '__main__':
    generate()
