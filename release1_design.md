# Release 1 — Python-first, cloud-native data observability

29 October 2026 · Design proposal · No application implementation is included

This proposal narrows the original platform architecture and extends the security design. It is the proposed release-specific decision record where older documents leave alternatives open. Interfaces and configuration examples here belong to this project unless explicitly identified as an upstream standard. Compatibility claims require a pinned-version integration test before release.

## 1. Decisions

| Concern | Proposed release decision | Reason |
|---|---|---|
| Backend | Python: FastAPI, Pydantic, SQLAlchemy/Alembic, psycopg, HTTPX | Typed validation, HTTP APIs, mature source libraries |
| Architecture | Modular monolith; separately deployed API, processor, scheduler and connector processes | One domain implementation; independent failure boundaries and scaling |
| Durable coordination | PostgreSQL inbox, work queue, leases, projections and outbox | Avoid a mandatory Kafka/Redis deployment for the platform |
| Connector execution | Isolated Python images by dependency family | Reuse libraries without bloating the API or sharing every source credential |
| Pipeline instrumentation | Existing Airflow provider and Spark/Flink OpenLineage plugins | Reuse runtime extraction rather than rebuilding it |
| UI | Python-rendered HTML initially; small browser JavaScript for lineage visualization | No Node runtime; browser graphics still require browser code |
| Go transition | Stable HTTP/JSON protocols and golden fixtures; replace processes gradually | Python packages and database tables must not become the plugin ABI |
| Kubernetes | One Helm chart with local, integration-test and production profiles | Same deployment shape; clear differences in infrastructure guarantees |
| HA | Stateless replicas + shared durable work + HA PostgreSQL | Pod replication alone is insufficient |
| Catalog | Platform owns release-1 asset, schema, lineage and health state; external catalog optional | Avoid requiring another large control plane just to use connector libraries |

The original OpenMetadata-first suggestion is adjusted here. A standalone, lightweight deployment with replaceable Go components is easier when our database and APIs own observability state. We can add asynchronous OpenMetadata/DataHub synchronization later. Reusing their connector packages does not require claiming their server is our system of record. Some sources may still depend on catalog APIs; test and isolate those rather than faking compatibility.

“Python-first” means the application we build. Spark/Flink instrumentation is existing JVM code, PostgreSQL and the identity provider retain their runtimes, and the browser renders HTML/CSS/JavaScript. No custom Java/Scala pipeline plugin is planned for the first release. Optional Python producer hooks cover gaps where the external runtime supports them.

## 2. Release scope and definition of support

Retain the original product requirements: discover assets and columns, table/column lineage, schema history, DQ results at dataset/column scope, push/pull evidence, freshness policies, and configurable history of at least 30 days.

| Integration | Collection path | Release-1 supported evidence | Explicit limits |
|---|---|---|---|
| Airflow | Official OpenLineage provider; REST reconciliation | DAG/task attempts, outcomes, parent-child links, supported operator metadata | Airflow submission success does not prove external output publication |
| Spark batch | OpenLineage Spark listener; output commit evidence | Runs, schemas and lineage where the listener supports the source/sink | Dynamic code, opaque UDFs and unsupported sinks can produce partial lineage |
| Spark Structured Streaming | Listener + progress adapter/hook | Query/restart identity, microbatch observations, watermark/lag/progress where exposed | Progress or watermark alone does not prove durable output; continuous mode is deferred |
| Flink | OpenLineage integration + REST/checkpoint/metrics poller | Job state, checkpoints and supported source/sink lineage | Pin one major version; arbitrary DataStream column lineage is not promised |
| Kafka | Existing metadata source + admin/consumer-group metrics adapters | Topics, partitions, offsets, consumer lag; schema only through configured registry/explicit schema | Kafka brokers do not intrinsically provide record schemas or complete producer-consumer lineage |
| BigQuery | Existing metadata source + official API/job-history adapter | Tables/views/schema; jobs; supported SQL lineage; publication/watermark evidence | Query/job visibility is regional and permission-dependent; SQL lineage may be partial |
| Cloud SQL | PostgreSQL/MySQL metadata source + language connector/proxy if useful | Tables/views/columns; configured watermark/manifest and SQL DQ | Cloud SQL is a managed service, not one SQL dialect; SQL Server is deferred |
| Spanner | Official Python SDK + INFORMATION_SCHEMA; optional catalog bridge | Tables/columns; declared lineage; configured watermark and bounded SQL DQ | GoogleSQL dialect first; PostgreSQL dialect deferred; no universal table build history |

