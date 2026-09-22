/**
 * Emit the full mock dataset: predictions for the next race (both snapshots),
 * predictions plus scores for the five most recent completed races, and
 * site_meta.
 *
 * Predictions are MOCK. Race results are REAL, taken from the verified
 * pipeline: rendering invented finishing positions would put wrong facts on
 * the page, which the project's accuracy rules forbid. Only the probabilities
 * are fabricated, and they are flagged as such on every page.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { buildPrediction, mulberry32 } from "./generate-mock.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const DATA = join(HERE, "..", "src", "data", "mock");
const read = (f) => JSON.parse(readFileSync(join(DATA, f), "utf8"));
const write = (f, o) => writeFileSync(join(DATA, f), JSON.stringify(o, null, 2) + "\n");

const ref = read("reference.json");
const realResults = read("_real_results.json");
const byId = new Map(ref.races.map((r) => [r.race_id, r]));

/** Driver list for a race: the real entrants where known, else the season field. */
function fieldFor(raceId) {
  const seasonField = ref.drivers.map((d) => ({ driverId: d.driverId }));
  const real = realResults[String(raceId)];
  // Strength order drives the mock probabilities, so it decides how good the
  // sample model looks. Taking the field in finishing order makes it perfect
  // (5/5 winners); taking it in driverId order makes it random (0/5). Neither
  // exercises the UI honestly. Instead it is a NOISY version of the real
  // order: a plausibly imperfect model that produces both hits and misses.
  const base = real ? real.map((r) => r.driverId) : seasonField.map((d) => d.driverId);
  if (!real) return base.map((id) => ({ driverId: id, team_entity_id: teamOf(id) }));
  const rng = mulberry32(raceId * 7919);
  const ids = base
    .map((id, i) => ({ id, k: i + (rng() - 0.5) * 9 })) // ~4-place typical error
    .sort((a, b) => a.k - b.k)
    .map((x) => x.id);
  return ids.map((id) => {
    // team_entity_id for the season; mid-season moves are out of scope for mock data
    const team = ref.teams.find(
      (t) => ref.drivers.some((d) => d.driverId === id) && teamOf(id) === t.team_entity_id,
    );
    return {
      driverId: id,
      team_entity_id: team ? team.team_entity_id : ref.teams[0].team_entity_id,
    };
  });
}
const TEAM_OF = JSON.parse(readFileSync(join(DATA, "_driver_team.json"), "utf8"));
function teamOf(driverId) {
  return TEAM_OF[String(driverId)];
}

function score(pred, results) {
  // Seeded on the race so the fixture stays byte-identical across builds.
  const rng = mulberry32(pred.race_id * 104729 + 17);
  const winner = results.find((r) => r.actual_position === 1);
  const byDriver = new Map(pred.drivers.map((d) => [d.driverId, d]));
  const pWinner = winner ? (byDriver.get(winner.driverId)?.p_win ?? 1e-9) : 1e-9;
  const logLoss = -Math.log(Math.max(pWinner, 1e-9));
  const brier = pred.drivers.reduce((s, d) => {
    const y = winner && d.driverId === winner.driverId ? 1 : 0;
    return s + (d.p_win - y) ** 2;
  }, 0);
  const topWin = [...pred.drivers].sort((a, b) => b.p_win - a.p_win)[0];
  const predPodium = [...pred.drivers]
    .sort((a, b) => b.p_podium - a.p_podium)
    .slice(0, 3)
    .map((d) => d.driverId);
  const actualPodium = results
    .filter((r) => r.actual_position && r.actual_position <= 3)
    .map((r) => r.driverId);
  // The baseline the model is measured against, scored on the same race.
  // Deliberately close to the model's own number: the real one is, and a mock
  // that made the model look good would misrepresent the finding.
  const baseLogLoss = logLoss * (0.86 + rng() * 0.34);
  return {
    baseline: {
      name: "qualifying order",
      log_loss: Math.round(baseLogLoss * 1e6) / 1e6,
      brier: Math.round(brier * (0.9 + rng() * 0.25) * 1e6) / 1e6,
      winner_hit: topWin.driverId === (winner && winner.driverId) ? 1 : 0,
      podium_hits: Math.min(3, predPodium.filter((d) => actualPodium.includes(d)).length),
    },
    scored_at: new Date(Date.parse(byId.get(pred.race_id).starts_at) + 3 * 3600e3)
      .toISOString()
      .replace(".000", ""),
    drivers: results,
    log_loss: Math.round(logLoss * 1e6) / 1e6,
    brier: Math.round(brier * 1e6) / 1e6,
    winner_hit: !!winner && topWin.driverId === winner.driverId,
    podium_hits: predPodium.filter((d) => actualPodium.includes(d)).length,
  };
}

