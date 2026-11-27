"""Version 1 write contracts. Times are normalized before deduplication."""
from datetime import timezone
from typing import Annotated, Literal
from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, model_validator

Id = Annotated[str, Field(min_length=1, max_length=256)]
Time = Annotated[AwareDatetime, AfterValidator(lambda v: v.astimezone(timezone.utc))]
Severity = Literal['info', 'warning', 'critical']
Type = Literal['boolean','integer','decimal','float','string','bytes','date','timestamp','map','array','struct','unknown']

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Asset(Contract):
    id: Id
    name: Id
    namespace: Id
    owner: str = ''
    source: str = 'unclassified'
    freshnessMinutes: int | None = Field(None, gt=0)

class Column(Contract):
    name: Id
    type: Type
    nullable: bool = True
    children: list['Column'] = Field(default_factory=list)

    @model_validator(mode='after')
    def structure(self):
        if self.children and self.type not in ('map','array','struct'):
            raise ValueError('Only nested types accept children')
        if len({c.name for c in self.children}) != len(self.children):
            raise ValueError('Duplicate child field')
        return self

class Schema(Contract):
    assetId: Id
    fields: list[Column]
    observedAt: Time

    @model_validator(mode='after')
    def names(self):
        if len({c.name for c in self.fields}) != len(self.fields):
            raise ValueError('Duplicate field name')
        return self

class Check(Contract):
    id: Id
    assetId: Id
    name: Id
    column: Id | None = None
    severity: Severity = 'warning'

class Result(Contract):
    assetId: Id
    checkId: Id
    observedAt: Time
    status: Literal['PASS','FAIL','ERROR','SKIPPED']
    value: str | float | None = None

class Incident(Contract):
    id: Id
    assetId: Id
    title: Id
    severity: Severity
    openedAt: Time

class Transition(Contract):
    state: Literal['acknowledged','resolved']

class Publication(Contract):
    eventId: Id
    assetId: Id
    publishedAt: Time
    partition: str | None = None
    evidenceKind: Literal['sink_commit']
    rows: int | None = Field(None, ge=0)

class Edge(Contract):
    origin: Id
    destination: Id
    sourceColumn: Id | None = None
    targetColumn: Id | None = None
    provenance: Literal['declared','inferred','unknown']
    transformation: str | None = None

    @model_validator(mode='after')
    def paired(self):
        if bool(self.sourceColumn) != bool(self.targetColumn):
            raise ValueError('Both columns are required for a field edge')
        return self

class Alert(Contract):
    version: Literal[1]
    source: Id
    alertId: Id
    instanceId: Id | None = None
    status: Literal['triggered','acknowledged','resolved']
    observedAt: Time
    severity: Severity
    url: HttpUrl

class Partition(Contract):
    assetId: Id
    partition: Id
    observedAt: Time
    objectCount: int = Field(ge=0)
    bytes: int = Field(ge=0)