All listed systems are release targets, with capability differences shown in the UI. “Connector supported” is not equivalent to “automatic complete column lineage.” A release may not label Flink column lineage complete without fixtures proving it. Explicit column mappings are available for every source.

Candidate validation baseline: one supported Airflow major, Spark 3.5.x Structured Streaming microbatch mode, one Flink major (prefer 2.x for new setups), Kafka in KRaft mode, Cloud SQL PostgreSQL and MySQL, and Spanner GoogleSQL. Exact patch versions, JVM plugin compatibility and Python interpreter version are selected through the compatibility gate, not guessed from latest tags. Add alternate engine versions only with tests.

## 3. Deployment architecture

See release1_architecture.svg for an immediately viewable diagram and release1_architecture.drawio for two editable pages: logical architecture and availability/delivery. Open the .drawio file at https://app.diagrams.net/ using File → Open From → Device. The HTML viewer includes both diagrams without network dependencies.

Four process roles share one source repository and release version:

| Role | Work | Starting production shape |
|---|---|---|
| API | Auth, validation, durable ingest, query/history, read-only MCP, HTML UI | 3 replicas across zones |
| Processor | Normalize evidence, resolve identities, update projections, evaluate policies, deliver catalog outbox | 2+ replicas with bounded leases |
| Scheduler | Enqueue due polls and time-driven freshness evaluations | 2 replicas; database uniqueness/claims prevent duplicate effects |
| Connector workers | Poll sources and execute allow-listed metadata/DQ recipes | 2 replicas per enabled pool for sustained workloads; Jobs for expensive/on-demand scans |

These are process and trust boundaries, not independently owned business microservices. Workers can be deployed separately without separate databases or duplicated business rules. Do not run a Spark/Flink cluster inside the core application container. Application workloads are clients of those engines.

The API serves prebuilt/static browser assets and Python-rendered pages. Keep APIs authoritative so a TypeScript UI can be added later without changing the backend protocol. Read-only MCP tools delegate to the same authorized application services.

## 4. Pluggability without a proprietary connector runtime

There is no universal open protocol that makes every metadata, ETL and DQ connector interchangeable. OpenLineage covers execution/lineage, not general discovery or every health metric. Airbyte and Kafka Connect protocols are useful within their data-movement ecosystems, but using them does not automatically produce our metadata semantics.

Expose standard surfaces and a small published extension contract:

| Layer | Standard or interface | Ownership |
|---|---|---|
| Execution and lineage ingress | OpenLineage RunEvent/DatasetEvent/JobEvent, validated against pinned schemas | Upstream standard |
| Application API | HTTP + OpenAPI; JSON Schema payloads | Project API, openly documented |
| Additional observations | CloudEvents 1.0 structured JSON with versioned data schemas | Standard envelope, project payload semantics |
| Agent access | MCP supported specification and remote authorization | Upstream protocol, project tools |
| Dataset expectations | Versioned asset schema, freshness and DQ policies | Project model; optional ODCS import after mapping proof |
| Worker control | Versioned HTTP work claim/heartbeat/complete | Project protocol, language-neutral |

Do not call our additional observation schema an established industry standard. Publish it under the repository license, with schema files, examples, compatibility policy and a conformance suite. “Data contract” here includes component messages; a separate dataset contract describes what a dataset promises consumers.

### Connector reuse strategy

1. Prefer official runtime instrumentation for Airflow/Spark/Flink.
2. First evaluate DataHub OSS Python sources for BigQuery, Kafka, PostgreSQL and MySQL, using their metadata-file output as an isolation boundary. A Python bridge translates selected aspect records to our observations. This avoids importing DataHub models into the core domain.
3. Evaluate an OpenMetadata bridge only when its connector saves work for a concrete unsupported capability. Do not ship both full frameworks by default. Its source/sink and server lookups may need a real OpenMetadata deployment; verify this before claiming standalone reuse.
4. Use official GCP clients and SQL metadata APIs for Spanner and focused job/watermark collection. These are library reuse, not a preexisting observability connector.
5. Preserve upstream recipes where supported. Store platform settings such as canonical instance ID, schedule, capabilities and secret references alongside the recipe, not by inventing an incompatible replacement syntax.

