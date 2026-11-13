import { expect, it } from "vitest";
import { smoothEdgePath } from "./edgePath";
const numbers = (path: string) =>
  path.match(/-?\d*\.?\d+(?:e[-+]?\d+)?/gi)!.map(Number);
it("draws a smooth curve between the original horizontal ports", () => {
  const path = smoothEdgePath(
    { startPoint: { x: 100, y: 40 }, endPoint: { x: 180, y: 90 } },
    "right",
  );
  expect(path).toContain("C");
  expect(numbers(path).slice(0, 2)).toEqual([100, 40]);
  expect(numbers(path).slice(-2)).toEqual([180, 90]);
});
it("replaces cramped orthogonal bends with a continuous curve inside the port bounds", () => {
  const path = smoothEdgePath(
    {
      startPoint: { x: 0, y: 0 },
      bendPoints: [
        { x: 40, y: 0 },
        { x: 40, y: 100 },
      ],
      endPoint: { x: 80, y: 100 },
    },
    "right",
  );
  expect(path.match(/C/g)).toHaveLength(1);
  expect(path).not.toMatch(/[LQ]/);
  const coords = numbers(path);
  expect(coords.slice(0, 2)).toEqual([0, 0]);
  expect(coords.slice(-2)).toEqual([80, 100]);
  expect(coords.every(Number.isFinite)).toBe(true);
  for (let i = 0; i < coords.length; i += 2) {
    expect(coords[i]).toBeGreaterThanOrEqual(0);
    expect(coords[i]).toBeLessThanOrEqual(80);
    expect(coords[i + 1]).toBeGreaterThanOrEqual(0);
    expect(coords[i + 1]).toBeLessThanOrEqual(100);
  }
});
it("handles vertical and coincident ports without invalid geometry", () => {
  const path = smoothEdgePath(
    { startPoint: { x: 50, y: 20 }, endPoint: { x: 50, y: 120 } },
    "down",
  );
  expect(numbers(path).slice(-2)).toEqual([50, 120]);
  expect(
    numbers(
      smoothEdgePath(
        { startPoint: { x: 0, y: 0 }, endPoint: { x: 0, y: 0 } },
        "right",
      ),
    ).every(Number.isFinite),
  ).toBe(true);
});

it("keeps aligned links straight without decorative waves and maintains horizontal port tangents", () => {
  expect(
    smoothEdgePath(
      { startPoint: { x: 100, y: 40 }, endPoint: { x: 196, y: 40 } },
      "right",
    ),
  ).toBe("M100,40C148,40,148,40,196,40");
  const coords = numbers(
    smoothEdgePath(
      { startPoint: { x: 100, y: 40 }, endPoint: { x: 196, y: 400 } },
      "right",
    ),
  );
  expect(coords).toEqual([100, 40, 148, 40, 148, 400, 196, 400]);
});
