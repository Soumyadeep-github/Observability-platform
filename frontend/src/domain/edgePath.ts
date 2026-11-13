import type { PositionedEdge } from "../vendor/marquez/types";

/** One continuous curve with tangents aligned to the dataset/job ports. */
export function smoothEdgePath(
  edge: Pick<PositionedEdge, "startPoint" | "endPoint" | "bendPoints">,
  direction: "right" | "down",
): string {
  const start = edge.startPoint,
    end = edge.endPoint;
  if (direction === "down") {
    const middle = (start.y + end.y) / 2;
    return `M${start.x},${start.y}C${start.x},${middle},${end.x},${middle},${end.x},${end.y}`;
  }
  const middle = (start.x + end.x) / 2;
  return `M${start.x},${start.y}C${middle},${start.y},${middle},${end.y},${end.x},${end.y}`;
}
