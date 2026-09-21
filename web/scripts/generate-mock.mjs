/**
 * Generate schema-valid MOCK prediction data.
 *
 * The probability constraints are not decorative: p_win must sum to 1, p_podium
 * to 3, p_top10 to 10, and every driver's position_distribution to 1. Inventing
 * numbers and nudging them would satisfy the sums while producing a matrix that
 * cannot correspond to any real race. Instead this samples finishing orders from
 * a Plackett-Luce model, so the position matrix is a genuine distribution over
 * orderings and every constraint holds by construction rather than by patching.
 *
 * Deterministic: a fixed seed means regenerating produces byte-identical files.
 */
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "src", "data", "mock");

// ---------------------------------------------------------------- seeded rng
function mulberry32(a) {
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const round6 = (x) => Math.round(x * 1e6) / 1e6;

/**
 * Sample N finishing orders under Plackett-Luce and return the position matrix.
 * matrix[i][j] = P(driver i finishes in position j+1). Rows sum to 1 and
 * columns sum to 1 by construction.
 */
function positionMatrix(strengths, rng, draws = 40000) {
  const n = strengths.length;
  const counts = Array.from({ length: n }, () => new Array(n).fill(0));
  for (let d = 0; d < draws; d++) {
    const pool = strengths.map((w, i) => ({ i, w }));
    for (let pos = 0; pos < n; pos++) {
      const total = pool.reduce((s, p) => s + p.w, 0);
      let r = rng() * total;
      let k = 0;
      while (k < pool.length - 1 && (r -= pool[k].w) > 0) k++;
      counts[pool[k].i][pos]++;
      pool.splice(k, 1);
    }
  }
  return counts.map((row) => row.map((c) => c / draws));
}

/** Force a vector to sum exactly to `target` after rounding, without distorting shape. */
function normaliseTo(vec, target) {
  const s = vec.reduce((a, b) => a + b, 0);
  const scaled = vec.map((v) => (v * target) / s);
  const rounded = scaled.map(round6);
  // push the rounding residue onto the largest element so the sum is exact
  const drift = round6(target - rounded.reduce((a, b) => a + b, 0));
  if (drift !== 0) {
    const i = rounded.indexOf(Math.max(...rounded));
    rounded[i] = round6(rounded[i] + drift);
  }
  return rounded;
}

export function buildPrediction({ race, drivers, snapshot, seed, generatedAt, result = null }) {
  const rng = mulberry32(seed);
  // Deliberately arbitrary strengths: this is sample data, not a forecast.
  const strengths = drivers.map((_, i) => Math.exp(-(i * 0.22) + (rng() - 0.5) * 0.5));
  const M = positionMatrix(strengths, rng);
  const n = drivers.length;

  const pWinRaw = M.map((r) => r[0]);
  const pWin = normaliseTo(pWinRaw, 1);
  const pPodium = normaliseTo(
    M.map((r) => r.slice(0, 3).reduce((a, b) => a + b, 0)),
    3,
  );
  const pTop10 = normaliseTo(
    M.map((r) => r.slice(0, Math.min(10, n)).reduce((a, b) => a + b, 0)),
    Math.min(10, n),
  );

  // Factors have to be coherent with the snapshot they belong to: a prediction
  // made before the cars run cannot cite a qualifying position. Sample data
  // that says otherwise teaches the wrong thing about the product.
  const PRE_WEEKEND_FACTORS = [
    ["Team form, last 5 races", "positive"],
    ["Circuit history", "positive"],
    ["Car pace, season to date", "positive"],
    ["Reliability, season to date", "negative"],
    ["Overtaking difficulty here", "negative"],
    ["Driver form, last 5 races", "positive"],
    ["Expected grid penalty", "negative"],
    ["Teammate pace gap", "negative"],
  ];
  const POST_QUALIFYING_FACTORS = [
    ["Qualifying position", "positive"],
    ["Gap to pole", "negative"],
    ["Long-run practice pace", "positive"],
    ["Grid penalty", "negative"],
    ["Teammate qualifying gap", "negative"],
    ["Overtaking difficulty here", "negative"],
    ["Team form, last 5 races", "positive"],
    ["Circuit history", "positive"],
  ];
  const FACTORS = snapshot === "post_qualifying" ? POST_QUALIFYING_FACTORS : PRE_WEEKEND_FACTORS;

  return {
    race_id: race.race_id,
    season: race.season,
    round: race.round,
    snapshot,
    generated_at: generatedAt,
    model_version: "mock-v0",
    data_version: "v0.1.1-data",
    commit_sha: "0000000",
    is_mock: true,
    drivers: drivers.map((d, i) => ({
      driverId: d.driverId,
      team_entity_id: d.team_entity_id,
      p_win: pWin[i],
      p_podium: pPodium[i],
      p_top10: pTop10[i],
      p_dnf: round6(0.04 + rng() * 0.14),
      expected_position: round6(M[i].reduce((s, p, j) => s + p * (j + 1), 0)),
      position_distribution: normaliseTo(M[i], 1),
      top_factors: Array.from({ length: 3 }, (_, k) => {
        const [label, direction] = FACTORS[(i * 3 + k) % FACTORS.length];
        return { label, direction, magnitude: round6(0.25 + rng() * 0.7) };
      }),
    })),
    result,
  };
}

export { mulberry32, positionMatrix, normaliseTo, round6, OUT, writeFileSync, mkdirSync, join };