For a file bridge: collect into bounded ephemeral storage; validate each record; submit deterministic observation IDs; checkpoint only after durable API acknowledgement. Resume/replay on restart. Do not assume every upstream source works without its server: stateful ingestion, enrichment and deletion detection are connector-specific. Start with stateless discovery; source deletion is applied only after a complete successful inventory generation, never after a failed scan.

Plugins are installed into reviewed image builds, not pip-installed from UI input. Operators select approved image digests/recipes. A Python entry point may register an adapter within its worker image, but HTTP/JSON is the durable cross-language boundary. No pickled Python objects, arbitrary Python imports in the API, or Celery-serialized task signatures form the protocol.

Each plugin publishes an immutable manifest: plugin ID/version, image digest, supported protocol major, capability list, engine version range, configuration schema, secret fields, required network destinations, upstream license and expected resource class. The API exposes that manifest for discovery. Unknown capabilities are displayed as unsupported rather than inferred.

## 5. Component contracts and delivery semantics

### Canonical identity

Assign internal UUID asset IDs. Resolve external identities through aliases keyed by workspace, environment, platform, stable source-instance ID and native object key. Endpoint hostnames alone are insufficient: failover or aliases must not create new assets. BigQuery object keys include project/dataset/table; Cloud SQL keys include instance/database/schema/table; Spanner includes project/instance/database/schema/table; Kafka includes stable cluster identity/topic.

Keep the original OpenLineage namespace/name as an alias. Configure deterministic mappings so Airflow, Spark and source discovery converge on the same asset. Column references include schema version and field path. Renames require explicit or validated mapping; do not silently equate similarly named columns.

### Observation example

Illustrative project payload in a CloudEvents structured envelope:

```json
{
  "specversion": "1.0",
  "id": "publish:source-a:run-42:attempt-2:orders:commit-18",
  "source": "urn:connector:production:spark-a",
  "type": "org.observability.asset.published.v1",
  "subject": "asset/7c5cf143-06da-4edc-b8f2-629a90f4734b",
  "time": "2026-10-29T01:00:00Z",
  "datacontenttype": "application/json",
  "data": {
    "contract_version": "1.0",
    "asset_id": "7c5cf143-06da-4edc-b8f2-629a90f4734b",
    "run_id": "run-42",
    "attempt": 2,
    "partition": "2026-10-29",
    "output_version": "commit-18",
    "published_at": "2026-10-29T01:00:00Z",
    "evidence_kind": "sink_commit",
    "schema_version": "schema-9"
  }
}
```

Workspace and producer identity come from authenticated scope. If payload workspace fields are supported, validate them against that scope. The server assigns ingestion time. Do not download schema URLs supplied in events: use a local approved schema registry to avoid SSRF and dependency outages.

### Contract families

| Contract | Key fields and rules |
|---|---|
| Asset/schema snapshot | Identity aliases, typed columns, schema hash/version, complete/partial scope; missing fields do not automatically mean deletion |
| Run observation | Job, run, attempt, parent/external IDs, event time and terminal outcome |
| Publication | Specific output, committed version/partition, commit evidence, optional watermark |
| Stream progress | Stable query/job ID, execution epoch, batch/checkpoint ID, progress sequence, captured time, lag/watermark/offset metrics |
| Lineage | Input/output assets and columns, transformation kind, provenance, confidence, validity, snapshot scope and completeness |
| Quality result | Stable check ID and definition version, scope/column, PASS/FAIL/ERROR/SKIPPED, metrics and captured time |
| Collector heartbeat | Connector identity/version, poll status, last successful source contact, cursor and coverage |
| Worker task | Task ID, type/version, config reference, lease/fence, deadline and idempotency key |

Publication and stream progress are distinct. A checkpoint may establish recovery progress without proving every external sink committed. DQ ERROR is an execution failure, not a failed data assertion. Names and numeric codes are language-neutral; decimal values use explicit representation when float conversion would lose precision. All timestamps are RFC3339 UTC; identifiers never depend on Python hashing or locale.

### HTTP behavior

