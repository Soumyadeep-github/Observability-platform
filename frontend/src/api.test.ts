import { afterEach, expect, it, vi } from "vitest";
import { api, request } from "./api";
afterEach(() => vi.unstubAllGlobals());
it("sends committed publication evidence to Python", async () => {
  const mock = vi
    .fn()
    .mockResolvedValue(
      new Response(JSON.stringify({ state: {} }), { status: 200 }),
    );
  vi.stubGlobal("fetch", mock);
  await api.publish("orders", "2026-11-01T12:00:00Z");
  const [url, options] = mock.mock.calls[0];
  expect(url).toBe("/api/v1/publications");
  expect(options.method).toBe("POST");
  expect(JSON.parse(options.body)).toMatchObject({
    assetId: "orders",
    evidenceKind: "sink_commit",
  });
});
it("surfaces API error details", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(JSON.stringify({ detail: "Conflicting evidence" }), {
          status: 409,
        }),
      ),
  );
  await expect(request("/publications")).rejects.toThrow(
    "Conflicting evidence",
  );
});
it("handles non-JSON proxy errors", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(new Response("Bad gateway", { status: 502 })),
  );
  await expect(request("/state")).rejects.toThrow("Request failed (502)");
});
