#!/usr/bin/env python3
"""Send SDK-generated sample OpenLineage events to a configured local Marquez."""
import json
import os
from pathlib import Path
import sys
import httpx

ROOT = Path(__file__).resolve().parents[1]
base_url = os.environ.get('MARQUEZ_URL', '').rstrip('/')
if not base_url:
    raise SystemExit('Set MARQUEZ_URL, for example http://127.0.0.1:5002')
# This is an explicit sample-data import, never called automatically by the API.
events = json.loads((ROOT / 'backend/app/demo_openlineage.json').read_text())
with httpx.Client(timeout=30, follow_redirects=False, trust_env=False) as client:
    for event in events:
        response = client.post(base_url + '/api/v1/lineage', json=event)
        if not response.is_success:
            print(f'Marquez rejected a sample event (HTTP {response.status_code}).', file=sys.stderr)
            raise SystemExit(1)
print(f'Sent {len(events)} OpenLineage RunEvents to Marquez. Graph projection may take time; refresh the lineage view.')