| Surface | Behavior |
|---|---|
| POST /api/v1/lineage | Native OpenLineage payload; endpoint/path configurable for upstream HTTP clients; normalize after durable acceptance |
| POST /api/v1/observations | Bounded batch of CloudEvents observations; reject invalid batch atomically; per-batch size cap |
| GET /api/v1/receipts/{id} | Accepted / processing / applied / quarantined; expose sanitized reason |
| GET /api/v1/assets and /assets/{id}/history | Permission-filtered pagination, current or valid_at/known_at state |
| POST /internal/v1/tasks/claim | Authorized worker pool, bounded batch, lease token and fencing generation |
| POST /internal/v1/tasks/{id}/heartbeat | Renew only current lease owner; server time is authoritative |
| POST /internal/v1/tasks/{id}/complete | Finalize only with current fencing generation; return committed cursor version |

Return 202 only after inbox and processing task commit durably. A 202 receipt is not a claim that state is already visible. Duplicate event keys with the same content return the existing receipt; same key with different content returns a conflict. Define deduplication horizon separately from raw-history deletion, at least covering the supported retry window. OpenLineage events do not universally provide a unique event ID: derive a producer-scoped key from canonical validated event content, preserving meaningful progress differences.

429 and retryable 5xx responses include retry guidance. Clients use bounded exponential backoff with jitter and a durable spool where available. A spool is deployment-specific; the official listener is not assumed to survive every producer crash. Source history reconciliation repairs gaps only where evidence still exists. Do not promise complete recovery for sources that expose no replayable history.

Unknown optional extension fields can be retained under limits; unknown major contract versions fail validation. Additive changes stay within a major; changed meaning requires a new major. Publish compatibility tests and a deprecation window. Preserve original payload plus normalizer version within retention/security limits.

## 6. Processing, queue and concurrency

API transaction: validate auth/schema/limits → insert inbox observation and processing task → commit → acknowledge. No synchronous connector calls or external catalog writes occur on this path.

Processors claim tasks in short PostgreSQL transactions using row locking with SKIP LOCKED. Lease expiry, attempt count, owner, heartbeat and monotonically increasing fence permit recovery after crashes. External work runs outside transactions. Completion checks the fence; stale workers cannot advance cursors or change task state. Their already-pushed immutable observations are harmless through deduplication, but external side effects require idempotency or fencing at the sink.

Normalization and projection updates happen with the inbox processing marker and outbox in one database transaction. Serialize updates per asset using a row/advisory lock with a consistent lock order for multi-asset operations. Do not let a late old attempt overwrite newer evidence. Keep execution outcomes, publication evidence and policy-derived health as separate dimensions.

Schedulers can both scan due work. A unique occurrence key (policy/connector ID, config version, scheduled time) prevents duplicate enqueueing; task claims coordinate execution. Use database time and short locks. Fair queues and per-source concurrency limits prevent slow sources or huge inventories starving freshness evaluation. Do not run scheduler logic as an uncoordinated timer inside every API pod.

Connector checkpoints are server-owned and versioned. Advance them only after all observations for the page/window have durable receipts and the connector task completion is fenced. Cursor is collection progress, not proof of completed projection. Retain unprocessed inbox entries and pending outbox messages until terminal processing, independently of normal history cleanup.

Start with PostgreSQL, not Kafka as a mandatory internal bus. Kafka is a monitored source in this release. Add a broker only after measurements show queue contention, throughput or replay consumers justify it; preserve the same observation contract and acknowledgement boundary.

## 7. Batch and streaming correctness

Batch: keep last attempted run/outcome and last successful per-asset publication separately. A failed refresh must not erase usable prior data. Backfills affect their target partitions; they do not automatically satisfy today's deadline.

Airflow: propagate parent run information to supported external operators and instrument Spark/Flink separately. Reconcile attempts, mapped tasks, retries and backfills through the selected Airflow version's API. Monitoring must never fail a business DAG solely because the observability endpoint is unavailable; record the reporting failure and reconcile it. Pipelines requiring fail-closed DQ gates configure those separately.

Spark streaming: use query identity across restart plus an execution epoch and batch ID to avoid conflating retries. Progress listener fields have source/sink-specific meaning. Choose a sampling/aggregation interval to avoid an observation per row or uncontrolled microbatch cardinality. Keep failures and schema changes unsampled. Declare continuous processing mode out of release scope until tested.

