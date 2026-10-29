# Cloud-native security design

Date: 29 October 2026  
Status: proposed design guidance; controls are not yet implemented or verified.

This document extends the [platform architecture](data_observability_design.md). It adapts the supplied Kubernetes/GKE guidance into a portable application security design. Organization-specific procedures, historical gaps, and enforcement labels in the source guideline are not requirements or evidence of controls in this project.

The same security boundaries apply to Go and Python backend implementations and the TypeScript UI. Cloud-specific infrastructure should be separate from portable application configuration.

## 1. Scope and trust boundaries

Protect asset metadata, schema and lineage, execution evidence, quality results, policies, source credentials, audit records, and administrative operations. Metadata can reveal confidential business structure even without source rows.

Trust boundaries include:
- Browser, Airflow producers, OpenLineage clients, and remote MCP clients to the application.
- Application API to database, scheduler, and workers.
- Connector workers to external data sources.
- Workloads to cloud identity and secret services.
- CI/CD to image registry and deployment infrastructure.

Primary threats include unauthorized metadata access, forged producer events, cross-workspace access, malicious connector configuration, credential leakage, vulnerable images, excessive privileges, and resource exhaustion.

## 2. Authentication and authorization

| Surface | Proposed approach |
|---|---|
| Human users | OpenID Connect with an external identity provider; authorization code flow with PKCE |
| Browser session | Prefer server-managed sessions in Secure, HttpOnly cookies; apply CSRF protection to cookie-authenticated mutations |
| Airflow and producers | Individual machine identities with scoped, short-lived access tokens where supported |
| Connector workers | Separate source-specific identities and credentials; avoid shared administrator credentials |
| REST and OpenLineage endpoints | Authenticate requests and authorize the identity for the target workspace and assets |
| Remote MCP | Follow the supported MCP authorization specification; validate tokens intended for this server and enforce the same domain permissions as REST |
| Cloud resources | Workload identity federation in production; no downloaded cloud account keys as the default |

Validate issuer, audience, signature, expiration, and relevant scopes. Reject tokens intended for a different service. Never pass arbitrary client bearer tokens through to data sources.

Suggested application roles:
- Viewer: permitted metadata, lineage, quality and health reads.
- Producer: report observations for assigned assets or namespaces.
- Connector operator: manage assigned connectors and inspect sanitized execution results.
- Administrator: manage application access, policies and configuration.

Kubernetes RBAC controls Kubernetes resources; it does not replace application authorization. If multiple workspaces are supported, every query, cache key, job, and historical lookup must preserve workspace isolation. PostgreSQL row-level security can provide defense in depth when designed and tested carefully.

Apply rate, request size, batch size, and execution limits per identity. Preserve idempotency and asset identity validation for incoming events.

## 3. Transport and network isolation

Use HTTPS for external REST, OpenLineage, UI and remote MCP traffic. Verify certificates and hostnames for database and source connections. Use modern TLS configurations, normally TLS 1.2 minimum with TLS 1.3 where supported.

Document where TLS terminates. If a gateway terminates TLS, separately secure traffic crossing subsequent trust boundaries. Mutual TLS may be added for selected service or connector paths; a service mesh is not a prerequisite for the first version.

Start application namespaces with default-deny ingress and egress NetworkPolicies. Explicitly permit required flows:

| Origin | Destination | Purpose |
|---|---|---|
| Gateway | API | Authenticated application traffic |
| API and authorized workers | PostgreSQL | State, observations, history and durable work |
| Workloads | Approved DNS | Name resolution |
| API | Identity provider | Authentication metadata and token operations as needed |
| Connector workers | Approved source endpoints | Source-specific collection |
| Authorized workloads | Secret and identity endpoints | Credentials and short-lived identity |
| Telemetry agents/workloads | Approved telemetry services | Sanitized operational telemetry |

Allow health checks, platform dependencies and cloud metadata-server access only as needed. Verify actual behavior for the chosen CNI and cloud platform.

Standard Kubernetes NetworkPolicy is primarily an L3/L4 mechanism. It does not provide general hostname, URL-path or HTTP authorization enforcement. Domain-based egress restrictions may require a suitable CNI extension or controlled egress proxy. Account for DNS changes and redirects.

Private nodes and restricted control-plane access are production infrastructure goals. IP allow-lists supplement authentication. Do not expose PostgreSQL or worker control endpoints publicly.

