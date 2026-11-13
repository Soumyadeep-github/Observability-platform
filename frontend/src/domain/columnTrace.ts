import type { ColumnResponse, DatasetDetails, LineageObject } from "./lineage";
export interface ExpandedDataset {
  fields: DatasetDetails["fields"];
  loading: boolean;
  error?: string;
}
export interface ColumnSelection {
  datasetId: string;
  namespace: string;
  dataset: string;
  field: string;
}
export type TraceDirection =
  | "selected"
  | "upstream"
  | "downstream"
  | "both"
  | "unrelated";
export interface ColumnTrace {
  nodes: Map<string, TraceDirection>;
  edges: Map<string, TraceDirection>;
  fields: Map<string, TraceDirection>;
  upstreamDatasets: number;
  downstreamDatasets: number;
  hasRoot: boolean;
}
export const fieldKey = (namespace: string, dataset: string, field: string) =>
  JSON.stringify([namespace, dataset, field]);
export const edgeKey = (origin: string, destination: string) =>
  JSON.stringify([origin, destination]);

/** Traverse input and output edges separately. Co-inputs are not downstream impact. */
export function traceColumn(
  selection: ColumnSelection,
  response: ColumnResponse,
  graph: LineageObject[],
): ColumnTrace {
  const root = response.graph.find(
    (n) =>
      n.data.namespace === selection.namespace &&
      n.data.dataset === selection.dataset &&
      n.data.field === selection.field,
  );
  const nativeIds = new Set(response.graph.map((n) => n.id));
  const columnEdges = new Map<
    string,
    { origin: string; destination: string }
  >();
  for (const node of response.graph)
    for (const edge of [...node.inEdges, ...node.outEdges]) {
      if (nativeIds.has(edge.origin) && nativeIds.has(edge.destination))
        columnEdges.set(edgeKey(edge.origin, edge.destination), edge);
    }
  const walk = (
    start: string,
    upstream: boolean,
    edges: { origin: string; destination: string }[],
  ) => {
    const found = new Set<string>([start]);
    const queue = [start];
    while (queue.length) {
      const current = queue.shift()!;
      for (const edge of edges) {
        const next = upstream
          ? edge.destination === current
            ? edge.origin
            : null
          : edge.origin === current
            ? edge.destination
            : null;
        if (next && !found.has(next)) {
          found.add(next);
          queue.push(next);
        }
      }
    }
    return found;
  };
  const upstream = root
    ? walk(root.id, true, [...columnEdges.values()])
    : new Set<string>();
  const downstream = root
    ? walk(root.id, false, [...columnEdges.values()])
    : new Set<string>();
  const classify = (up: boolean, down: boolean): TraceDirection =>
    up && down ? "both" : up ? "upstream" : down ? "downstream" : "unrelated";
  const fields = new Map<string, TraceDirection>();
  const upstreamDatasets = new Set<string>();
  const downstreamDatasets = new Set<string>();
  for (const node of response.graph) {
    const dataset = graph.find(
      (n) =>
        n.type === "DATASET" &&
        n.data.namespace === node.data.namespace &&
        n.data.name === node.data.dataset,
    );
    const isRoot = node.id === root?.id;
    const up = !isRoot && upstream.has(node.id),
      down = !isRoot && downstream.has(node.id);
    fields.set(
      fieldKey(node.data.namespace, node.data.dataset, node.data.field),
      isRoot ? "selected" : classify(up, down),
    );
    if (dataset && dataset.id !== selection.datasetId) {
      if (up) upstreamDatasets.add(dataset.id);
      if (down) downstreamDatasets.add(dataset.id);
    }
  }
  // Keep jobs only as graph context along paths between the evidenced datasets.
  const tableEdges = [
    ...new Map(
      graph
        .flatMap((n) => n.outEdges)
        .map((e) => [edgeKey(e.origin, e.destination), e]),
    ).values(),
  ];
  const pathNodes = (allowedDatasets: Set<string>, up: boolean) => {
    if (!allowedDatasets.size) return new Set([selection.datasetId]);
    const allowed = new Set([
      selection.datasetId,
      ...allowedDatasets,
      ...graph.filter((n) => n.type === "JOB").map((n) => n.id),
    ]);
    return walk(
      selection.datasetId,
      up,
      tableEdges.filter(
        (e) => allowed.has(e.origin) && allowed.has(e.destination),
      ),
    );
  };
  const upPath = pathNodes(upstreamDatasets, true),
    downPath = pathNodes(downstreamDatasets, false);
  const nodes = new Map<string, TraceDirection>();
  for (const node of graph)
    nodes.set(
      node.id,
      node.id === selection.datasetId
        ? "selected"
        : node.type === "DATASET"
          ? classify(
              upstreamDatasets.has(node.id),
              downstreamDatasets.has(node.id),
            )
          : classify(upPath.has(node.id), downPath.has(node.id)),
    );
  const edges = new Map<string, TraceDirection>();
  for (const edge of tableEdges)
    edges.set(
      edgeKey(edge.origin, edge.destination),
      classify(
        upPath.has(edge.origin) && upPath.has(edge.destination),
        downPath.has(edge.origin) && downPath.has(edge.destination),
      ),
    );
  return {
    nodes,
    edges,
    fields,
    upstreamDatasets: upstreamDatasets.size,
    downstreamDatasets: downstreamDatasets.size,
    hasRoot: !!root,
  };
}