Flink: correlate job IDs and restarts; collect job state, latest completed checkpoint, checkpoint age and exposed watermark/lag. Native lineage depends on connector and engine generation. A long-running RUNNING job with obsolete checkpoints or growing lag is unhealthy even without a terminal failure.

Kafka: distinguish log end offset, committed consumer offset and event-time freshness. Lag can be high during healthy catch-up; zero lag can coincide with a stalled upstream producer. Topic offset growth is not proof of a downstream dataset publication. Topic schemas come from a configured registry or explicit contract.

Freshness modes: expected publication deadline, maximum publication age, watermark age, checkpoint/progress age, consumer lag or a combination. Store event-time watermark separately from latest business timestamp: an engine watermark is not a universal completeness guarantee. Idle streams require an explicit policy; absence of incoming records is not automatically a failure. Use a scheduled evaluator so time changes health without new events. Collector outage yields stale monitoring/unknown evidence rather than invented build failures.

## 8. Data model, lineage and retention

PostgreSQL tables by logical responsibility: assets/aliases; schema_versions/columns; jobs/runs/attempts; inbox_observations; publication_evidence; stream_progress; lineage_edge_versions; check_definitions/results; policy_versions; health_current/transitions; connector_configs/cursors; task_queue/leases; outbox; audit.

Use relational columns for identity, time, filter and join keys; JSONB for bounded extensions. Version schemas, policies, checks and lineage. Represent historical effective time and when evidence became known so late corrections remain explainable. Use provenance-scoped edge snapshots: one connector's partial view must not delete another source's edges. Track declared, SQL-inferred and runtime-observed lineage distinctly.

Retain current state independently from history. Default history to 30 days; workspace settings and asset overrides may extend it. Preserve boundary schema/lineage/check/policy versions needed to reconstruct the retained window, even when created earlier. Never drop a time partition while any row is protected by retention, references or pending work. Start with a minimum 30-day policy; increasing retention cannot recover expired history.

Raw observations, summaries, audit logs and deduplication keys have distinct retention rules. At moderate scale, partition high-volume history by time and use indexed selective deletion for mixed policies. Store large sanitized payloads in optional object storage only when measured size justifies another dependency. Do not store copies of source datasets.

## 9. Quality execution

First release: ingest external DQ results and run a bounded SQL check set for BigQuery, Cloud SQL and Spanner: row count, not-null, uniqueness and configured range predicates, at dataset/column scope. Version definitions, parameters and execution scope. Use source-specific adapters and query time/bytes/row limits; a nominally simple uniqueness query can be expensive.

For Spark/Flink streaming, accept precomputed window/batch check results through the common contract. Do not launch distributed processing engines from API requests or scan unlimited Kafka records to infer quality. Existing DQ frameworks may run in producer jobs and emit mapped results. No Deequ JVM dependency belongs in the core Python image.

## 10. Lightweight images and Kubernetes lifecycle

Use a multi-stage image build: resolve a locked dependency set and build wheels in the builder; copy only runtime environment, code and static assets into a minimal supported glibc-based Python runtime. Remove build tools, caches and development dependencies from the final image. Run non-root, read-only filesystem with bounded temporary storage, CA certificates and no unnecessary utilities. Avoid Alpine as an automatic choice: native wheels and source builds may increase complexity.

| Image family | Included | Excluded |
|---|---|---|
| Core | API/processor/scheduler package, DB driver, auth/HTTP, templates/assets | Spark/Flink JVMs, Airflow, data ingestion frameworks, cloud connector extras |
| Metadata worker | Pinned upstream framework + only selected source extras + bridge | Web server UI and unrelated source packages |
| GCP worker | BigQuery/Spanner SDKs and optional Cloud SQL connection library | Distributed processing engines |
| Metrics/SQL worker | Minimal Kafka/SQL clients required for its enabled sources | All-source connector bundle |

Initial engineering target: core image compressed size at most 200 MiB, measured in CI after choosing dependency versions; this is a target, not a measured result. Report compressed and unpacked sizes separately. Worker budgets are recorded by family and may be larger. Optimizing one universal all-connector image conflicts with the dependency requirements; isolation keeps the always-running core small.

Helm exposes replicas, resource requests/limits, topology spread, disruption budgets, probes, network policies, service accounts, secret references and retention settings. Migrations run once as a coordinated release Job with separate credentials; API pods never race to migrate. Use expand/contract database changes to allow rolling upgrades and later Go consumers.

