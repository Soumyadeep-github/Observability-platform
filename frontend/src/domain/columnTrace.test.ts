import { expect, it } from "vitest";
import { fieldKey, traceColumn, type ColumnSelection } from "./columnTrace";
import type { ColumnResponse, LineageObject } from "./lineage";
import fixture from "../../../backend/app/demo_lineage.json";
import columns from "../../../backend/app/demo_columns.json";
const graph = fixture.graph as LineageObject[];
const response: ColumnResponse = {
  ...columns,
  mode: "demo",
  provider: "Fixture",
  coverage: "Explicit mappings",
};
const selection = (
  dataset: string,
  namespace: string,
  field: string,
): ColumnSelection => ({
  datasetId: `dataset:${namespace}:${dataset}`,
  dataset,
  namespace,
  field,
});
it("finds transitive upstream and downstream datasets for a selected field", () => {
  const result = traceColumn(
    selection("daily_revenue", "analytics.finance", "amount"),
    response,
    graph,
  );
  expect(result.nodes.get("dataset:analytics.commerce:fct_orders")).toBe(
    "upstream",
  );
  expect(
    result.nodes.get("dataset:analytics.reporting:executive_metrics"),
  ).toBe("downstream");
  expect(result.nodes.get("dataset:analytics.core:dim_customers")).toBe(
    "unrelated",
  );
  expect(result.nodes.get("job:signal.demo:build_daily_revenue")).toBe(
    "upstream",
  );
  expect(result.nodes.get("job:signal.demo:build_executive_metrics")).toBe(
    "downstream",
  );
  expect(result.upstreamDatasets).toBe(1);
  expect(result.downstreamDatasets).toBe(1);
});
it("does not confuse a join co-input with downstream impact", () => {
  const result = traceColumn(
    selection("daily_revenue", "analytics.finance", "region"),
    response,
    graph,
  );
  expect(result.nodes.get("dataset:analytics.core:dim_customers")).toBe(
    "unrelated",
  );
  const joined = traceColumn(
    selection("executive_metrics", "analytics.reporting", "region"),
    response,
    graph,
  );
  expect(joined.nodes.get("dataset:analytics.core:dim_customers")).toBe(
    "upstream",
  );
  expect(joined.nodes.get("dataset:analytics.commerce:fct_orders")).toBe(
    "upstream",
  );
  expect(joined.upstreamDatasets).toBe(3);
});
it("uses field identity and evidence rather than dataset-level edges or matching names", () => {
  const result = traceColumn(
    selection("daily_revenue", "analytics.finance", "id"),
    response,
    graph,
  );
  expect(
    result.fields.get(fieldKey("analytics.finance", "daily_revenue", "amount")),
  ).toBe("unrelated");
  expect(result.nodes.get("dataset:operational.public:payments")).toBe(
    "unrelated",
  );
  const missing = traceColumn(
    selection("daily_revenue", "analytics.finance", "not_reported"),
    response,
    graph,
  );
  expect(missing.hasRoot).toBe(false);
  expect(missing.upstreamDatasets).toBe(0);
  expect(missing.downstreamDatasets).toBe(0);
  expect(missing.nodes.get("job:signal.demo:build_daily_revenue")).toBe(
    "unrelated",
  );
});
it("terminates on cycles and marks a dataset participating in both directions", () => {
  const data = (name: string): ColumnResponse["graph"][number] => ({
    id: `field-${name}`,
    type: "DATASET_FIELD",
    data: { namespace: "n", dataset: name, field: "x" },
    inEdges: [],
    outEdges: [],
  });
  const a = data("a"),
    b = data("b");
  a.outEdges = [{ origin: a.id, destination: b.id }];
  b.outEdges = [{ origin: b.id, destination: a.id }];
  const objects: LineageObject[] = [a, b].map((n) => ({
    id: `dataset:n:${n.data.dataset}`,
    type: "DATASET",
    data: { namespace: "n", name: n.data.dataset },
    inEdges: [],
    outEdges: n.outEdges.map((e) => ({
      origin: `dataset:n:${e.origin.slice(6)}`,
      destination: `dataset:n:${e.destination.slice(6)}`,
    })),
  }));
  const result = traceColumn(
    selection("a", "n", "x"),
    { ...response, graph: [a, b] },
    objects,
  );
  expect(result.nodes.get("dataset:n:b")).toBe("both");
  expect(result.upstreamDatasets).toBe(1);
  expect(result.downstreamDatasets).toBe(1);
});