const files = [];
// --- next race, both snapshots
const next = ref.races.find((r) => r.round === 15);
const nextField = fieldFor(next.race_id);
for (const [snapshot, offsetH, seed] of [
  ["pre_weekend", -96, 1501],
  ["post_qualifying", -20, 1502],
]) {
  const generated_at = new Date(Date.parse(next.starts_at) + offsetH * 3600e3)
    .toISOString()
    .replace(".000", "");
  const p = buildPrediction({
    race: next,
    drivers: nextField,
    snapshot,
    seed,
    generatedAt: generated_at,
  });
  const name = `prediction-${next.season}-${next.round}-${snapshot}.json`;
  write(name, p);
  files.push([name, p]);
}
// --- five completed races, scored against real results
for (const rid of [1178, 1179, 1180, 1181, 1182]) {
  const race = byId.get(rid);
  const field = fieldFor(rid);
  const generated_at = new Date(Date.parse(race.starts_at) - 20 * 3600e3)
    .toISOString()
    .replace(".000", "");
  const p = buildPrediction({
    race,
    drivers: field,
    snapshot: "post_qualifying",
    seed: 2000 + rid,
    generatedAt: generated_at,
  });
  p.commit_sha = "0000000";
  p.result = score(p, realResults[String(rid)]);
  const name = `prediction-${race.season}-${race.round}-post_qualifying.json`;
  write(name, p);
  files.push([name, p]);
}

// --- site meta
const last = byId.get(1182);
write("site_meta.json", {
  data_version: "v0.1.1-data",
  generated_at: new Date("2026-09-21T22:00:00Z").toISOString().replace(".000", ""),
  is_mock: true,
  last_completed_race: {
    race_id: last.race_id,
    season: last.season,
    round: last.round,
    name: last.name,
    slug: last.slug,
    circuit_id: last.circuit_id,
    starts_at: last.starts_at,
  },
  next_race: {
    race_id: next.race_id,
    season: next.season,
    round: next.round,
    name: next.name,
    slug: next.slug,
    circuit_id: next.circuit_id,
    starts_at: next.starts_at,
    sessions: [
      { name: "Practice 1", starts_at: "2026-09-24T09:30:00Z" },
      { name: "Practice 2", starts_at: "2026-09-24T13:00:00Z" },
      { name: "Practice 3", starts_at: "2026-09-25T09:30:00Z" },
      { name: "Qualifying", starts_at: "2026-09-25T13:00:00Z" },
      { name: "Race", starts_at: "2026-09-26T11:00:00Z" },
    ],
  },
});

const sum = (a) => a.reduce((x, y) => x + y, 0);
console.log(`wrote ${files.length} predictions + site_meta.json`);
for (const [name, p] of files) {
  const w = sum(p.drivers.map((d) => d.p_win));
  console.log(
    `  ${name.padEnd(46)} n=${String(p.drivers.length).padStart(2)} ` +
      `sum(p_win)=${w.toFixed(9)} ${p.result ? `logloss=${p.result.log_loss.toFixed(3)} hit=${p.result.winner_hit} podium=${p.result.podium_hits}/3` : "(no result yet)"}`,
  );
}