Liveness checks process health; readiness checks ability to serve the role; startup probes cover startup. Do not restart every pod because a shared source is unavailable. On termination: stop claiming tasks, mark unready, drain in-flight HTTP requests, finish short transactions and release/expire leases safely. Make termination grace period explicit.

## 11. Availability and recovery

Production proposal: regional/multi-zone Kubernetes, three API replicas, at least two processors and schedulers, worker replicas for critical sources, and HA PostgreSQL with automatic failover. Spread across available zones and configure disruption budgets; these protect some disruptions, not all outages.

Offer managed PostgreSQL in production or an operator-managed HA cluster for a fully in-Kubernetes installation. The local profile uses one database instance by default and must be labelled non-HA. A three-node local Kubernetes cluster can exercise scheduling and worker failover, not demonstrate independent-zone resilience.

| Failure | Required behavior |
|---|---|
| API pod dies after database commit | Client retry receives existing receipt; processor continues |
| Worker dies or pauses beyond lease | New worker resumes; stale completion cannot advance checkpoint |
| Two schedulers run concurrently | Unique occurrence keys and claims prevent duplicate state effects |
| PostgreSQL fails over | Retry short transactions; reconnect; uncertain commits resolve through event IDs |
| Source/API throttles or is unreachable | Backoff, preserve cursor, report collector degradation; no invented source failures |
| Identity provider temporarily unavailable | Validate tokens with cached valid signing keys where safe; reject unverifiable tokens |
| Zone unavailable | Remaining application replicas and database failover sustain service within tested limits |
| Catalog unavailable | Outbox retries; core ingest/query remains available |

HA and disaster recovery differ. Synchronous replication policy and failover selection determine whether acknowledged events survive a database failure. A 202 does not create stronger durability than the database configuration. Backups/PITR cover corruption and disaster recovery; define retention and restore tests separately.

Proposed validation targets, pending load/failure tests: 99.9% monthly API availability; p95 ingestion acknowledgement below 500 ms at the agreed test load; ordinary projection lag under 60 s; freshness evaluation within 2 min of a deadline; single pod recovery under 2 min; database failover under 5 min. Aim for zero loss of acknowledged events for the documented synchronous single-zone-failure scenario only if the database deployment proves that guarantee. Regional DR has separate proposed RPO ≤5 min / RTO ≤60 min; no active-active multi-region writes in release 1.

Illustrative sizing workload: 10,000 assets, 1,000 daily batch runs, 100 stream jobs sampled once/minute, and 100 observations/second sustained with 500/second bursts. This is a test envelope, not a capacity claim. Measure payload sizes, write amplification, queue wait, history growth, pool contention and costs. Enforce per-pool DB connection limits and autoscaling maxima so scale-out cannot exhaust PostgreSQL.

## 12. Local test profiles

| Profile | Contents | What it establishes |
|---|---|---|
| core-local | Kind + compatible CNI, application roles, PostgreSQL, development OIDC/TLS | Install, auth, APIs, contracts, policy and basic network behavior |
| integration-local | Add Airflow, Kafka/registry, small Spark batch/stream and Flink jobs; PostgreSQL/MySQL sources | Real producer and connector compatibility on synthetic data |
| ha-local | Multiple local nodes and replicas; lease, kill/restart and disruption tests | Process coordination and idempotency; not zone-level HA |
| cloud-staging | Real BigQuery, Cloud SQL, Spanner and cloud identity/networking | Provider behavior, IAM, TLS, quotas, and database/cloud failure tests |

Enable heavyweight integration engines individually or in scheduled suites; the observability platform does not require all of them to boot for every developer. An emulator or fake is useful for contract tests but cannot certify BigQuery, Spanner or Cloud SQL compatibility. End-to-end cloud tests incur provider resources; put budgets and cleanup on the test environment.

## 13. Security inheritance

Apply the existing security design: OIDC, scoped producers, same authorization for REST/MCP, separate worker identities, default-deny networking, Restricted pod posture, mounted/rotated secrets where practical, workload federation, image provenance, metadata redaction and independent audit retention. No raw production data in local tests. Connector recipes are code-equivalent and only trusted operators can select approved packages and images.

