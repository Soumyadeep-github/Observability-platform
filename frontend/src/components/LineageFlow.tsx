import { useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowRight,
  Database,
  GitBranch,
  RefreshCw,
  Workflow,
} from "lucide-react";
import type { Asset, ColumnTarget } from "../domain/model";
import { request } from "../api";
import type {
  ColumnResponse,
  DatasetDetails,
  LineageObject,
  LineageResponse,
} from "../domain/lineage";
import FlowCanvas from "./FlowCanvas";
import {
  traceColumn,
  fieldKey,
  type ColumnSelection,
  type ExpandedDataset,
} from "../domain/columnTrace";
export default function LineageFlow({
  assets,
  onInspect,
  assetId = "",
  initialColumn,
}: {
  assets: Asset[];
  onInspect: (id: string) => void;
  assetId?: string;
  initialColumn?: ColumnTarget | null;
}) {
  const [response, setResponse] = useState<LineageResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [focus, setFocus] = useState(assetId);
  const [expanded, setExpanded] = useState<Record<string, ExpandedDataset>>({});
  const [focusDataset, setFocusDataset] = useState<string | null>(null);
  const [column, setColumn] = useState<ColumnSelection | null>(null);
  const [trace, setTrace] = useState<{
    data: ColumnResponse;
    selectionKey: string;
  } | null>(null);
  const [traceError, setTraceError] = useState("");
  const [tracePending, setTracePending] = useState(false);
  const [traceRetry, setTraceRetry] = useState(0);
  const generation = useRef(0);
  const autoExpanded = useRef<string | null>(null);
  const initialApplied = useRef<ColumnTarget | null>(null);
  const schemaCache = useRef<Record<string, DatasetDetails>>({});
  const schemaRequests = useRef(new Set<string>());
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => setFocus(assetId), [assetId]);
  useEffect(() => {
    let active = true;
    generation.current += 1;
    schemaCache.current = {};
    schemaRequests.current.clear();
    setExpanded({});
    setFocusDataset(null);
    setColumn(null);
    setTrace(null);
    setLoading(true);
    setError("");
    setResponse(null);
    setSelected(null);
    request<LineageResponse>(
      `/lineage?asset_id=${encodeURIComponent(focus)}&depth=6`,
    )
      .then((value) => {
        if (active) setResponse(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      generation.current += 1;
    };
  }, [focus, refresh]);
  useEffect(() => {
    setTrace(null);
    setTraceError("");
    if (!column) {
      setTracePending(false);
      return;
    }
    let active = true;
    setTracePending(true);
    const controller = new AbortController();
    request<ColumnResponse>(
      `/column-lineage?namespace=${encodeURIComponent(column.namespace)}&name=${encodeURIComponent(column.dataset)}&field=${encodeURIComponent(column.field)}&depth=6`,
      { signal: controller.signal },
    )
      .then((value) => {
        if (active)
          setTrace({
            data: value,
            selectionKey: fieldKey(
              column.namespace,
              column.dataset,
              column.field,
            ),
          });
      })
      .catch((error) => {
        if (active) setTraceError(error.message);
      })
      .finally(() => {
        if (active) setTracePending(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [column, traceRetry]);
  const highlight = useMemo(
    () =>
      column &&
      trace &&
      response &&
      trace.selectionKey ===
        fieldKey(column.namespace, column.dataset, column.field)
        ? traceColumn(column, trace.data, response.graph)
        : null,
    [column, trace, response],
  );
  async function loadSchema(node: LineageObject) {
    const token = generation.current,
      key = `${token}:${node.id}`;
    if (schemaRequests.current.has(key)) return;
    schemaRequests.current.add(key);
    setExpanded((current) =>
      current[node.id]
        ? { ...current, [node.id]: { fields: [], loading: true } }
        : current,
    );
    try {
      const details = await request<DatasetDetails>(
        `/dataset-details?namespace=${encodeURIComponent(node.data.namespace)}&name=${encodeURIComponent(node.data.name)}`,
      );
      if (token !== generation.current) return;
      schemaCache.current[node.id] = details;
      setExpanded((current) =>
        current[node.id]
          ? {
              ...current,
              [node.id]: { fields: details.fields, loading: false },
            }
          : current,
      );
    } catch (error) {
      if (token === generation.current)
        setExpanded((current) =>
          current[node.id]
            ? {
                ...current,
                [node.id]: {
                  fields: [],
                  loading: false,
                  error:
                    error instanceof Error
                      ? error.message
                      : "Schema unavailable",
                },
              }
            : current,
        );
    } finally {
      schemaRequests.current.delete(key);
    }
  }
  useEffect(() => {
    if (!column) {
      autoExpanded.current = null;
      return;
    }
    if (!highlight || !response) return;
    const key = JSON.stringify([column.datasetId, column.field]);
    if (autoExpanded.current === key) return;
    autoExpanded.current = key;
    const related = response.graph.filter(
      (node) =>
        node.type === "DATASET" &&
        node.id !== column.datasetId &&
        ["upstream", "downstream", "both"].includes(
          highlight.nodes.get(node.id) || "",
        ),
    );
    const missing = related.filter((node) => !expanded[node.id]);
    if (!missing.length) return;
    setFocusDataset(null);
    setExpanded((current) => {
      const next = { ...current };
      for (const node of missing) {
        const cached = schemaCache.current[node.id];
        next[node.id] = { fields: cached?.fields || [], loading: !cached };
      }
      return next;
    });
    for (const node of missing)
      if (!schemaCache.current[node.id]) void loadSchema(node);
  }, [column, highlight, response]);
  useEffect(() => {
    if (!response || !initialColumn || initialApplied.current === initialColumn)
      return;
    const asset = assets.find((a) => a.id === initialColumn.id);
    const node = response.graph.find(
      (n) =>
        n.type === "DATASET" &&
        n.data.namespace === asset?.namespace &&
        n.data.name === asset?.name,
    );
    if (!node) return;
    initialApplied.current = initialColumn;
    if (!expanded[node.id]) {
      setExpanded((current) => ({
        ...current,
        [node.id]: { fields: [], loading: true },
      }));
      void loadSchema(node);
    }
    setColumn({
      datasetId: node.id,
      namespace: node.data.namespace,
      dataset: node.data.name,
      field: initialColumn.field,
    });
  }, [response, initialColumn, assets]);
  function toggleDataset(node: LineageObject) {
    if (expanded[node.id]) {
      setExpanded((current) => {
        const next = { ...current };
        delete next[node.id];
        return next;
      });
      setFocusDataset(null);
      return;
    }
    const cached = schemaCache.current[node.id];
    setExpanded((current) => ({
      ...current,
      [node.id]: { fields: cached?.fields || [], loading: !cached },
    }));
    setFocusDataset(node.id);
    setSelected(null);
    if (!cached) void loadSchema(node);
  }

  return (
    <section className="panel lineage-panel">
      <div className="panel-heading">
        <div>
          <h2>
            <GitBranch size={17} /> Data flow
          </h2>
          <p>
            Expand a dataset and select a column. Related datasets expand with
            matching fields highlighted.
          </p>
        </div>
        <span className="subtle-tag">OpenLineage model</span>
      </div>
      <div className="flow-toolbar">
        <label>
          Explore{" "}
          <select
            aria-label="Lineage focus asset"
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
          >
            <option value="">Workspace flow / default root</option>
            {assets.map((a) => (
              <option key={a.id} value={a.id}>
                {a.name}
              </option>
            ))}
          </select>
        </label>
        <button
          className="button secondary"
          onClick={() => setRefresh((x) => x + 1)}
          disabled={loading}
          aria-label="Refresh lineage"
        >
          <RefreshCw size={14} />
        </button>
      </div>
      {loading && (
        <div className="flow-placeholder" role="status">
          <GitBranch size={30} />
          <p>Loading lineage objects…</p>
        </div>
      )}
      {error && (
        <div className="flow-placeholder" role="alert">
          <p>{error}</p>
          <button
            className="button secondary"
            onClick={() => setRefresh((x) => x + 1)}
          >
            Retry lineage
          </button>
        </div>
      )}
      {response && (
        <>
          <div className={`flow-provenance ${response.mode}`}>
            <i />
            {response.mode === "demo"
              ? "Demo · Marquez-shaped fixture"
              : "Live · Marquez API"}
            <span>{response.graph.length} objects</span>
          </div>
          {column && (
            <section
              className="inline-column-trace"
              aria-label="Selected column trace"
            >
              <div>
                <strong>
                  {column.dataset}.{column.field}
                </strong>
                {tracePending ? (
                  <p role="status">Loading column mappings…</p>
                ) : traceError ? (
                  <p role="alert">
                    {traceError}{" "}
                    <button onClick={() => setTraceRetry((n) => n + 1)}>
                      Retry trace
                    </button>
                  </p>
                ) : (
                  highlight && (
                    <p>
                      {highlight.upstreamDatasets} upstream{" "}
                      {highlight.upstreamDatasets === 1
                        ? "dataset"
                        : "datasets"}{" "}
                      · {highlight.downstreamDatasets} downstream{" "}
                      {highlight.downstreamDatasets === 1
                        ? "dataset"
                        : "datasets"}{" "}
                      in this view
                      {!highlight.hasRoot ||
                      (!highlight.upstreamDatasets &&
                        !highlight.downstreamDatasets)
                        ? " · No mappings shown in the current dataset view"
                        : ""}
                    </p>
                  )
                )}
              </div>
              <button className="text-button" onClick={() => setColumn(null)}>
                Clear column selection
              </button>
            </section>
          )}
          <FlowCanvas
            graph={response.graph}
            showHealth={response.mode === "demo"}
            assets={assets}
            selected={selected}
            onSelect={setSelected}
            expandedDatasets={expanded}
            onToggleDataset={toggleDataset}
            onRetrySchema={(node) => void loadSchema(node)}
            onSelectColumn={(selection) => {
              setColumn((current) =>
                current?.datasetId === selection.datasetId &&
                current.field === selection.field
                  ? null
                  : selection,
              );
              setSelected(null);
            }}
            columnSelection={column}
            columnTrace={highlight}
            focusDatasetId={focusDataset}
            schemaBusy={Object.values(expanded).some(
              (schema) => schema.loading,
            )}
            onInspect={onInspect}
          />
          <div className="flow-trace-legend">
            <span className="upstream">Upstream dataset</span>
            <span className="selected">Selected column</span>
            <span className="downstream">Downstream dataset</span>
            <span className="both">Both directions</span>
          </div>
          <div className="flow-caption">
            <span>
              <Database size={13} /> Dataset
            </span>
            <ArrowRight size={12} />
            <span>
              <Workflow size={13} /> Job
            </span>
            <ArrowRight size={12} />
            <span>
              <Database size={13} /> Dataset
            </span>
            <small>
              Layout reused from Marquez · drag to pan · scroll to zoom
            </small>
          </div>
          <p className="flow-coverage">{response.coverage}</p>
        </>
      )}
    </section>
  );
}
