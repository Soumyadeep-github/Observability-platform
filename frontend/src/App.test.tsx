import { render, screen, within, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { api } from "./api";
import fixture from "../../backend/app/demo_seed.json";
import type { DemoState, Health } from "./domain/model";
import { filterAssets, minutesAgo, qualityRate } from "./domain/model";
vi.mock("./api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./api")>()),
  api: { state: vi.fn(), incident: vi.fn(), publish: vi.fn(), reset: vi.fn() },
}));
afterEach(() => vi.unstubAllGlobals());
const healthById: Record<string, Health> = {
  orders: "critical",
  revenue: "critical",
  customers: "healthy",
  events: "healthy",
  payments: "healthy",
  sessions: "warning",
  inventory: "unknown",
  dashboard: "healthy",
};
function seed(): DemoState {
  return {
    ...structuredClone(fixture),
    mode: "demo",
    assets: fixture.assets.map((a) => ({ ...a, health: healthById[a.id] })),
  } as DemoState;
}
beforeEach(() => {
  vi.mocked(api.state).mockReset().mockResolvedValue(seed());
  vi.mocked(api.incident).mockReset();
  vi.mocked(api.publish).mockReset();
  vi.mocked(api.reset).mockReset();
});
async function ready() {
  render(<App />);
  await screen.findByRole("heading", { name: "Your data, in focus." });
}
describe("workspace workflows", () => {
  it("opens schema details and restores focus after keyboard dismissal", async () => {
    const user = userEvent.setup();
    await ready();
    const button = screen.getByRole("button", { name: "dim_customers" });
    await user.click(button);
    const dialog = screen.getByRole("dialog");
    expect(
      within(dialog).getByRole("heading", { name: "dim_customers" }),
    ).toBeInTheDocument();
    await user.click(within(dialog).getByRole("tab", { name: "Schema" }));
    expect(within(dialog).getByText("TIMESTAMP")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });
  it("combines search and filters and clears empty results", async () => {
    const user = userEvent.setup();
    await ready();
    await user.type(
      screen.getByRole("textbox", { name: "Search assets" }),
      "finance",
    );
    await user.selectOptions(
      screen.getByLabelText("Health filter"),
      "critical",
    );
    expect(
      screen.getByRole("button", { name: "daily_revenue" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "executive_metrics" }),
    ).not.toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Source filter"), "Kafka");
    expect(
      screen.getByText("No assets match your filters"),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(screen.getByText("Showing 8 of 8 assets")).toBeInTheDocument();
  });
  it("acknowledges incidents through Python API", async () => {
    const user = userEvent.setup();
    await ready();
    await user.click(
      within(screen.getByRole("navigation")).getByRole("button", {
        name: /Incidents/,
      }),
    );
    const updated = seed();
    updated.incidents[0].state = "acknowledged";
    vi.mocked(api.incident).mockResolvedValue(updated);
    await user.click(screen.getAllByRole("button", { name: "Acknowledge" })[0]);
    expect(api.incident).toHaveBeenCalledWith("INC-1042", "acknowledged");
    await waitFor(() =>
      expect(
        screen.getAllByRole("button", { name: "Resolve incident" }),
      ).toHaveLength(2),
    );
  });
  it("sends sample publication with fixed demo clock", async () => {
    const user = userEvent.setup();
    await ready();
    await user.click(screen.getByRole("button", { name: "payments" }));
    await user.click(screen.getByRole("tab", { name: "Overview" }));
    vi.mocked(api.publish).mockResolvedValue({ state: seed() });
    await user.click(
      screen.getByRole("button", { name: "Simulate publication" }),
    );
    expect(api.publish).toHaveBeenCalledWith("payments", fixture.now);
    await waitFor(() =>
      expect(
        screen.getAllByText(
          "Sample sink commit recorded. Quality evidence is unchanged.",
        ),
      ).toHaveLength(2),
    );
  });
  it("shows mutation failure without discarding current data", async () => {
    const user = userEvent.setup();
    await ready();
    await user.click(screen.getByRole("button", { name: "payments" }));
    await user.click(screen.getByRole("tab", { name: "Overview" }));
    vi.mocked(api.publish).mockRejectedValue(new Error("API unavailable"));
    await user.click(
      screen.getByRole("button", { name: "Simulate publication" }),
    );
    expect(
      await within(screen.getByRole("dialog")).findByRole("alert"),
    ).toHaveTextContent("API unavailable");
    expect(
      screen.getByRole("heading", { name: "payments" }),
    ).toBeInTheDocument();
  });
  it("handles unreachable Python API", async () => {
    vi.mocked(api.state).mockRejectedValue(new Error("Connection refused"));
    render(<App />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Could not reach the Python API",
    );
  });
  it("shows connection coverage limitations", async () => {
    const user = userEvent.setup();
    await ready();
    await user.click(
      within(screen.getByRole("navigation")).getByRole("button", {
        name: "Connections",
      }),
    );
    expect(screen.getAllByText("Not configured")).toHaveLength(4);
    expect(screen.getAllByText("Facet fixtures only")).toHaveLength(4);
  });
});
describe("presentation helpers", () => {
  it("excludes error and skipped checks from assertion pass rate", () => {
    expect(qualityRate(seed().assets)).toBe(96);
    expect(qualityRate([])).toBeNull();
  });
  it("formats missing and future evidence honestly", () => {
    expect(minutesAgo(null, fixture.now)).toBe("No evidence");
    expect(minutesAgo("invalid", fixture.now)).toBe("Unknown");
    expect(minutesAgo("2027-01-01T00:00:00Z", fixture.now)).toBe("Unknown");
    expect(minutesAgo("2026-11-01T10:18:00Z", fixture.now)).toBe("1h 42m ago");
  });
  it("matches namespace and owner without case sensitivity", () => {
    expect(
      filterAssets(seed().assets, " FINANCE ", "all", "BigQuery"),
    ).toHaveLength(2);
    expect(filterAssets(seed().assets, "", "unknown", "all")[0].id).toBe(
      "inventory",
    );
  });
});

it("removes Columns navigation and routes schema tracing directly into Lineage", async () => {
  const user = userEvent.setup();
  const graph = await import("../../backend/app/demo_lineage.json");
  const columns = await import("../../backend/app/demo_columns.json");
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
    vi.fn().mockImplementation(async (url: string) => {
      if (url.includes("/dataset-details")) {
        const params = new URL(url, "http://localhost").searchParams;
        const match = graph.graph.find(
          (n) =>
            n.data.name === params.get("name") &&
            n.data.namespace === params.get("namespace"),
        )!;
        return new Response(
          JSON.stringify({ ...match.data, mode: "demo", provider: "Fixture" }),
        );
      }
      return new Response(
        JSON.stringify({
          ...(url.includes("/column-lineage") ? columns : graph),
          mode: "demo",
          provider: "Fixture",
          coverage: "Sample",
        }),
      );
    }),
  );
  await ready();
  expect(
    within(screen.getByRole("navigation")).queryByRole("button", {
      name: "Columns",
    }),
  ).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "daily_revenue" }));
  await user.click(screen.getByRole("button", { name: "Trace column amount" }));
  expect(
    await screen.findByRole("heading", { name: "Lineage" }),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(
      screen.getByRole("region", { name: "Selected column trace" }),
    ).toHaveTextContent("daily_revenue.amount"),
  );
  expect(
    await screen.findByRole("button", { name: "Trace fct_orders.amount" }),
  ).toHaveAttribute("data-trace", "upstream");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