Source metadata access and DQ query execution use different permission sets. Discovery must still work when row-reading permission is intentionally absent. The platform is an observability service, not a query proxy granting users all connector privileges.

## 14. Go migration without a rewrite of every connector

1. Stabilize OpenAPI/JSON Schemas, normalization fixtures, alias rules, projection ordering and lease semantics in Python.
2. Keep upstream ingestion workers in Python behind the HTTP observation/task interfaces.
3. Implement a Go normalizer/evaluator against the same conformance fixtures; run it in shadow mode without writes and compare results.
4. Transfer projection ownership by explicit workspace/asset shard with a fencing boundary. Never run Python and Go as competing writers for the same projection accidentally.
5. Replace API/scheduler roles incrementally. Keep compatible DB migrations until all consumers move; contract-test authorization, pagination, decimals and timestamp semantics.

HTTP/JSON contracts reduce coupling but do not make database access automatic across languages. SQL migrations and persistence behavior still need careful implementation. Shared tables remain an internal release-level interface until components are deliberately separated into independently released services.

## 15. Implementation gates before coding broadly

First run small compatibility experiments; these are future tasks, not completed work:

1. Airflow task → Spark batch → BigQuery: one canonical output asset, correct parent run, retry and publication evidence.
2. Kafka → Spark Structured Streaming → supported sink: progress, restart, committed output and sampling behavior.
3. Kafka → Flink → Kafka: pinned listener, topic identity, checkpoint polling; explicitly demonstrate column-lineage limits.
4. Run selected DataHub OSS sources to a file without a DataHub server. Inspect schemas, upstream lookups and checkpoint dependencies. Prove Kafka registry and Cloud SQL dialect behavior.
5. Spanner schema + watermark + SQL DQ with least privilege in cloud staging.
6. Duplicate and reordered events; worker lease expiry; concurrent scheduler; database failover; 30-day boundary reconstruction and deletion safety.
7. Validate core-image budget, clean installation on Kubernetes, and restricted network paths.

Do not code the full connector platform until the source/sink and event semantics pass these gates. Release definition includes the matrix of tested engine/plugin versions, capability fixtures, known gaps and security evidence.

Open decisions with proposed defaults: single workspace UI first with workspace IDs throughout storage; no arbitrary untrusted plugin upload; Flink 2.x first; Cloud SQL PostgreSQL/MySQL only; Spanner GoogleSQL only; external catalog optional; no mandatory service mesh or broker. These defaults make scope concrete and can be changed before implementation.

## References and source boundaries

Official documentation checked during this design. Latest/main pages evolve: freeze versions and rerun fixtures before implementation. Product decisions and acceptance targets above are proposals, not upstream guarantees.

- Airflow Spark integration: https://airflow.apache.org/docs/apache-airflow-providers-openlineage/stable/spark.html
- Airflow limitations: https://airflow.apache.org/docs/apache-airflow-providers-openlineage/stable/troubleshooting.html
- OpenLineage Spark installation: https://openlineage.io/docs/integrations/spark/installation/
- OpenLineage Flink 2.x coverage: https://github.com/OpenLineage/OpenLineage/blob/main/website/docs/integrations/flink/flink2.md
- Spark Structured Streaming guide: https://spark.apache.org/docs/3.5.6/structured-streaming-programming-guide.html
- DataHub ingestion framework: https://docs.datahub.com/docs/architecture/metadata-ingestion
- DataHub metadata-file sink: https://github.com/datahub-project/datahub/blob/master/metadata-ingestion/sink_docs/metadata-file.md
- OpenMetadata connector interfaces: https://docs.open-metadata.org/v1.12.x/connectors/custom-connectors
- BigQuery job history: https://docs.cloud.google.com/bigquery/docs/information-schema-jobs
- Spanner information schema: https://docs.cloud.google.com/spanner/docs/information-schema
- Cloud SQL language connectors: https://docs.cloud.google.com/sql/docs/postgres/connect-connectors
- Kubernetes security: https://kubernetes.io/docs/concepts/security/
- OpenAPI: https://spec.openapis.org/oas/latest.html
- CloudEvents: https://cloudevents.io/
- MCP: https://modelcontextprotocol.io/specification/latest

References to CloudEvents, OpenAPI and MCP establish protocol choices; exact supported versions are pinned in the compatibility gate. No machine-readable schema, Helm chart, container or application has been implemented by this proposal.
