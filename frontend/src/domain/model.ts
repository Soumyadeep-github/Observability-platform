export type Health = "healthy" | "warning" | "critical" | "unknown";
export type CheckStatus = "PASS" | "FAIL" | "ERROR" | "SKIPPED";
export interface QualityCheck {
  id: string;
  name: string;
  column: string;
  status: CheckStatus;
  value: string;
}
export interface Asset {
  id: string;
  name: string;
  namespace: string;
  source: "BigQuery" | "PostgreSQL" | "Kafka" | "Spanner";
  owner: string;
  rows: string;
  description: string;
  publishedAt: string | null;
  freshnessMinutes: number;
  monitorAvailable: boolean;
  health: Health;
  columns: { name: string; type: string; nullable: boolean }[];
  checks: QualityCheck[];
  upstream: string[];
  lineageCoverage: "declared" | "partial";
}
export interface Incident {
  id: string;
  assetId: string;
  column?: string;
  title: string;
  severity: "critical" | "warning";
  dimension: string;
  openedAt: string;
  state: "open" | "acknowledged" | "resolved";
}
export interface DemoState {
  version: 1;
  now: string;
  mode: "demo";
  assets: Asset[];
  incidents: Incident[];
}
export function qualityRate(assets: Asset[]): number | null {
  const evaluated = assets
    .flatMap((a) => a.checks)
    .filter((c) => c.status === "PASS" || c.status === "FAIL");
  return evaluated.length
    ? Math.round(
        (evaluated.filter((c) => c.status === "PASS").length /
          evaluated.length) *
          100,
      )
    : null;
}
export function minutesAgo(time: string | null, now: string): string {
  if (!time) return "No evidence";
  const minutes = Math.floor((Date.parse(now) - Date.parse(time)) / 60_000);
  if (!Number.isFinite(minutes) || minutes < 0) return "Unknown";
  return minutes < 60
    ? `${minutes}m ago`
    : `${Math.floor(minutes / 60)}h ${minutes % 60}m ago`;
}
export function filterAssets(
  assets: Asset[],
  query: string,
  status: string,
  source: string,
): Asset[] {
  const q = query.trim().toLowerCase();
  return assets.filter(
    (a) =>
      `${a.name} ${a.namespace} ${a.owner}`.toLowerCase().includes(q) &&
      (status === "all" || a.health === status) &&
      (source === "all" || a.source === source),
  );
}

export interface ColumnTarget {
  id: string;
  field: string;
}
