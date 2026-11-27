"""Partition dependencies use UTC instants for hours and local dates for days."""
from datetime import timedelta
from zoneinfo import ZoneInfo
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

class Gate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    assetId: str = Field(min_length=1)
    unit: Literal['hour','day']
    offset: int = Field(le=0,ge=-366)

def evaluate(rules, instant, publications, partitions):
    facts={(r['assetId'],r['partition']) for r in publications if r.get('partition')}
    facts.update((r['assetId'],r['partition']) for r in partitions if r['objectCount']>0)
    out=[]
    for rule in rules:
        zone=ZoneInfo(rule['timezone'])
        gate=Gate.model_validate(rule['requires'])
        if gate.unit=='hour':
            period=(instant.astimezone(zone).replace(minute=0,second=0,microsecond=0).astimezone(instant.tzinfo)+timedelta(hours=gate.offset)).astimezone(zone).isoformat(timespec='minutes')
        else:
            period=(instant.astimezone(zone).date()+timedelta(days=gate.offset)).isoformat()
        out.append(dict(assetId=rule['assetId'],requires=gate.assetId,period=period,status='observed' if (gate.assetId,period) in facts else 'unknown'))
    return out
