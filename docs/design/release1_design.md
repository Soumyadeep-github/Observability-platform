# Release 1 · Delivery evidence

The release answers a shift operator's recurring question. Which scheduled dataset is ready for consumers, for which business period, and what still needs attention? A completed job, an observed file, a committed destination partition and a passing quality check are independent facts. Acknowledging a page records human response. Recovery requires fresh publication or quality evidence.

## Scope and compatibility

| Integration type | Reference or planned example | Delivery status |
|---|---|---|
| Batch orchestrator | Airflow OpenLineage provider | Native RunEvent receiver implemented. Real producer qualification pending. |
| Object storage | S3-compatible ListObjectsV2 | Paginated partition polling adapter. Qualify with the target storage service. |
| Warehouse | PostgreSQL-compatible information schema | Schema collector. Producers submit sink commit evidence separately. BigQuery-specific adapter deferred. |
| Monitoring dashboard | Grafana webhook contact point | Inbound grouped alert adapter and dashboard/source link |
| Paging system | PagerDuty v3 webhook | Inbound lifecycle adapter and incident link |
| Batch engine and stream processor | Spark batch, Spark Structured Streaming, Flink | Dedicated runtime collection deferred |
| Message broker | Kafka | Offset, registry and consumer-group collectors deferred |
| Relational and distributed databases | Cloud SQL and Spanner | Service-specific discovery and dialect qualification deferred |

Scope follows the orchestrated batch → object partition → warehouse chain. Pull adapters run outside the core image. Job-run producers push to the native event route. Each collector receives only its own source credentials and a writer credential for one workspace. Build the collector with `docker build --target collector -t observability-collector .`. Mount its JSON config and supply `OBS_API` and `OBS_TOKEN`; invoke the image with the config file path. Install third-party Python collectors in that image using the `observability.collectors` entry point. A plugin yields endpoint/payload pairs. Extend the sample configuration to the partitions expected in the polling interval.

```json
{"type":"object-store","bucket":"example-input","assetId":"landing","partitions":[{"id":"2026-11-01","prefix":"day=2026-11-01/"}]}
```

List all pages before reporting a partition count. An empty listing supplies observed zero objects. An unavailable listing produces no observation. A positive listing establishes existence only. For sinks requiring completion manifests, consume the producer's commit event. The warehouse adapter takes `type=warehouse`, `assetId`, `schema`, `table` and `dsnEnv`. Schedule the container with a cluster CronJob and provide a stable observation time on replay.

## Time and freshness

The service uses UTC wall time. Tests inject a clock into the application factory. Event time describes the source observation. Receipt time records when the platform learned it. Replay through a cutoff uses receipt time. Late arrivals remain inspectable. A view displays unknown for an unobserved commit or missing freshness policy. The latest sink commit alone moves the publication timestamp.

Configure `OBS_GATES` as a workspace-keyed JSON object. A rule below checks a prior local calendar date. Use `unit=hour` for hourly gates. A due asset with a fresh publication and missing dependency reads waiting. A late publication still reads late and exposes its missing gates.

```json
{"sandbox":[{"assetId":"summary","timezone":"America/New_York","requires":{"assetId":"landing","unit":"day","offset":-2}}]}
```

Days subtract calendar dates in the policy timezone. Hours use elapsed hours, with the UTC offset in each local partition label. The two repeated fall-back hours are distinct. Spring-forward skips the nonexistent hour. Daily partition IDs use YYYY-MM-DD. Hourly IDs include minutes and an offset. Partition keys must follow this convention.

## External alerts and response

The canonical route accepts one alert per request plus a stable delivery key. A version change requires its own schema parser. Configure mappings per workspace; an unmapped identifier remains visible with unknown asset scope. Map a stable rule or service identity and preserve the individual alert instance for correlation. Never infer recovery from a cleared alert.

```json
{"version":1,"source":"monitor","alertId":"delivery-lag","instanceId":"instance-27","status":"triggered","observedAt":"2026-11-01T08:25:00Z","severity":"warning","url":"https://monitor.example/alerts/27"}
```

`OBS_ALERT_MAP={"sandbox":{"monitor":{"delivery-lag":"summary"},"pager":{"service-id":"summary"}}}`. Configure the monitor contact point to POST a bearer-authenticated webhook to `/integrations/monitor`. Each member of a group produces separate evidence. The adapter uses alertname for mapping, fingerprint for the instance, and the source's dashboard or rule link. Configure the pager subscription for incident triggered, acknowledged and resolved at `/integrations/pager/{subscription}`. Set `OBS_PAGER_SUBSCRIPTIONS` to a secret JSON map of subscription → {workspace,secret}. The adapter verifies the raw-body signature before ingest. For additional sources, translate to the versioned canonical contract. Paging, escalation and dashboard editing stay with the configured external services.