## 4. Connector isolation and SSRF defenses

Connectors execute source-specific libraries and have access to valuable credentials. Treat them as a separate trust boundary:
- Execute collection in separate worker pods or jobs, outside API request processing.
- Use bounded concurrency, timeouts, retry limits, CPU/memory limits and cancellation.
- Give each worker only the source access and credentials it needs.
- Restrict configurable protocols, destinations, ports and redirect behavior.
- Validate destinations at connection time, including resolved addresses; handle DNS rebinding and redirects.
- Block unintended loopback, link-local and cloud metadata destinations. Private database addresses are allowed only through explicit source configuration and network policy.
- Route arbitrary-destination integrations through a controlled egress path where necessary.
- Redact source responses and credentials from diagnostics.

A connector must not receive Kubernetes administration rights or arbitrary host access. Separate credentials by source and environment. Namespace separation alone is not a complete boundary for hostile third-party code; assess stronger sandboxing or dedicated clusters if untrusted plugin execution becomes a product feature.

## 5. Pods and Kubernetes permissions

Target the Restricted Pod Security Standard for application namespaces, with version-pinned policy configuration and explicitly reviewed exceptions:
- Run as non-root and disable privilege escalation.
- Drop Linux capabilities and use RuntimeDefault seccomp.
- Avoid privileged containers, host networking, host PID/IPC and hostPath mounts.
- Prefer a read-only root filesystem; mount bounded temporary storage where needed.
- Configure resource requests/limits and namespace quotas.
- Use dedicated service accounts by process role.
- Disable automatic service-account token mounting where no Kubernetes or workload-identity token is needed.
- Grant only required namespaced Kubernetes permissions; most application processes should not need Kubernetes API access.

Use native Pod Security Admission initially. Add ValidatingAdmissionPolicy or a policy engine when checks beyond its scope are justified, such as required image provenance or forbidden public exposure.

Separate node pools can reduce workload interference, but taints and labels alone are not a strong security boundary.

## 6. Secrets and workload identity

Never store credentials in source control, container images, ConfigMaps, example manifests, committed Helm values or logs. Rotate exposed credentials promptly; history cleanup does not revoke a leaked credential.

Production secrets should originate in an external secret manager. Mount secret files where practical using a CSI integration or suitable synchronization mechanism. If using Kubernetes Secrets, restrict access and configure encryption at rest. A Kubernetes Secret is not automatically encrypted merely because its payload is base64 encoded.

Injecting a Kubernetes Secret into an environment variable retains the exposure characteristics of environment variables. Mounted files still require access controls and rotation handling. Applications should reload rotated credentials or restart in a controlled way.

GKE Workload Identity Federation supports direct resource access as well as service-account impersonation. A Kubernetes-to-Google-service-account binding is not universally required. Choose the method supported by each target service and grant the minimum resource-level permissions.

Keep cloud identities and bindings distinct by environment. Use short-lived federation for CI/CD where available.

## 7. Metadata, database and audit protection

Collect metadata and aggregate quality metrics by default. Raw rows, failed-row samples and query text require explicit collection policies, redaction and access controls. Avoid exposing sensitive SQL literals in lineage or audit output.

Use separate database roles for application operations, migrations and maintenance. Keep administrative credentials out of API pods. Encrypt database storage and backups; restrict backup access and test recovery.

Audit:
- Authentication and authorization failures.
- Role, policy and connector configuration changes.
- Administrative operations and MCP mutations.
- Retention changes and manual destructive operations.

Record actor, workspace, action, target, timestamp, outcome and correlation ID. Do not record passwords, bearer tokens or full sensitive payloads. Protect audit records from application-level tampering; stronger production requirements may use a separate restricted audit sink.

Asset-history retention and security-audit retention are separate policies. Deleting source credentials or applying audit redaction must not depend on waiting for the asset-history window to expire.

## 8. MCP-specific behavior

Start MCP with read-only search, asset, lineage, health and history tools. Add mutations only with explicit scopes, authorization, audit records and appropriate client confirmation behavior.

Treat metadata descriptions, SQL comments and connector output as untrusted content. They must not change tool permissions or trigger privileged operations. Return only data the caller is authorized to access.

Remote MCP transports use HTTPS. A local stdio MCP adapter has a different boundary: local process permissions and its configured credentials. Neither transport bypasses application authorization.

## 9. Local and production profiles

