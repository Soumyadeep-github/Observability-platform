import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import LineageFlow from "./LineageFlow";
import { toMarquezLayout, type LineageObject } from "../domain/lineage";
import fixture from "../../../backend/app/demo_lineage.json";
import columnFixture from "../../../backend/app/demo_columns.json";
const graph = fixture.graph as LineageObject[];
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), { status });
function apiResponse(url: string) {
  if (url.includes("/dataset-details")) {
    const params = new URL(url, "http://localhost").searchParams;
    const node = graph.find(
      (n) =>
        n.data.namespace === params.get("namespace") &&
        n.data.name === params.get("name"),
    )!;
    return json({ ...node.data, mode: "demo", provider: "Fixture" });
  }
  if (url.includes("/column-lineage"))
    return json({
      ...columnFixture,
      mode: "demo",
      provider: "Fixture",
      coverage: "Explicit mappings",
    });
  return json({ graph, mode: "demo", provider: "Fixture", coverage: "Sample" });
}
beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (url: string) => apiResponse(url)),
  );
});
afterEach(() => vi.unstubAllGlobals());
const node = (name: string) =>
  screen.getByRole("group", { name: `${name} lineage node` });

it("keeps native dataset/job objects and deduplicates edges", () => {
  const layout = toMarquezLayout(graph);
  expect(layout.nodes).toHaveLength(11);
  expect(layout.edges).toHaveLength(7);
  for (const edge of layout.edges)
    expect(layout.nodes.find((n) => n.id === edge.sourceNodeId)?.kind).not.toBe(
      layout.nodes.find((n) => n.id === edge.targetNodeId)?.kind,
    );
});
it("handles cycles and omits boundary edges outside a bounded response", () => {
  const a: LineageObject = {
    id: "a",
    type: "DATASET",
    data: { namespace: "n", name: "a" },
    inEdges: [],
    outEdges: [
      { origin: "a", destination: "b" },
      { origin: "a", destination: "outside" },
    ],
  };
  const b: LineageObject = {
    id: "b",
    type: "JOB",
    data: { namespace: "n", name: "b" },
    inEdges: [],
    outEdges: [{ origin: "b", destination: "a" }],
  };
  expect(toMarquezLayout([a, b]).edges).toHaveLength(2);
});
it("preserves job selection, routed arrows and graph zoom", async () => {
  const user = userEvent.setup();
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", { name: "Job build_daily_revenue" }),
  );
  expect(
    screen.getByRole("region", { name: "Selected lineage object" }),
  ).toHaveTextContent("build_daily_revenue");
  expect(screen.getAllByTestId("lineage-edge")).toHaveLength(7);
  for (const edge of screen.getAllByTestId("lineage-edge")) {
    const coordinates = edge
      .getAttribute("d")!
      .match(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi)!
      .map(Number);
    expect(edge.tagName.toLowerCase()).toBe("path");
    expect(edge.getAttribute("d")).toContain("C");
    expect(coordinates.at(-2)).toBeGreaterThan(coordinates[0]);
  }
  const old = screen.getByLabelText("Lineage zoom").textContent;
  await user.click(screen.getByRole("button", { name: "Zoom in lineage" }));
  expect(screen.getByLabelText("Lineage zoom").textContent).not.toBe(old);
});
it("expands all schema fields inside the dataset, then highlights directional dataset impact", async () => {
  const user = userEvent.setup();
  const inspect = vi.fn();
  render(<LineageFlow assets={[]} onInspect={inspect} />);
  await user.click(
    await screen.findByRole("button", { name: "Dataset daily_revenue" }),
  );
  for (const field of ["id", "created_at", "amount", "region"])
    expect(
      await screen.findByRole("button", {
        name: `Trace daily_revenue.${field}`,
      }),
    ).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Dataset daily_revenue" }),
  ).toHaveAttribute("aria-expanded", "true");
  const zoomBefore = screen.getByLabelText("Lineage zoom").textContent;
  await user.click(
    screen.getByRole("button", { name: "Trace daily_revenue.amount" }),
  );
  await waitFor(() =>
    expect(node("fct_orders")).toHaveAttribute("data-trace", "upstream"),
  );
  expect(node("daily_revenue")).toHaveAttribute("data-trace", "selected");
  expect(node("executive_metrics")).toHaveAttribute("data-trace", "downstream");
  expect(node("dim_customers")).toHaveAttribute("data-trace", "unrelated");
  expect(node("payments")).toHaveAttribute("data-trace", "unrelated");
  await screen.findByRole("button", { name: "Trace fct_orders.amount" });
  await screen.findByRole("button", { name: "Trace executive_metrics.amount" });
  await waitFor(() =>
    expect(screen.getByLabelText("Lineage zoom").textContent).not.toBe(
      zoomBefore,
    ),
  );
  expect(inspect).not.toHaveBeenCalled();
  await user.click(
    screen.getByRole("button", { name: "Clear column selection" }),
  );
  expect(node("fct_orders")).not.toHaveAttribute("data-trace");
  expect(
    screen.getByRole("button", { name: "Trace daily_revenue.amount" }),
  ).toBeInTheDocument();
});
it("can expand several datasets and highlights their matching field rows", async () => {
  const user = userEvent.setup();
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", { name: "Dataset daily_revenue" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Trace daily_revenue.amount" }),
  );
  await waitFor(() =>
    expect(node("fct_orders")).toHaveAttribute("data-trace", "upstream"),
  );
  expect(
    await screen.findByRole("button", { name: "Trace fct_orders.amount" }),
  ).toHaveAttribute("data-trace", "upstream");
  expect(
    await screen.findByRole("button", {
      name: "Trace executive_metrics.amount",
    }),
  ).toHaveAttribute("data-trace", "downstream");
  await user.click(screen.getByRole("button", { name: "Dataset fct_orders" }));
  expect(
    screen.queryByRole("button", { name: "Trace fct_orders.amount" }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Dataset fct_orders" }));
  expect(
    await screen.findByRole("button", { name: "Trace fct_orders.amount" }),
  ).toHaveAttribute("data-trace", "upstream");
  expect(
    screen.getByRole("button", { name: "Trace daily_revenue.amount" }),
  ).toHaveAttribute("aria-pressed", "true");
});
it("collapses and reopens a dataset using its cached schema", async () => {
  const user = userEvent.setup();
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", { name: "Dataset daily_revenue" }),
  );
  await screen.findByRole("button", { name: "Trace daily_revenue.amount" });
  await user.click(
    screen.getByRole("button", { name: "Dataset daily_revenue" }),
  );
  expect(
    screen.queryByRole("button", { name: "Trace daily_revenue.amount" }),
  ).not.toBeInTheDocument();
  await user.click(
    await screen.findByRole("button", { name: "Dataset daily_revenue" }),
  );
  await screen.findByRole("button", { name: "Trace daily_revenue.amount" });
  expect(
    vi
      .mocked(fetch)
      .mock.calls.filter(([url]) => String(url).includes("/dataset-details")),
  ).toHaveLength(1);
});
it("supports keyboard column selection without opening another view", async () => {
  const user = userEvent.setup();
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", { name: "Dataset daily_revenue" }),
  );
  const field = await screen.findByRole("button", {
    name: "Trace daily_revenue.region",
  });
  field.focus();
  await user.keyboard("{Enter}");
  expect(
    await screen.findByRole("region", { name: "Selected column trace" }),
  ).toHaveTextContent("daily_revenue.region");
  await waitFor(() =>
    expect(node("executive_metrics")).toHaveAttribute(
      "data-trace",
      "downstream",
    ),
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
it("shows unknown mappings and does not infer same-name column dependencies", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (url: string) =>
      url.includes("/column-lineage")
        ? json({
            graph: [],
            mode: "live",
            provider: "Marquez",
            coverage: "No evidence",
          })
        : apiResponse(url),
    ),
  );
  const user = userEvent.setup();
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", { name: "Dataset inventory_snapshot" }),
  );
  await user.click(
    await screen.findByRole("button", {
      name: "Trace inventory_snapshot.amount",
    }),
  );
  expect(
    await screen.findByText(/No mappings shown in the current dataset view/),
  ).toBeInTheDocument();
  expect(node("fct_orders")).toHaveAttribute("data-trace", "unrelated");
});
it("shows inline schema failures and retries without opening a dialog", async () => {
  let schemaCalls = 0;
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(async (url: string) =>
        url.includes("/dataset-details") && schemaCalls++ === 0
          ? json({ detail: "Marquez unavailable" }, 503)
          : apiResponse(url),
      ),
  );
  const user = userEvent.setup();
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", { name: "Dataset daily_revenue" }),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Marquez unavailable",
  );
  await user.click(screen.getByRole("button", { name: "Retry schema" }));
  expect(
    await screen.findByRole("button", { name: "Trace daily_revenue.amount" }),
  ).toBeInTheDocument();
});
it("ignores stale column responses when selection changes quickly", async () => {
  let finishAmount: ((response: Response) => void) | undefined;
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async (url: string) =>
      url.includes("/column-lineage") &&
      new URL(url, "http://localhost").searchParams.get("field") === "amount"
        ? new Promise<Response>((resolve) => {
            finishAmount = resolve;
          })
        : apiResponse(url),
    ),
  );
  const user = userEvent.setup();
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  await user.click(
    await screen.findByRole("button", { name: "Dataset daily_revenue" }),
  );
  await user.click(
    await screen.findByRole("button", { name: "Trace daily_revenue.amount" }),
  );
  await user.click(
    screen.getByRole("button", { name: "Trace daily_revenue.region" }),
  );
  const summary = screen.getByRole("region", { name: "Selected column trace" });
  await waitFor(() =>
    expect(summary).toHaveTextContent(
      "1 upstream dataset · 1 downstream dataset",
    ),
  );
  await act(async () => {
    finishAmount?.(
      json({
        ...columnFixture,
        graph: columnFixture.graph.filter((n) => n.data.field === "amount"),
      }),
    );
  });
  expect(summary).toHaveTextContent("daily_revenue.region");
  expect(summary).toHaveTextContent(
    "1 upstream dataset · 1 downstream dataset",
  );
  expect(
    within(node("daily_revenue")).getByRole("button", {
      name: "Trace daily_revenue.region",
    }),
  ).toHaveAttribute("aria-pressed", "true");
});
it("shows an empty lineage response honestly", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      json({
        graph: [],
        mode: "live",
        provider: "Marquez",
        coverage: "Run-derived",
      }),
    ),
  );
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  expect(
    await screen.findByText("No lineage objects found"),
  ).toBeInTheDocument();
});
it("keeps upstream failures visible without a fixture fallback", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(json({ detail: "Marquez unavailable" }, 503)),
  );
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Marquez unavailable",
  );
  expect(
    screen.queryByText("Demo · Marquez-shaped fixture"),
  ).not.toBeInTheDocument();
});

it("keeps curved connectors directional on a narrow graph", async () => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      callback: (entries: { contentRect: { width: number } }[]) => void;
      constructor(
        callback: (entries: { contentRect: { width: number } }[]) => void,
      ) {
        this.callback = callback;
      }
      observe() {
        this.callback([{ contentRect: { width: 400 } }]);
      }
      unobserve() {}
      disconnect() {}
    },
  );
  render(<LineageFlow assets={[]} onInspect={vi.fn()} />);
  await screen.findByRole("button", { name: "Dataset daily_revenue" });
  await waitFor(() =>
    expect(screen.getAllByTestId("lineage-edge")).toHaveLength(7),
  );
  for (const edge of screen.getAllByTestId("lineage-edge")) {
    const coords = edge
      .getAttribute("d")!
      .match(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi)!
      .map(Number);
    expect(coords.at(-1)).toBeGreaterThan(coords[1]);
  }
  expect(screen.getByText("Top → bottom")).toBeInTheDocument();
});