## Tool and UI contract

GET `/api/v1/views` and MCP `tools/list` enumerate the same views. Every tool takes the same filter schema as the matching view; `structuredContent` carries the same fields, rows, coverage, metrics, page position and observation time. The live UI renders these payloads. Contract changes must pass the parity test in CI using a nonempty external workload in every view.

| View and tool | Operator question |
|---|---|
| assets | Which datasets are registered and who owns each? |
| lineage | Which observed edges lead to or from this dataset or column? |
| schema_diff | What changed between observed schema snapshots? |
| freshness | Which deliveries are late, waiting or unknown? |
| volume | How many rows or objects were observed for this period? |
| quality | Which checks passed, failed, errored or skipped over time? |
| runs | Which job attempts have reported lifecycle evidence? |
| root_cause | Which incident or alert observations can explain the symptom? |
| point_in_time | What evidence was available by this cutoff? |
| coverage | Which fact types have observations for each asset? |

The agent design uses a deployment-configured provider base URL, model ID, protocol adapter and secret. Enable only approved free hosted models with billing disabled and no paid fallback. The LLM receives the minimum authorized facts. Only the agent service calls MCP. Return unknown when evidence is absent, describe incomplete lineage as partial, show timestamps with offsets, and link each material claim to the evidence receipt or external source. Distinguish an observed failure from a hypothesized cause. Quota exhaustion returns an availability message and a direct link to the same platform view. Hosted chat transport and delegated sign-in are release gates; the read-only MCP projection is implemented.

## Measure the value

The home screen puts publication age, job outcome, quality and dependency status on one row per asset. Operators can move from a late asset to a directed dependency or an external alert with evidence and a time. Refresh every 15 seconds and display the last successful refresh. Expired or missing observations deserve separate counts.

| Indicator | Definition and use |
|---|---|
| Current freshness | Fresh / assessed assets in the current filter. Display waiting and unknown counts alongside it. |
| On-time delivery | Scheduled periods with the required commit by deadline / all due periods. Publish unknown and late-arrival counts separately. |
| Detection delay | First actionable observation receipt minus missed deadline. Report p50/p95 and sample count. |
| Time to identify impact | First recorded operator identification of affected downstream dataset minus first alert receipt. Instrument the investigation action before publishing this KPI. |
| Time to recover | First verified healthy delivery after failure minus failure onset. Track human acknowledgement separately. |
| Alert attribution | Distinct mapped external instances / distinct received instances; report by source. |
| Monitoring coverage | Assets with an owner, policy, and recent evidence / in-scope assets. Include expected-but-silent assets in denominator. |

The delivery board measures current freshness. The root cause view counts unique mapped alert instances and lists potentially affected downstream assets with partial lineage coverage. For a pilot, establish two weeks of baseline on the same assets and schedule. Compare two weeks after enabling the integration, segmented by severity and source, with sample counts and median/p95. Record the monitoring and paging links an operator otherwise had to visit. Retain the integration if impact is identified faster without reducing coverage or increasing page volume. Decide numeric targets with the operator before the pilot.

## Storage, retention and capacity

One accepted write commits its evidence key and projections atomically. PostgreSQL serializes writes within each workspace. Index workspace, asset and observation time. The current application applies projections synchronously. A future queue worker can claim pending evidence using short transactions, expiring leases and fenced completion. Backlog age and ingest-to-visible delay are release gates before enabling asynchronous processing.

For E events/day, B bytes per stored event including projection/index overhead, and D retained days, budget E × B × D plus current catalog, WAL, free space, replicas and backups. Measure B from a representative load including column mappings and schema snapshots. At 100,000 events/day and 4 KiB/event, 30 days is about 11.4 GiB before WAL, headroom and replication. Size queue space for peak arrivals/second × recoverable outage seconds × bytes per queued item. Drain capacity must exceed normal arrivals. Verify with burst and restore drills. Use a configurable minimum 30-day evidence horizon, keep dedupe keys through the producer retry horizon and retain pending work until complete. Automated pruning, partitioned retention, high-cardinality SQL projections and failover load tests remain release gates.
