import type { Edge, Node } from "../vendor/marquez/types";
export interface LineageObject {
  id: string;
  type: "DATASET" | "JOB" | "COLUMN";
  data: {
    namespace: string;
    name: string;
    description?: string;
    sourceName?: string;
    datasetName?: string;
    fieldType?: string | null;
    fields?: { name: string; type?: string }[];
    latestRun?: { state?: string; id?: string };
  };
  inEdges: { origin: string; destination: string }[];
  outEdges: { origin: string; destination: string }[];
}
export interface LineageResponse {
  graph: LineageObject[];
  mode: "demo" | "live";
  provider: string;
  coverage: string;
  focusId?: string;
}
// Keep Marquez's native IDs and dataset/job distinction; no inferred relationships.
export function toMarquezLayout(graph: LineageObject[]): {
  nodes: Node<LineageObject["type"], LineageObject>[];
  edges: Edge[];
} {
  const ids = new Set(graph.map((n) => n.id));
  const edges = new Map<string, Edge>();
  for (const node of graph) {
    for (const edge of [...node.inEdges, ...node.outEdges]) {
      if (!ids.has(edge.origin) || !ids.has(edge.destination)) continue;
      const id = JSON.stringify([edge.origin, edge.destination]);
      edges.set(id, {
        id,
        sourceNodeId: edge.origin,
        targetNodeId: edge.destination,
      });
    }
  }
  return {
    nodes: graph.map((node) => ({
      id: node.id,
      kind: node.type,
      width: node.type === "JOB" ? 210 : 238,
      height: 100,
      data: node,
    })),
    edges: [...edges.values()],
  };
}

export interface DatasetDetails {
  namespace: string;
  name: string;
  description?: string | null;
  fields: {
    name: string;
    type?: string | null;
    nullable?: boolean | null;
    description?: string | null;
  }[];
  mode: "demo" | "live";
  provider: string;
}
export interface ColumnResponse {
  mode: "demo" | "live";
  provider: string;
  coverage: string;
  graph: {
    id: string;
    type: string;
    data: {
      namespace: string;
      dataset: string;
      field: string;
      fieldType?: string | null;
      transformationType?: string | null;
      transformationDescription?: string | null;
    };
    inEdges: { origin: string; destination: string }[];
    outEdges: { origin: string; destination: string }[];
  }[];
}
export function columnObjects(response: ColumnResponse): LineageObject[] {
  return response.graph.map((node) => ({
    id: node.id,
    type: "COLUMN",
    inEdges: node.inEdges,
    outEdges: node.outEdges,
    data: {
      namespace: node.data.namespace,
      name: node.data.field,
      datasetName: node.data.dataset,
      fieldType: node.data.fieldType,
      description:
        [node.data.transformationType, node.data.transformationDescription]
          .filter(Boolean)
          .join(" · ") || "No transformation details reported",
    },
  }));
}
