import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Bell,
  BookOpen,
  Box,
  Check,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Database,
  ExternalLink,
  GitBranch,
  LayoutDashboard,
  LoaderCircle,
  Radio,
  RefreshCw,
  Search,
  ShieldCheck,
  TriangleAlert,
  X,
} from "lucide-react";
import type { ColumnTarget, DemoState, Health } from "./domain/model";
import { filterAssets, minutesAgo, qualityRate } from "./domain/model";
import { api } from "./api";

const LineageFlow = lazy(() => import("./components/LineageFlow"));

type View = "Overview" | "Assets" | "Incidents" | "Lineage" | "Connections";
const nav = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Assets", icon: Database },
  { name: "Incidents", icon: Bell },
  { name: "Lineage", icon: GitBranch },
  { name: "Connections", icon: Radio },
] as const;
const healthLabels: Record<Health, string> = {
  healthy: "Healthy",
  warning: "Warning",
  critical: "Critical",
  unknown: "Unknown",
};
function Badge({ status }: { status: Health | string }) {
  return (
    <span className={`badge ${status.toLowerCase()}`}>
      <i />
      {healthLabels[status as Health] || status}
    </span>
  );
}
function SourceIcon({ source }: { source: string }) {
  return (
    <span className={`source-icon ${source.toLowerCase()}`}>
      <Database size={16} />
    </span>
  );
}
function Sparkline({ color, values }: { color: string; values: number[] }) {
  return (
    <svg className="sparkline" viewBox="0 0 100 30" aria-hidden="true">
      <polyline
        points={values
          .map((v, i) => `${(i * 100) / (values.length - 1)},${30 - v}`)
          .join(" ")}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function App() {
  const [data, setData] = useState<DemoState | null>(null);
  const [error, setError] = useState("");
  const [view, setView] = useState<View>("Overview");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("all");
  const [source, setSource] = useState("all");
  const [columnTarget, setColumnTarget] = useState<ColumnTarget | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [tab, setTab] = useState("Overview");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [showResolved, setShowResolved] = useState(false);
  const [help, setHelp] = useState(false);
  const returnFocus = useRef<HTMLElement | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    let active = true;
    api
      .state()
      .then((s) => {
        if (active) setData(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, []);
  useEffect(() => {
    if (!selected) return;
    closeRef.current?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSelected(null);
      if (event.key === "Tab") {
        const elements = Array.from(
          document.querySelectorAll<HTMLElement>(
            ".drawer button:not([disabled]), .drawer a[href], .drawer select",
          ),
        );
        const first = elements[0],
          last = elements.at(-1);
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last?.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      returnFocus.current?.focus();
    };
  }, [selected]);
  const openAsset = (id: string) => {
    returnFocus.current = document.activeElement as HTMLElement;
    setSelected(id);
    setTab("Schema");
  };
  const openColumn = (id: string, field: string) => {
    setSelected(null);
    setView("Lineage");
    setColumnTarget({ id, field });
  };
  async function mutate(action: () => Promise<DemoState>, message: string) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      setData(await action());
      setNotice(message);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  if (!data)
    return (
      <main className="loading">
        <Activity size={40} />
        <h1>Signal</h1>
        {error ? (
          <>
            <p role="alert">Could not reach the Python API: {error}</p>
            <p>Start the backend on port 8000 and reload.</p>
            <button onClick={() => window.location.reload()}>Retry</button>
          </>
        ) : (
          <p role="status">Connecting to your observability workspace…</p>
        )}
      </main>
    );
  const assets = filterAssets(data.assets, query, status, source);
  const activeIncidents = data.incidents.filter((i) => i.state !== "resolved");
  const healthy = data.assets.filter((a) => a.health === "healthy").length;
  const critical = data.assets.filter((a) => a.health === "critical").length;
  const asset = data.assets.find((a) => a.id === selected);

  const rate = qualityRate(data.assets);
  const navigate = (next: View) => {
    setView(next);
    setColumnTarget(null);
    setQuery("");
    setStatus("all");
    setSource("all");
  };
  const assetTable = (
    <section className="panel asset-panel">
      <div className="panel-heading">
        <div>
          <h2>
            {view === "Overview" ? "Monitored assets" : "Asset catalog"}{" "}
            <span className="count">{data.assets.length}</span>
          </h2>
          <p>Publication evidence and quality, in one place.</p>
        </div>
        {view === "Overview" && (
          <button className="text-button" onClick={() => navigate("Assets")}>
            View all assets <ArrowRight size={14} />
          </button>
        )}
      </div>
      <div className="table-toolbar">
        <label className="search">
          <Search size={16} />
          <input
            aria-label="Search assets"
            placeholder="Search by asset, namespace, or owner…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
        <div className="filters">
          <label>
            <span className="sr-only">Health filter</span>
            <select
              aria-label="Health filter"
              value={status}
              onChange={(e) => setStatus(e.target.value)}
            >
              <option value="all">All health</option>
              {Object.entries(healthLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label>
            <span className="sr-only">Source filter</span>
            <select
              aria-label="Source filter"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="all">All sources</option>
              {["BigQuery", "PostgreSQL", "Kafka", "Spanner"].map((s) => (
                <option key={s}>{s}</option>
              ))}
            </select>
          </label>
        </div>
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Asset name</th>
              <th>Health</th>
              <th>Last publication</th>
              <th>Quality checks</th>
              <th>Owner</th>
              <th>
                <span className="sr-only">Open asset</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {assets.map((a) => (
              <tr key={a.id}>
                <td>
                  <div className="asset-name">
                    <SourceIcon source={a.source} />
                    <div>
                      <button
                        className="asset-link"
                        onClick={() => openAsset(a.id)}
                      >
                        {a.name}
                      </button>
                      <small>{a.namespace}</small>
                    </div>
                  </div>
                </td>
                <td>
                  <Badge status={a.health} />
                </td>
                <td>
                  <span
                    className={
                      !a.monitorAvailable
                        ? "muted"
                        : a.health === "critical"
                          ? "late"
                          : ""
                    }
                  >
                    {minutesAgo(a.publishedAt, data.now)}
                  </span>
                  <small>{a.freshnessMinutes}m freshness policy</small>
                </td>
                <td>
                  <span className="quality-dots">
                    {a.checks.map((c) => (
                      <i
                        key={c.id}
                        className={c.status.toLowerCase()}
                        title={`${c.name}: ${c.status}`}
                      />
                    ))}
                  </span>
                  <span className="check-count">
                    {a.checks.filter((c) => c.status === "PASS").length}/
                    {a.checks.length} passing
                  </span>
                </td>
                <td>
                  <span className="owner-avatar">{a.owner.slice(0, 1)}</span>
                  {a.owner}
                </td>
                <td>
                  <button
                    className="icon-button"
                    aria-label={`Inspect ${a.name}`}
                    onClick={() => openAsset(a.id)}
                  >
                    <ChevronRight size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {!assets.length && (
          <div className="empty">
            <Search size={26} />
            <h3>No assets match your filters</h3>
            <p>Try another name, health status, or source.</p>
            <button
              onClick={() => {
                setQuery("");
                setStatus("all");
                setSource("all");
              }}
            >
              Clear filters
            </button>
          </div>
        )}
      </div>
      <div className="table-footer">
        <span>
          Showing {assets.length} of {data.assets.length} assets
        </span>
        <span>
          <i className="live-dot" /> Python API · SQLite demo store
        </span>
      </div>
    </section>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("Overview");
          }}
        >
          <span className="brand-mark">
            <Activity size={22} />
          </span>
          signal<span className="brand-dot">.</span>
        </a>
        <button className="workspace" onClick={() => setHelp(!help)}>
          <span className="workspace-icon">S</span>
          <span>
            Sandbox workspace<small>Local proof of concept</small>
          </span>
          <ChevronDown size={14} />
        </button>
        <span className="nav-caption">WORKSPACE</span>
        <nav aria-label="Main navigation">
          {nav.map((n) => (
            <button
              key={n.name}
              className={view === n.name ? "active" : ""}
              onClick={() => navigate(n.name)}
            >
              <n.icon size={18} />
              {n.name}
              {n.name === "Incidents" && (
                <span className="nav-count">{activeIncidents.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="demo-card">
            <span>
              <Box size={15} /> POC environment
            </span>
            <p>Explore the platform with reproducible sample evidence.</p>
            <button onClick={() => setHelp(!help)}>
              About this demo <ArrowUpRight size={13} />
            </button>
          </div>
          <button className="help-button" onClick={() => setHelp(!help)}>
            <CircleHelp size={17} /> Help & documentation
          </button>
          <div className="profile">
            <span className="avatar">SM</span>
            <div>
              Soumyadeep<small>Workspace owner</small>
            </div>
            <span className="profile-dot" />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumbs">
            Workspace <ChevronRight size={14} />
            <span>{view}</span>
          </div>
          <div className="topbar-right">
            <span className="environment">
              <i /> Demo environment
            </span>
            <button
              className="icon-button"
              aria-label="View incidents"
              onClick={() => navigate("Incidents")}
            >
              <Bell size={18} />
              {activeIncidents.length > 0 && (
                <span className="notification-dot" />
              )}
            </button>
            <span className="avatar small">SM</span>
          </div>
        </header>
        <main id="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">DATA OBSERVABILITY</div>
              <h1>{view === "Overview" ? "Your data, in focus." : view}</h1>
              <p>
                {
                  {
                    Overview:
                      "A clear picture of reliability across your data ecosystem.",
                    Assets:
                      "Discover your data. Understand its health and dependencies.",
                    Incidents:
                      "Investigate issues, acknowledge ownership, and track resolution.",
                    Lineage:
                      "Follow the flow of data and understand downstream impact.",
                    Connections:
                      "Understand collection coverage across your source systems.",
                  }[view]
                }
              </p>
            </div>
            <div className="heading-actions">
              <span className="date-label">Nov 1, 2026 · 12:00 UTC</span>
              <button
                className="button secondary"
                disabled={busy}
                onClick={() =>
                  mutate(api.state, "Workspace refreshed from the Python API.")
                }
              >
                <RefreshCw size={15} className={busy ? "spin" : ""} /> Refresh
              </button>
            </div>
          </div>
          {error && (
            <div role="alert" className="message error">
              {error}
              <button aria-label="Dismiss error" onClick={() => setError("")}>
                <X size={15} />
              </button>
            </div>
          )}
          {notice && (
            <div role="status" className="message success">
              <Check size={16} />
              {notice}
              <button
                aria-label="Dismiss notification"
                onClick={() => setNotice("")}
              >
                <X size={15} />
              </button>
            </div>
          )}
          {help && (
            <section className="help-panel">
              <div>
                <BookOpen size={20} />
                <h2>Built for a clearer view of your data</h2>
              </div>
              <p>
                This is a local POC with a React + TypeScript UI and a Python
                FastAPI backend. All assets and connectors are sample fixtures.
                The demo clock is fixed at November 1, 2026, 12:00 UTC. Changes
                persist in SQLite.
              </p>
              <p>
                Health comes from the Python API. Publication simulation updates
                freshness only; quality failures remain. Resolving an incident
                records triage and does not alter evidence. Lineage is
                explicitly declared, not automatically discovered.
              </p>
              <a
                href="http://127.0.0.1:8000/docs"
                target="_blank"
                rel="noreferrer"
              >
                Explore the API documentation <ExternalLink size={14} />
              </a>
              <button
                className="text-button"
                disabled={busy}
                onClick={() =>
                  mutate(
                    api.reset,
                    "Demo reset to the original sample evidence.",
                  )
                }
              >
                Reset demo data
              </button>
            </section>
          )}
          {view === "Overview" && (
            <>
              <div className="metrics">
                <Metric
                  label="Monitored assets"
                  value={String(data.assets.length)}
                  detail="Across 4 sample sources"
                  icon={<Database size={18} />}
                  color="#7585a3"
                  values={[11, 13, 12, 17, 17, 22, 24, 24, 27]}
                />
                <Metric
                  label="Healthy assets"
                  value={`${healthy}/${data.assets.length}`}
                  detail={`${Math.round((healthy / data.assets.length) * 100)}% of monitored assets`}
                  icon={<ShieldCheck size={18} />}
                  color="#17a580"
                  values={[20, 23, 20, 25, 21, 19, 24, 22, 24]}
                />
                <Metric
                  label="Active incidents"
                  value={String(activeIncidents.length)}
                  detail={`${critical} assets need attention`}
                  icon={<TriangleAlert size={18} />}
                  color="#e39148"
                  values={[5, 5, 13, 8, 8, 19, 16, 22, 21]}
                />
                <Metric
                  label="Quality pass rate"
                  value={rate === null ? "—" : `${rate}%`}
                  detail="Excludes error / skipped checks"
                  icon={<Activity size={18} />}
                  color="#8674d5"
                  values={[26, 23, 25, 23, 27, 25, 19, 23, 24]}
                />
              </div>
              <div className="overview-grid">
                <section className="panel health-panel">
                  <div className="panel-heading">
                    <div>
                      <h2>Asset health</h2>
                      <p>Current state from the latest sample evidence</p>
                    </div>
                    <span className="subtle-tag">Snapshot</span>
                  </div>
                  <div className="health-content">
                    <div
                      className="health-ring"
                      style={{
                        background: `conic-gradient(#23a384 0 ${(healthy / data.assets.length) * 100}%, #e3a450 ${(healthy / data.assets.length) * 100}% ${((healthy + data.assets.filter((a) => a.health === "warning").length) / data.assets.length) * 100}%, #df6a6a ${((healthy + data.assets.filter((a) => a.health === "warning").length) / data.assets.length) * 100}% ${((data.assets.length - data.assets.filter((a) => a.health === "unknown").length) / data.assets.length) * 100}%, #cbd2dc 0)`,
                      }}
                    >
                      <div>
                        <strong>{data.assets.length}</strong>
                        <span>total assets</span>
                      </div>
                    </div>
                    <div className="health-legend">
                      {(
                        [
                          "healthy",
                          "warning",
                          "critical",
                          "unknown",
                        ] as Health[]
                      ).map((h) => (
                        <button
                          key={h}
                          onClick={() => {
                            setView("Assets");
                            setStatus(h);
                          }}
                        >
                          <span>
                            <i className={h} />
                            {healthLabels[h]}
                          </span>
                          <strong>
                            {data.assets.filter((a) => a.health === h).length}
                          </strong>
                        </button>
                      ))}
                    </div>
                  </div>
                </section>
                <section className="panel incident-preview">
                  <div className="panel-heading">
                    <div>
                      <h2>
                        Needs your attention{" "}
                        <span className="count orange">
                          {activeIncidents.length}
                        </span>
                      </h2>
                      <p>Open issues across your data ecosystem</p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("Incidents")}
                    >
                      View incidents <ArrowRight size={14} />
                    </button>
                  </div>
                  {activeIncidents.slice(0, 3).map((i) => (
                    <button
                      className="incident-row"
                      key={i.id}
                      onClick={() =>
                        i.column
                          ? openColumn(i.assetId, i.column)
                          : openAsset(i.assetId)
                      }
                    >
                      <span className={`incident-symbol ${i.severity}`}>
                        <TriangleAlert size={17} />
                      </span>
                      <span>
                        <strong>{i.title}</strong>
                        <small>
                          {data.assets.find((a) => a.id === i.assetId)?.name}{" "}
                          <b>·</b> {i.dimension}
                        </small>
                      </span>
                      <span className="incident-age">
                        {minutesAgo(i.openedAt, data.now)}
                        <ChevronRight size={14} />
                      </span>
                    </button>
                  ))}
                  {!activeIncidents.length && (
                    <div className="empty">
                      <ShieldCheck />
                      <p>No active incidents.</p>
                    </div>
                  )}
                </section>
              </div>
              {assetTable}
            </>
          )}
          {view === "Assets" && assetTable}
          {view === "Incidents" && (
            <section className="panel">
              <div className="panel-heading">
                <div>
                  <h2>
                    Incident inbox{" "}
                    <span className="count">{activeIncidents.length}</span>
                  </h2>
                  <p>Triage state is separate from underlying asset health.</p>
                </div>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={showResolved}
                    onChange={(e) => setShowResolved(e.target.checked)}
                  />{" "}
                  Include resolved
                </label>
              </div>
              <div className="incident-list">
                {data.incidents
                  .filter((i) => showResolved || i.state !== "resolved")
                  .map((i) => (
                    <article className="incident-card" key={i.id}>
                      <span className={`incident-symbol ${i.severity}`}>
                        <TriangleAlert size={20} />
                      </span>
                      <div className="incident-body">
                        <small>
                          {i.id} · {i.dimension}
                        </small>
                        <h3>{i.title}</h3>
                        <button
                          className="asset-link"
                          onClick={() =>
                            i.column
                              ? openColumn(i.assetId, i.column)
                              : openAsset(i.assetId)
                          }
                        >
                          {data.assets.find((a) => a.id === i.assetId)?.name}
                          {i.column ? `.${i.column}` : ""}
                        </button>
                        <p>
                          Opened {minutesAgo(i.openedAt, data.now)} ·{" "}
                          <Badge status={i.state} />
                        </p>
                      </div>
                      {i.state !== "resolved" && (
                        <button
                          className="button secondary"
                          disabled={busy}
                          onClick={() =>
                            mutate(
                              () =>
                                api.incident(
                                  i.id,
                                  i.state === "open"
                                    ? "acknowledged"
                                    : "resolved",
                                ),
                              `${i.id} ${i.state === "open" ? "acknowledged" : "resolved"}.`,
                            )
                          }
                        >
                          {i.state === "open"
                            ? "Acknowledge"
                            : "Resolve incident"}
                        </button>
                      )}
                    </article>
                  ))}
                {!activeIncidents.length && !showResolved && (
                  <div className="empty">
                    <ShieldCheck size={32} />
                    <h3>Your inbox is clear</h3>
                    <p>All sample incidents have been resolved.</p>
                  </div>
                )}
              </div>
            </section>
          )}
          {view === "Lineage" && (
            <Suspense
              fallback={
                <div className="panel flow-placeholder">
                  Loading lineage view…
                </div>
              }
            >
              <LineageFlow
                assets={data.assets}
                onInspect={openAsset}
                assetId={columnTarget?.id}
                initialColumn={columnTarget}
              />
            </Suspense>
          )}
          {view === "Connections" && (
            <>
              <div className="connection-grid">
                {["BigQuery", "PostgreSQL", "Kafka", "Spanner"].map((s) => {
                  const group = data.assets.filter((a) => a.source === s);
                  const available = group.every((a) => a.monitorAvailable);
                  return (
                    <section key={s} className="panel connection-card">
                      <div className="connection-title">
                        <SourceIcon source={s} />
                        <span className="subtle-tag">Sample connector</span>
                      </div>
                      <h2>{s}</h2>
                      <Badge status={available ? "healthy" : "unknown"} />
                      <p>
                        {group.length} assets ·{" "}
                        {available
                          ? "Sample evidence available"
                          : "Collector unavailable"}
                      </p>
                      <dl>
                        <dt>Schema discovery</dt>
                        <dd>Fixture only</dd>
                        <dt>Table lineage</dt>
                        <dd>Declared</dd>
                        <dt>Column lineage</dt>
                        <dd>Facet fixtures only</dd>
                        <dt>Live source access</dt>
                        <dd>Not configured</dd>
                      </dl>
                      <button
                        className="text-button"
                        onClick={() => {
                          setView("Assets");
                          setSource(s);
                        }}
                      >
                        Explore assets <ArrowRight size={14} />
                      </button>
                    </section>
                  );
                })}
              </div>
              <div className="help-panel">
                <h2>Connectors are the next integration milestone</h2>
                <p>
                  This POC makes no outbound connections to warehouses or
                  streaming systems. Source credentials, isolated connector
                  workers, and production authentication are part of the
                  proposed release architecture.
                </p>
              </div>
            </>
          )}
          <footer className="page-footer">
            <span>
              <Activity size={13} /> Signal observability
            </span>
            <span>
              Sample evidence · Fixed demo clock · Python + TypeScript
            </span>
          </footer>
        </main>
      </div>
      {asset && (
        <div className="overlay" onClick={() => setSelected(null)}>
          <section
            className="drawer"
            role="dialog"
            aria-modal="true"
            aria-labelledby="asset-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="drawer-top">
              <span>ASSET DETAILS</span>
              <button
                ref={closeRef}
                className="icon-button"
                aria-label="Close asset details"
                onClick={() => setSelected(null)}
              >
                <X size={20} />
              </button>
            </div>
            <div className="drawer-heading">
              <SourceIcon source={asset.source} />
              <h2 id="asset-title">{asset.name}</h2>
              <Badge status={asset.health} />
            </div>
            <p className="namespace">{asset.namespace}</p>
            <p className="description">{asset.description}</p>
            <div className="tabs" role="tablist" aria-label="Asset information">
              {["Overview", "Schema", "Quality", "Lineage"].map((t) => (
                <button
                  role="tab"
                  aria-selected={tab === t}
                  key={t}
                  onClick={() => setTab(t)}
                >
                  {t}
                </button>
              ))}
            </div>
            <div role="tabpanel" aria-label={tab} className="drawer-content">
              {tab === "Overview" && (
                <>
                  <dl className="detail-grid">
                    <div>
                      <dt>Owner</dt>
                      <dd>{asset.owner}</dd>
                    </div>
                    <div>
                      <dt>Source</dt>
                      <dd>{asset.source}</dd>
                    </div>
                    <div>
                      <dt>Sample row count</dt>
                      <dd>{asset.rows}</dd>
                    </div>
                    <div>
                      <dt>Freshness policy</dt>
                      <dd>{asset.freshnessMinutes} minutes</dd>
                    </div>
                  </dl>
                  <section className="evidence-card">
                    <h3>
                      <Activity size={17} /> Publication evidence
                    </h3>
                    <strong>{minutesAgo(asset.publishedAt, data.now)}</strong>
                    <p>
                      {asset.publishedAt || "No publication evidence available"}
                    </p>
                    <p>
                      Collector:{" "}
                      {asset.monitorAvailable
                        ? "available (sample)"
                        : "unavailable"}
                      . A successful job alone does not prove output
                      publication.
                    </p>
                    <button
                      className="button primary"
                      disabled={busy}
                      onClick={() =>
                        mutate(
                          async () =>
                            (await api.publish(asset.id, data.now)).state,
                          "Sample sink commit recorded. Quality evidence is unchanged.",
                        )
                      }
                    >
                      <RefreshCw size={15} /> Simulate publication
                    </button>
                    <small>
                      Writes a sample sink commit to the Python API.
                    </small>
                  </section>
                  <div className="info-note">
                    <CircleHelp size={18} />
                    <p>
                      Health is evaluated by Python against the fixed demo
                      clock. Quality failures remain critical after publication.
                    </p>
                  </div>
                </>
              )}
              {tab === "Schema" && (
                <>
                  <div className="panel-heading">
                    <h3>Current schema</h3>
                    <span className="subtle-tag">Fixture v1</span>
                  </div>
                  <table className="schema-table">
                    <thead>
                      <tr>
                        <th>Column</th>
                        <th>Type</th>
                        <th>Nullable</th>
                        <th>Lineage</th>
                      </tr>
                    </thead>
                    <tbody>
                      {asset.columns.map((c) => (
                        <tr key={c.name}>
                          <td>{c.name}</td>
                          <td>
                            <code>{c.type}</code>
                          </td>
                          <td>{c.nullable ? "Yes" : "No"}</td>
                          <td>
                            <button
                              className="text-button"
                              aria-label={`Trace column ${c.name}`}
                              onClick={() => openColumn(asset.id, c.name)}
                            >
                              <GitBranch size={13} /> Trace
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  <p className="section-note">
                    Schema history and diff are planned; this POC exposes one
                    sample schema.
                  </p>
                </>
              )}
              {tab === "Quality" && (
                <>
                  <h3>Quality checks</h3>
                  <p className="muted">
                    FAIL means a failed assertion. ERROR means the check could
                    not execute.
                  </p>
                  {asset.checks.map((c) => (
                    <div className="quality-check" key={c.id}>
                      <div>
                        <strong>{c.name}</strong>
                        <small>Column: {c.column}</small>
                        <p>{c.value}</p>
                      </div>
                      <Badge status={c.status} />
                    </div>
                  ))}
                </>
              )}
              {tab === "Lineage" && (
                <Suspense fallback={<p role="status">Loading lineage view…</p>}>
                  <LineageFlow
                    assets={data.assets}
                    assetId={asset.id}
                    onInspect={setSelected}
                  />
                </Suspense>
              )}
            </div>
            {busy && (
              <p className="drawer-status" role="status">
                <LoaderCircle className="spin" size={15} /> Saving to Python
                API…
              </p>
            )}
            {error && (
              <p role="alert" className="drawer-error">
                {error}
              </p>
            )}
            {notice && (
              <p role="status" className="drawer-notice">
                {notice}
              </p>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
function Metric({
  label,
  value,
  detail,
  icon,
  color,
  values,
}: {
  label: string;
  value: string;
  detail: string;
  icon: React.ReactNode;
  color: string;
  values: number[];
}) {
  return (
    <section className="metric">
      <div className="metric-label">
        {label}
        <span>{icon}</span>
      </div>
      <div className="metric-value">
        <strong>{value}</strong>
        <Sparkline color={color} values={values} />
      </div>
      <p>
        {label === "Active incidents" ? (
          <ArrowUpRight size={13} />
        ) : (
          <ArrowDownRight size={13} />
        )}{" "}
        {detail}
      </p>
      <span className="sr-only">Decorative sample sparkline</span>
    </section>
  );
}
