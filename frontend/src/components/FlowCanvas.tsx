import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { select } from "d3-selection";
import { zoom, zoomIdentity, zoomTransform, type ZoomBehavior } from "d3-zoom";
import {
  ArrowRight,
  Database,
  Workflow,
  Minus,
  Plus,
  Maximize,
  X,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import type { Asset } from "../domain/model";
import { toMarquezLayout, type LineageObject } from "../domain/lineage";
import {
  edgeKey,
  fieldKey,
  type ColumnSelection,
  type ColumnTrace,
  type ExpandedDataset,
} from "../domain/columnTrace";
import { smoothEdgePath } from "../domain/edgePath";
import { useLayout } from "../vendor/marquez/layout/useLayout";
export default function FlowCanvas({
  graph,
  assets,
  selected,
  onSelect,
  onInspect,
  showHealth = true,
  expandedDatasets,
  onToggleDataset,
  onRetrySchema,
  onSelectColumn,
  columnSelection,
  columnTrace,
  focusDatasetId,
  schemaBusy = false,
}: {
  showHealth?: boolean;
  expandedDatasets?: Record<string, ExpandedDataset>;
  onToggleDataset?: (node: LineageObject) => void;
  onRetrySchema?: (node: LineageObject) => void;
  onSelectColumn?: (selection: ColumnSelection) => void;
  columnSelection?: ColumnSelection | null;
  columnTrace?: ColumnTrace | null;
  focusDatasetId?: string | null;
  schemaBusy?: boolean;
  graph: LineageObject[];
  assets: Asset[];
  selected: string | null;
  onSelect: (id: string | null) => void;
  onInspect: (id: string) => void;
}) {
  const [width, setWidth] = useState(900);
  const direction = width < 620 ? "down" : "right";
  const columnGraph =
    graph.length > 0 && graph.every((n) => n.type === "COLUMN");
  const { nodes, edges } = useMemo(() => {
    const result = toMarquezLayout(graph);
    result.nodes = result.nodes.map((node) => {
      const expansion = expandedDatasets?.[node.id];
      return expansion
        ? {
            ...node,
            width: 270,
            height:
              116 +
              (expansion.loading || expansion.error
                ? 54
                : Math.max(1, Math.min(8, expansion.fields.length)) * 32),
          }
        : node;
    });
    return result;
  }, [graph, expandedDatasets]);
  const { layout, error, isRendering } = useLayout({
    id: "signal-lineage",
    nodes,
    edges,
    direction,
    keepPreviousGraph: true,
  });
  const container = useRef<HTMLDivElement>(null);
  const svg = useRef<SVGSVGElement>(null);
  const group = useRef<SVGGElement>(null);
  const behavior = useRef<ZoomBehavior<SVGSVGElement, unknown> | null>(null);
  const schemaContainers = useRef(new Map<string, HTMLDivElement>());
  const [scale, setScale] = useState(1);
  const height = 560;
  const markerId = useId().replace(/:/g, "");
  const object = graph.find((n) => n.id === selected);
  const assetFor = (node: LineageObject) =>
    node.type === "DATASET"
      ? assets.find(
          (a) =>
            a.namespace === node.data.namespace && a.name === node.data.name,
        )
      : undefined;
  const selectedAsset = object && assetFor(object);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) =>
      setWidth(Math.max(240, entry.contentRect.width)),
    );
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const fit = useCallback(() => {
    if (!layout || !svg.current || !behavior.current) return;
    const k = Math.min(
      (width - 60) / Math.max(layout.width, 1),
      (height - 60) / Math.max(layout.height, 1),
      1.25,
    );
    const transform = zoomIdentity
      .translate(
        (width - layout.width * k) / 2,
        (height - layout.height * k) / 2,
      )
      .scale(k);
    select(svg.current).call(behavior.current.transform, transform);
  }, [layout, width]);
  useEffect(() => {
    if (!svg.current || !group.current || !layout) return;
    const svgSelection = select<SVGSVGElement, unknown>(svg.current);
    const groupSelection = select(group.current);
    const instance = zoom<SVGSVGElement, unknown>()
      .filter((event) =>
        event.type === "wheel"
          ? !(event.target as Element).closest(".expanded-schema")
          : !event.button &&
            !(event.target as Element).closest('button,[role="button"]'),
      )
      .extent([
        [0, 0],
        [width, height],
      ])
      .scaleExtent([0.1, 3])
      .on("zoom", (event) => {
        groupSelection.attr("transform", event.transform.toString());
        setScale(event.transform.k);
      });
    behavior.current = instance;
    svgSelection.call(instance).on("dblclick.zoom", null);
    if (columnSelection) {
      const current = zoomTransform(svg.current);
      groupSelection.attr("transform", current.toString());
      setScale(current.k);
    } else if (focusDatasetId && expandedDatasets?.[focusDatasetId]) {
      const node = layout.nodes.find((n) => n.id === focusDatasetId);
      if (node) {
        const k = Math.min(
          1.15,
          (width - 60) / node.width,
          (height - 80) / node.height,
        );
        svgSelection.call(
          instance.transform,
          zoomIdentity
            .translate(
              width / 2 - (node.bottomLeftCorner.x + node.width / 2) * k,
              height / 2 - (node.bottomLeftCorner.y + node.height / 2) * k,
            )
            .scale(k),
        );
      } else fit();
    } else fit();
    return () => {
      svgSelection.on(".zoom", null);
      behavior.current = null;
    };
  }, [layout, width, fit, focusDatasetId]);
  const fittedColumn = useRef<string | null>(null);
  useEffect(() => {
    if (!columnSelection) {
      fittedColumn.current = null;
      return;
    }
    if (
      !columnTrace ||
      !layout ||
      !svg.current ||
      !behavior.current ||
      schemaBusy ||
      isRendering
    )
      return;
    const key = fieldKey(
      columnSelection.namespace,
      columnSelection.dataset,
      columnSelection.field,
    );
    const relevant = layout.nodes.filter((node) => {
      const relation = columnTrace.nodes.get(node.id);
      return relation && relation !== "unrelated";
    });
    if (!relevant.length) return;
    const geometryKey =
      key +
      JSON.stringify(
        relevant.map((n) => [
          n.id,
          n.bottomLeftCorner.x,
          n.bottomLeftCorner.y,
          n.width,
          n.height,
        ]),
      );
    if (fittedColumn.current === geometryKey) return;
    fittedColumn.current = geometryKey;
    if (relevant.length === 1) return;
    const left = Math.min(...relevant.map((n) => n.bottomLeftCorner.x));
    const top = Math.min(...relevant.map((n) => n.bottomLeftCorner.y));
    const right = Math.max(
      ...relevant.map((n) => n.bottomLeftCorner.x + n.width),
    );
    const bottom = Math.max(
      ...relevant.map((n) => n.bottomLeftCorner.y + n.height),
    );
    const k = Math.min(
      (width - 80) / Math.max(1, right - left),
      (height - 80) / Math.max(1, bottom - top),
      1.15,
    );
    select(svg.current).call(
      behavior.current.transform,
      zoomIdentity
        .translate(
          width / 2 - ((left + right) / 2) * k,
          height / 2 - ((top + bottom) / 2) * k,
        )
        .scale(k),
    );
  }, [columnSelection, columnTrace, layout, width, schemaBusy, isRendering]);
  useEffect(() => {
    for (const container of schemaContainers.current.values()) {
      const target = container.querySelector<HTMLElement>(
        '.expanded-column[data-trace="selected"], .expanded-column[data-trace="upstream"], .expanded-column[data-trace="downstream"], .expanded-column[data-trace="both"]',
      );
      if (
        target &&
        (target.offsetTop < container.scrollTop ||
          target.offsetTop + target.offsetHeight >
            container.scrollTop + container.clientHeight)
      )
        container.scrollTop = Math.max(0, target.offsetTop - 32);
    }
  }, [columnTrace, expandedDatasets, layout]);
  function changeZoom(factor: number) {
    if (svg.current && behavior.current)
      select(svg.current).call(behavior.current.scaleBy, factor);
  }
  if (!graph.length)
    return (
      <div className="flow-placeholder">
        <Database size={30} />
        <h3>No lineage objects found</h3>
        <p>Send OpenLineage RunEvents to Marquez, then refresh.</p>
      </div>
    );
  const relatedIds = new Set(
    selected
      ? [
          selected,
          ...edges
            .filter(
              (e) => e.sourceNodeId === selected || e.targetNodeId === selected,
            )
            .flatMap((e) => [e.sourceNodeId, e.targetNodeId]),
        ]
      : nodes.map((n) => n.id),
  );
  return (
    <>
      <div className="flow-canvas" ref={container}>
        <div className="flow-canvas-label">
          <span>{columnGraph ? "COLUMN LINEAGE" : "OBJECT LINEAGE"}</span>
          <small>
            {direction === "down" ? "Top → bottom" : "Left → right"}
          </small>
        </div>
        <div className="flow-zoom">
          <button
            aria-label="Zoom out lineage"
            onClick={() => changeZoom(1 / 1.25)}
          >
            <Minus size={15} />
          </button>
          <output aria-label="Lineage zoom">{Math.round(scale * 100)}%</output>
          <button aria-label="Zoom in lineage" onClick={() => changeZoom(1.25)}>
            <Plus size={15} />
          </button>
          <button aria-label="Fit lineage to view" onClick={fit}>
            <Maximize size={15} />
          </button>
        </div>
        {isRendering && (
          <div className="flow-layout-status" role="status">
            Arranging graph with Marquez layout…
          </div>
        )}
        {error && (
          <div className="flow-layout-status" role="alert">
            Unable to arrange lineage graph.
          </div>
        )}
        <svg
          ref={svg}
          viewBox={`0 0 ${width} ${height}`}
          role="group"
          aria-label={
            columnGraph
              ? "Interactive column lineage graph"
              : "Interactive dataset and job lineage graph"
          }
        >
          <defs>
            <marker
              id={markerId}
              viewBox="0 0 10 10"
              refX="8"
              refY="5"
              markerWidth="9"
              markerHeight="9"
              markerUnits="userSpaceOnUse"
              orient="auto"
            >
              <path
                d="M 3 1 L 8 5 L 3 9"
                fill="none"
                stroke="#9c91c7"
                strokeWidth="1.5"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </marker>
            {Object.entries({
              upstream: "#379b90",
              downstream: "#678ed2",
              both: "#ab8a54",
              unrelated: "#dce0e9",
            }).map(([direction, color]) => (
              <marker
                key={direction}
                id={`${markerId}-${direction}`}
                viewBox="0 0 10 10"
                refX="8"
                refY="5"
                markerWidth="9"
                markerHeight="9"
                markerUnits="userSpaceOnUse"
                orient="auto"
              >
                <path
                  d="M 3 1 L 8 5 L 3 9"
                  fill="none"
                  stroke={color}
                  strokeWidth="1.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </marker>
            ))}
          </defs>
          <g ref={group}>
            {layout?.edges.map((edge) => {
              const traceDirection = columnSelection
                ? columnTrace?.edges.get(
                    edgeKey(edge.sourceNodeId, edge.targetNodeId),
                  ) || "unrelated"
                : undefined;
              const traceColor =
                traceDirection === "upstream"
                  ? "#379b90"
                  : traceDirection === "downstream"
                    ? "#678ed2"
                    : traceDirection === "both"
                      ? "#ab8a54"
                      : "#dce0e9";
              const highlighted =
                !selected ||
                edge.sourceNodeId === selected ||
                edge.targetNodeId === selected;
              return (
                <path
                  key={edge.id}
                  data-testid="lineage-edge"
                  data-trace={traceDirection}
                  aria-label={`${graph.find((n) => n.id === edge.sourceNodeId)?.data.name} to ${graph.find((n) => n.id === edge.targetNodeId)?.data.name}`}
                  d={smoothEdgePath(edge, direction)}
                  fill="none"
                  stroke={
                    traceDirection
                      ? traceColor
                      : highlighted
                        ? "#9c91c7"
                        : "#dce0e9"
                  }
                  strokeWidth={
                    traceDirection && traceDirection !== "unrelated"
                      ? 2.8
                      : highlighted && selected
                        ? 2.5
                        : 1.5
                  }
                  strokeLinejoin="round"
                  strokeLinecap="round"
                  markerEnd={`url(#${markerId}${traceDirection ? `-${traceDirection}` : ""})`}
                />
              );
            })}
            {layout?.nodes.map((node) => {
              const item = node.data;
              const mapped = assetFor(item);
              const job = item.type === "JOB";
              const active = selected === item.id;
              return (
                <g
                  key={item.id}
                  transform={`translate(${node.bottomLeftCorner.x},${node.bottomLeftCorner.y})`}
                  role="group"
                  aria-label={`${item.data.name} lineage node`}
                  data-dataset-id={item.id}
                  data-trace={
                    columnSelection
                      ? columnTrace?.nodes.get(item.id) ||
                        (item.id === columnSelection.datasetId
                          ? "selected"
                          : "unrelated")
                      : undefined
                  }
                  className={`flow-node ${job ? "job" : "dataset"} ${active ? "selected" : ""} ${expandedDatasets?.[item.id] ? "expanded" : ""}`}
                  opacity={
                    columnSelection
                      ? item.id === columnSelection.datasetId ||
                        (columnTrace?.nodes.get(item.id) &&
                          columnTrace.nodes.get(item.id) !== "unrelated")
                        ? 1
                        : 0.25
                      : relatedIds.has(item.id)
                        ? 1
                        : 0.4
                  }
                >
                  <title>
                    {item.data.namespace}.
                    {item.data.datasetName ? `${item.data.datasetName}.` : ""}
                    {item.data.name}
                  </title>
                  <rect
                    width={node.width}
                    height={node.height}
                    rx={job ? 16 : 7}
                    className="flow-node-bg"
                  />
                  <g
                    role="button"
                    tabIndex={0}
                    aria-label={`${job ? "Job" : item.type === "COLUMN" ? "Column" : "Dataset"} ${item.type === "COLUMN" ? `${item.data.datasetName}.` : ""}${item.data.name}`}
                    aria-expanded={
                      item.type === "DATASET" && onToggleDataset
                        ? !!expandedDatasets?.[item.id]
                        : undefined
                    }
                    aria-pressed={
                      item.type !== "DATASET" || !onToggleDataset
                        ? active
                        : undefined
                    }
                    className="flow-node-header"
                    onClick={() =>
                      item.type === "DATASET" && onToggleDataset
                        ? onToggleDataset(item)
                        : onSelect(active ? null : item.id)
                    }
                    onKeyDown={(e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault();
                        item.type === "DATASET" && onToggleDataset
                          ? onToggleDataset(item)
                          : onSelect(active ? null : item.id);
                      }
                    }}
                  >
                    <rect
                      width={node.width}
                      height={100}
                      rx={7}
                      fill="transparent"
                    />
                    <rect
                      x="0"
                      y="20"
                      width="3"
                      height="60"
                      rx="1"
                      fill={job ? "#a18bce" : "#79aab9"}
                    />
                    <g transform="translate(16,15)">
                      {job ? <Workflow size={15} /> : <Database size={15} />}
                    </g>
                    <text x="39" y="26" className="flow-node-kind">
                      {job
                        ? "TRANSFORMATION JOB"
                        : item.type === "COLUMN"
                          ? `COLUMN · ${item.data.fieldType || "Unknown type"}`
                          : mapped?.source === "Kafka"
                            ? "DATASET · TOPIC"
                            : "DATASET · TABLE"}
                    </text>
                    <text x="16" y="53" className="flow-node-name">
                      {item.data.name.length > 27
                        ? item.data.name.slice(0, 25) + "…"
                        : item.data.name}
                    </text>
                    <text x="16" y="75" className="flow-node-namespace">
                      {(item.data.datasetName || item.data.namespace).slice(
                        0,
                        32,
                      )}
                    </text>
                    {item.type === "DATASET" && onToggleDataset && (
                      <g transform={`translate(${node.width - 30}, 49)`}>
                        {expandedDatasets?.[item.id] ? (
                          <ChevronDown size={15} />
                        ) : (
                          <ChevronRight size={15} />
                        )}
                      </g>
                    )}
                    {mapped && showHealth && (
                      <circle
                        cx={node.width - 15}
                        cy="21"
                        r="3.5"
                        className={`flow-health ${mapped.health}`}
                      />
                    )}
                  </g>
                  {expandedDatasets?.[item.id] &&
                    (() => {
                      const schema = expandedDatasets[item.id];
                      return (
                        <foreignObject
                          x={1}
                          y={100}
                          width={node.width - 2}
                          height={node.height - 101}
                        >
                          <div
                            className="expanded-schema"
                            ref={(element) => {
                              if (element)
                                schemaContainers.current.set(item.id, element);
                              else schemaContainers.current.delete(item.id);
                            }}
                            aria-label={`Columns in ${item.data.name}`}
                          >
                            {schema.loading ? (
                              <p role="status">Loading columns…</p>
                            ) : schema.error ? (
                              <div className="expanded-schema-error">
                                <p role="alert">{schema.error}</p>
                                <button onClick={() => onRetrySchema?.(item)}>
                                  Retry schema
                                </button>
                              </div>
                            ) : schema.fields.length ? (
                              schema.fields.map((field) => {
                                const isSelected =
                                  columnSelection?.datasetId === item.id &&
                                  columnSelection.field === field.name;
                                const relation = columnTrace?.fields.get(
                                  fieldKey(
                                    item.data.namespace,
                                    item.data.name,
                                    field.name,
                                  ),
                                );
                                return (
                                  <button
                                    key={field.name}
                                    className={`expanded-column ${isSelected ? "selected" : ""}`}
                                    data-trace={relation}
                                    aria-label={`Trace ${item.data.name}.${field.name}`}
                                    aria-pressed={isSelected}
                                    onClick={() =>
                                      onSelectColumn?.({
                                        datasetId: item.id,
                                        namespace: item.data.namespace,
                                        dataset: item.data.name,
                                        field: field.name,
                                      })
                                    }
                                  >
                                    <span>{field.name}</span>
                                    <code>{field.type || "Unknown"}</code>
                                  </button>
                                );
                              })
                            ) : (
                              <p>No columns reported.</p>
                            )}
                          </div>
                        </foreignObject>
                      );
                    })()}
                </g>
              );
            })}
          </g>
        </svg>
      </div>
      {object && (!onToggleDataset || object.type === "JOB") && (
        <section
          className="flow-selection"
          aria-label="Selected lineage object"
        >
          <div>
            <span className="eyebrow">
              {object.type === "JOB"
                ? "JOB"
                : object.type === "COLUMN"
                  ? "COLUMN"
                  : "DATASET"}
            </span>
            <h3>{object.data.name}</h3>
            <p>{object.data.description || object.data.namespace}</p>
            <small>
              {object.inEdges.length} input edges · {object.outEdges.length}{" "}
              output edges
              {object.type === "JOB" && object.data.latestRun?.state
                ? ` · Latest run: ${object.data.latestRun.state}`
                : ""}
            </small>
          </div>
          {selectedAsset && (
            <button
              className="button secondary"
              onClick={() => onInspect(selectedAsset.id)}
            >
              Inspect asset <ArrowRight size={14} />
            </button>
          )}
          <button
            className="icon-button"
            aria-label="Clear lineage selection"
            onClick={() => onSelect(null)}
          >
            <X size={16} />
          </button>
        </section>
      )}
    </>
  );
}
