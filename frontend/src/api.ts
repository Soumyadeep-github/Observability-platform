import type { DemoState } from "./domain/model";
export async function request<T>(
  path: string,
  options?: RequestInit,
): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* Non-JSON proxy error */
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}
export const api = {
  state: () => request<DemoState>("/state"),
  reset: () => request<DemoState>("/demo/reset", { method: "POST" }),
  incident: (id: string, state: "acknowledged" | "resolved") =>
    request<DemoState>(`/incidents/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: JSON.stringify({ state }),
    }),
  publish: (assetId: string, publishedAt: string) =>
    request<{ state: DemoState }>("/publications", {
      method: "POST",
      body: JSON.stringify({
        eventId: crypto.randomUUID(),
        assetId,
        publishedAt,
        evidenceKind: "sink_commit",
      }),
    }),
};
