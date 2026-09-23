/**
 * Plain-language summaries of a published position distribution.
 *
 * position_distribution[k] is the model's probability of finishing in
 * position k + 1. Everything here is a deterministic reading of those numbers,
 * so the sentence under a chart can never disagree with the chart.
 */

export interface DistributionSummary {
  /** The single most likely position, 1-based. */
  mode: number;
  /**
   * The 10th and 90th percentile positions. Positions are whole numbers, so at
   * least eight in ten finishes fall between them, inclusive.
   */
  low: number;
  high: number;
}

/** The first position at which the cumulative probability reaches q. */
export function quantile(dist: number[], q: number): number {
  if (dist.length === 0) throw new RangeError("empty distribution");
  let cumulative = 0;
  for (let k = 0; k < dist.length; k++) {
    cumulative += dist[k]!;
    // A hair of tolerance: the stored values are rounded to 6dp.
    if (cumulative >= q - 1e-9) return k + 1;
  }
  return dist.length;
}

export function distributionSummary(dist: number[]): DistributionSummary {
  let mode = 0;
  for (let k = 1; k < dist.length; k++) if (dist[k]! > dist[mode]!) mode = k;
  return { mode: mode + 1, low: quantile(dist, 0.1), high: quantile(dist, 0.9) };
}
