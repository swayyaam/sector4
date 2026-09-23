import { describe, expect, it } from "vitest";
import { distributionSummary, quantile } from "../src/lib/distribution";
import { loadDataset } from "../src/lib/data";

describe("distribution summaries", () => {
  it("reads the mode and the 10th and 90th percentiles", () => {
    const d = [0.05, 0.5, 0.2, 0.15, 0.1];
    expect(distributionSummary(d)).toEqual({ mode: 2, low: 2, high: 4 });
  });

  it("puts a certain finish at one position", () => {
    expect(distributionSummary([0, 0, 1, 0])).toEqual({ mode: 3, low: 3, high: 3 });
  });

  it("tolerates the 6dp rounding in published files", () => {
    // Sums to 0.9999999: the last position must still be reachable.
    expect(quantile([0.3333333, 0.3333333, 0.3333333], 1)).toBe(3);
  });

  it("the range it states holds at least eight in ten of the probability", () => {
    for (const p of loadDataset().predictions) {
      for (const d of p.drivers) {
        const s = distributionSummary(d.position_distribution);
        const inside = d.position_distribution.slice(s.low - 1, s.high).reduce((a, b) => a + b, 0);
        expect(inside).toBeGreaterThanOrEqual(0.8 - 1e-6);
      }
    }
  });
});
