/**
 * Load and validate every data file, once, at build time.
 *
 * Nothing reaches a page without passing validation. If a file is malformed or
 * the numbers do not hold together, the build stops with every problem listed
 * rather than rendering a wrong figure.
 *
 * The files are pulled in with import.meta.glob rather than read from disk.
 * Reading from disk works in dev and then fails in the build, where the
 * compiled module no longer sits beside src/data; globbing makes the bundler
 * resolve the paths at build time, so the data is baked into the output and
 * there is no filesystem access at render time at all.
 */
import {
  checkReferentialIntegrity,
  parseOrThrow,
  predictionSchema,
  referenceSchema,
  siteMetaSchema,
  type Circuit,
  type Driver,
  type Prediction,
  type Race,
  type Reference,
  type SiteMeta,
  type Team,
} from "./schema";

export interface Dataset {
  reference: Reference;
  predictions: Prediction[];
  meta: SiteMeta;
  /** True when any part of the dataset is sample data. Drives the site-wide banner. */
  isMock: boolean;
}

/** Raw JSON keyed by file path, exactly as import.meta.glob hands it over. */
export type RawFiles = Record<string, unknown>;

const MOCK_FILES = import.meta.glob("../data/mock/*.json", {
  eager: true,
  import: "default",
}) as RawFiles;

/**
 * Real pipeline output, when it exists. Built by src/build_site_data.py.
 *
 * The site prefers it over the fixtures automatically: there is no flag to
 * forget to flip, and no way to ship real predictions while still showing the
 * sample-data banner, or the reverse.
 */
const LIVE_FILES = import.meta.glob("../data/live/*.json", {
  eager: true,
  import: "default",
}) as RawFiles;

function basename(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}

/**
 * Validate a set of raw files into a Dataset. Pure, so it can be exercised with
 * deliberately broken input without touching the real data.
 */
export function buildDataset(files: RawFiles): Dataset {
  const byName = new Map(Object.entries(files).map(([path, value]) => [basename(path), value]));

  const referenceRaw = byName.get("reference.json");
  if (referenceRaw === undefined) throw new Error("reference.json is missing");
  const metaRaw = byName.get("site_meta.json");
  if (metaRaw === undefined) throw new Error("site_meta.json is missing");

  const reference = parseOrThrow(referenceSchema, referenceRaw, "reference.json");
  const meta = parseOrThrow(siteMetaSchema, metaRaw, "site_meta.json");

  // Sorted by filename so the build order — and therefore the output — does not
  // depend on how the filesystem happened to enumerate the directory.
  const predictionNames = [...byName.keys()]
    .filter((n) => n.startsWith("prediction-") && n.endsWith(".json"))
    .sort();
  if (predictionNames.length === 0) throw new Error("no prediction files found");

  const predictions = predictionNames.map((n) => parseOrThrow(predictionSchema, byName.get(n), n));

  const integrity = checkReferentialIntegrity(reference, predictions);
  if (integrity.length) {
    throw new Error(
      `referential integrity failed:\n${integrity.map((e) => `  - ${e}`).join("\n")}`,
    );
  }

  // One flag drives the preview banner. If any file is sample data the whole
  // site says so; it must not be possible to ship a page without the warning.
  const isMock = meta.is_mock || predictions.some((p) => p.is_mock);

  return { reference, predictions, meta, isMock };
}

let cached: Dataset | null = null;

function hasPredictions(files: RawFiles): boolean {
  return Object.keys(files).some((p) => basename(p).startsWith("prediction-"));
}

export function loadDataset(): Dataset {
  if (!cached) {
    cached = buildDataset(hasPredictions(LIVE_FILES) ? LIVE_FILES : MOCK_FILES);
  }
  return cached;
}

// ------------------------------------------------------------------ lookups
// One implementation each, so no page invents its own.

export function driverById(ref: Reference): Map<number, Driver> {
  return new Map(ref.drivers.map((d) => [d.driverId, d]));
}

export function teamById(ref: Reference): Map<string, Team> {
  return new Map(ref.teams.map((t) => [t.team_entity_id, t]));
}

export function raceById(ref: Reference): Map<number, Race> {
  return new Map(ref.races.map((r) => [r.race_id, r]));
}

export function circuitById(ref: Reference): Map<number, Circuit> {
  return new Map(ref.circuits.map((c) => [c.circuit_id, c]));
}

/** Both snapshots for one race, newest generation first within each. */
export function predictionsForRace(all: Prediction[], raceId: number): Prediction[] {
  const rank = (p: Prediction) => (p.snapshot === "post_qualifying" ? 0 : 1);
  return all.filter((p) => p.race_id === raceId).sort((a, b) => rank(a) - rank(b));
}

/** The snapshot a page should show by default: post-qualifying when it exists. */
export function preferredSnapshot(all: Prediction[], raceId: number): Prediction | undefined {
  const forRace = predictionsForRace(all, raceId);
  return forRace.find((p) => p.snapshot === "post_qualifying") ?? forRace[0];
}

/** Completed races, most recent first. */
export function scoredPredictions(all: Prediction[]): Prediction[] {
  return all
    .filter((p) => p.result !== null)
    .sort((a, b) => b.season - a.season || b.round - a.round);
}

/**
 * Mean log loss over the scored races that have one, and the baseline's mean
 * over the same races, so the two are always compared like for like.
 *
 * A snapshot that gave the winner no probability has no log loss. It is left
 * out of both means and counted in `undefined`, for the page to state, rather
 * than averaged in as a floor. It still counts as a race the model did not
 * beat the baseline.
 */
export function logLossSummary(rows: Prediction[]) {
  const defined = rows.filter((p) => p.result!.log_loss !== null);
  const paired = defined.filter((p) => p.result!.baseline !== null);
  const mean = (xs: number[]) => (xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : null);
  return {
    mean: mean(defined.map((p) => p.result!.log_loss!)),
    baselineMean: mean(paired.map((p) => p.result!.baseline!.log_loss)),
    undefined: rows.length - defined.length,
    withBaseline: rows.filter((p) => p.result!.baseline !== null).length,
    modelBetter: paired.filter((p) => p.result!.log_loss! < p.result!.baseline!.log_loss).length,
  };
}

export function driversByWinProbability(p: Prediction) {
  return [...p.drivers].sort((a, b) => b.p_win - a.p_win);
}

/** What happened at a race's circuit before it, when the pipeline computed it. */
export function circuitHistoryFor(ref: Reference, raceId: number) {
  return ref.circuit_history.find((h) => h.race_id === raceId);
}