Use one portable Helm chart with separate configuration profiles.

| Control | Local Kubernetes | Cloud production |
|---|---|---|
| Cluster | Kind or equivalent with a NetworkPolicy-capable CNI | Managed Kubernetes with hardened infrastructure |
| Identity provider | Local test OIDC provider and synthetic users | Organizational identity provider |
| TLS | Locally trusted development CA | Managed certificate lifecycle |
| Secrets | Disposable development credentials, outside Git | External secret manager and rotation |
| Cloud access | Mock adapters or narrowly scoped development identity | Workload identity federation |
| Data | Synthetic datasets and metadata | Authorized production sources |
| Pod and network controls | Enforce and test portable policies | Same controls plus cloud-specific protections |
| PostgreSQL | In-cluster instance for testing | Private database, backups and recovery procedures |
| Image policy | Local build workflow with explicit development exceptions | Approved registry, digest pinning and verified provenance |

Local overrides must not silently disable production security. Prefer configuration validation that rejects insecure combinations in the production profile.

Local tests cannot prove cloud IAM, KMS, VPC perimeter, managed database or private-network configuration. Test those in a small cloud staging environment.

## 10. GKE production overlay

Evaluate these infrastructure controls for the chosen deployment:
- Private nodes and private or tightly restricted control-plane access.
- Dedicated least-privilege node identities and workload federation.
- Dataplane V2 with tested NetworkPolicies.
- Approved image registry and Binary Authorization or equivalent provenance enforcement.
- Shielded nodes, supported release lifecycle and vulnerability scanning.
- Private database access, backups and deletion protection.
- Customer-managed encryption keys when required by risk or organizational policy.
- Controlled outbound access with explicit identity and Google API dependencies.
- VPC Service Controls for supported data services when justified.

Dataplane V2 already provides NetworkPolicy enforcement; a disabled legacy network-policy add-on alone does not prove enforcement is absent. VPC Service Controls protect supported service perimeters; they are not a general replacement for pod network policy or application authorization.

Cloud organization policies, shared networking approvals and separation-of-duties processes depend on the operator. They are not portable application requirements. Do not copy historical provider quotas or environment exceptions into chart defaults.

## 11. Supply chain and delivery

Pin production image digests. Generate SBOMs, scan dependencies and images, and verify signing/provenance before deployment. Keep signing identities and CI permissions narrow. GKE Binary Authorization is a provider-specific option; portable installations can use an appropriate admission mechanism.

Manage infrastructure and deployment configuration through reviewed code. Validate in non-production before production. Avoid standing broad deployment credentials and document emergency access with audit and expiry.

Start with a single application codebase, separate process roles and isolated connector workers. These controls do not require a fleet of microservices or a service mesh.

## 12. Acceptance criteria before claiming enforcement

| Check | Expected evidence |
|---|---|
| Authentication | Missing, expired and wrong-audience tokens are rejected |
| Application authorization | Viewer cannot mutate; producer cannot report against unauthorized assets |
| Workspace isolation | REST, MCP, workers and historical queries cannot cross workspace boundaries |
| Network policy | Test pods demonstrate allowed and denied connections with the deployed CNI |
| Pod restrictions | Privileged/root configurations are rejected by the selected admission policy |
| Connector SSRF | Unapproved destinations, redirects and metadata endpoints are blocked; approved private sources work |
| Secret handling | Repository/image scans and log checks show no seeded credentials; rotation is exercised |
| MCP | Tool reads and writes enforce the same permissions as equivalent REST operations |
| Supply chain | Production deployment rejects images missing the required approval/provenance |
| Recovery | Backup restoration and credential revocation are demonstrated |
| Cloud overlay | Staging tests verify workload identity and intended network/perimeter access |

Report each control as proposed, implemented, or verified with a deployment/version and test evidence. A manifest or design statement alone is not proof of enforcement.

## References

Technical reference points reviewed during design; pin deployment versions before implementation:
- [Kubernetes security overview](https://kubernetes.io/docs/concepts/security/)
- [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/)
- [Kubernetes security checklist](https://kubernetes.io/docs/concepts/security/security-checklist/)
- [Good practices for Kubernetes Secrets](https://kubernetes.io/docs/concepts/security/secrets-good-practices/)
- [GKE Workload Identity Federation](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [GKE networking best practices](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/networking)
- [GKE NetworkPolicy configuration](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/network-policy)
