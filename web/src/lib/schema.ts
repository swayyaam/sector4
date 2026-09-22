/**
 * Runtime validation of every data file the site builds from.
 *
 * The JSON Schemas in /schema describe shape. They cannot express the
 * constraints that actually matter here — that win probabilities sum to one
 * across a field, that every driver referenced exists — because those are
 * relationships between rows, not properties of one. Those live here, and the
 * build fails on violation rather than rendering a wrong number.
 */
import { z } from "zod";

/**
 * Probabilities are stored rounded to 6dp, so a sum over ~23 drivers can drift
 * by a few times 1e-9. Anything beyond this is a real error, not float noise.
 */
export const SUM_TOLERANCE = 1e-6;

const probability = z.number().min(0).max(1);
const isoDateTime = z.iso.datetime();

/** Sum helper that keeps the failure message useful. */
function sumsTo(values: number[], target: number): { ok: boolean; actual: number } {
  const actual = values.reduce((a, b) => a + b, 0);
  return { ok: Math.abs(actual - target) <= SUM_TOLERANCE, actual };
}

// ----------------------------------------------------------------- reference
export const driverSchema = z.object({
  driverId: z.int().positive(),
  driverRef: z.string().regex(/^[a-z0-9_]+$/),
  code: z
    .string()
    .regex(/^[A-Z]{3}$/)
    .nullable(),
  permanent_number: z.int().min(0).max(99).nullable(),
  forename: z.string().min(1),
  surname: z.string().min(1),
  nationality: z.string().min(1),
  photo: z
    .object({
      file: z.string().min(1),
      width: z.int().positive(),
      height: z.int().positive(),
      credit_id: z.string().min(1),
    })
    .nullable(),
});

export const teamSchema = z.object({
  team_entity_id: z.string().min(1),
  constructorId: z.int().positive(),
  constructorRef: z.string().regex(/^[a-z0-9_]+$/),
  name: z.string().min(1),
  short_name: z.string().min(1).max(16),
  season: z.int().min(1950).max(2100),
  colour: z.string().regex(/^#[0-9a-f]{6}$/),
  colour_on_light: z.string().regex(/^#[0-9a-f]{6}$/),
});

export const raceSchema = z.object({
  race_id: z.int().positive(),
  season: z.int().min(1950).max(2100),
  round: z.int().min(1).max(30),
  name: z.string().min(1),
  slug: z.string().regex(/^[a-z0-9]+(-[a-z0-9]+)*$/),
  circuit_id: z.int().positive(),
  starts_at: isoDateTime,
  regs_era: z.string().min(1),
});

export const circuitSchema = z.object({
  circuit_id: z.int().positive(),
  circuitRef: z.string().regex(/^[a-z0-9_]+$/),
  name: z.string().min(1),
  locality: z.string().min(1),
  country: z.string().min(1),
  lat: z.number().min(-90).max(90),
  lng: z.number().min(-180).max(180),
  track_path: z.string().min(1).nullable(),
  track_view_box: z.string().min(1).nullable(),
  track_credit_id: z.string().min(1).nullable(),
});

export const referenceSchema = z
  .object({
    drivers: z.array(driverSchema).min(1),
    teams: z.array(teamSchema).min(1),
    races: z.array(raceSchema).min(1),
    circuits: z.array(circuitSchema).min(1),
  })
  .superRefine((ref, ctx) => {
    const dup = <T>(items: T[], key: (t: T) => string | number, label: string) => {
      const seen = new Set<string | number>();
      for (const i of items) {
        const k = key(i);
        if (seen.has(k)) {
          ctx.addIssue({ code: "custom", message: `duplicate ${label}: ${k}` });
        }
        seen.add(k);
      }
    };
    dup(ref.drivers, (d) => d.driverId, "driverId");
    dup(ref.teams, (t) => t.team_entity_id, "team_entity_id");
    dup(ref.races, (r) => r.race_id, "race_id");
    dup(ref.circuits, (c) => c.circuit_id, "circuit_id");

    const circuitIds = new Set(ref.circuits.map((c) => c.circuit_id));
    for (const r of ref.races) {
      if (!circuitIds.has(r.circuit_id)) {
        ctx.addIssue({
          code: "custom",
          message: `race ${r.race_id} (${r.name}) references circuit_id ${r.circuit_id}, which is not in circuits`,
        });
      }
    }
    // Slugs address pages, so a collision inside a season would make one race unreachable.
    const slugs = new Set<string>();
    for (const r of ref.races) {
      const key = `${r.season}/${r.slug}`;
      if (slugs.has(key)) {
        ctx.addIssue({ code: "custom", message: `duplicate race slug for ${key}` });
      }
      slugs.add(key);
    }
  });

// ---------------------------------------------------------------- prediction
export const topFactorSchema = z.object({
  label: z.string().min(1).max(80),
  direction: z.enum(["positive", "negative"]),
  magnitude: z.number().min(0).max(1),
});

export const driverPredictionSchema = z.object({
  driverId: z.int().positive(),
  team_entity_id: z.string().min(1),
  p_win: probability,
  p_podium: probability,
  p_top10: probability,
  p_dnf: probability,
  expected_position: z.number().min(1).max(30),
  position_distribution: z.array(probability).min(1).max(30),
  top_factors: z.array(topFactorSchema).max(6),
});

/**
 * What the qualifying-order baseline scored on the same race.
 *
 * Shown beside the model's own number on the track record, because a log loss
 * with nothing to compare it against tells a reader nothing, and because the
 * model has no out-of-sample evidence that it beats this baseline. Letting
 * people see both is more honest than any sentence we could write.
 */
export const baselineScoreSchema = z.object({
  name: z.string().min(1),
  log_loss: z.number().min(0),
  brier: z.number().min(0).max(2),
  winner_hit: z.number().min(0).max(1),
  podium_hits: z.number().min(0).max(3),
});

export const raceResultSchema = z.object({
  scored_at: isoDateTime,
  baseline: baselineScoreSchema.nullable().default(null),
  drivers: z
    .array(
      z.object({
        driverId: z.int().positive(),
        actual_position: z.int().min(1).max(30).nullable(),
        status: z.string().min(1),
      }),
    )
    .min(1),
  log_loss: z.number().min(0),
  brier: z.number().min(0).max(2),
  winner_hit: z.boolean(),
  podium_hits: z.int().min(0).max(3),
});

export const predictionSchema = z
  .object({
    race_id: z.int().positive(),
    season: z.int().min(1950).max(2100),
    round: z.int().min(1).max(30),
    snapshot: z.enum(["pre_weekend", "post_qualifying"]),
    generated_at: isoDateTime,
    model_version: z.string().min(1),
    data_version: z.string().min(1),
    commit_sha: z.string().regex(/^[0-9a-f]{7,40}$/),
    is_mock: z.boolean().default(false),
    /** What the model actually used, so a page can say so rather than imply it. */
    model_features: z.array(z.string().min(1)).optional(),
    model_note: z.string().min(1).optional(),
    /**
     * Predictions are append-only. A correction before the session is a new
     * revision, and the page shows every one, including the ones that did not
     * count, so a reader can see what was published when.
     */
    revision: z.int().min(1).default(1),
    published_commit: z
      .string()
      .regex(/^[0-9a-f]{7,40}$/)
      .nullable()
      .default(null),
    revisions: z
      .array(
        z.object({
          revision: z.int().min(1),
          file: z.string().min(1),
          generated_at: isoDateTime,
          published_commit: z
            .string()
            .regex(/^[0-9a-f]{7,40}$/)
            .nullable(),
          supersedes: z.string().nullable().optional(),
          superseded_by: z.string().nullable().optional(),
          reason: z.string().nullable().optional(),
          effective: z.boolean(),
          late: z.boolean(),
        }),
      )
      .default([]),
    drivers: z.array(driverPredictionSchema).min(1).max(30),
    result: raceResultSchema.nullable(),
  })
  .superRefine((p, ctx) => {
    const at = (m: string) => ctx.addIssue({ code: "custom", message: `${label(p)}: ${m}` });
    const n = p.drivers.length;

    const ids = new Set<number>();
    for (const d of p.drivers) {
      if (ids.has(d.driverId)) at(`driverId ${d.driverId} appears twice`);
      ids.add(d.driverId);
    }

    // A driver cannot be more likely to win than to finish on the podium, nor
    // more likely to podium than to finish in the top ten. A model that emits
    // this is broken even though each value is individually a valid probability.
    for (const d of p.drivers) {
      if (d.p_win > d.p_podium + SUM_TOLERANCE) {
        at(`driver ${d.driverId} has p_win ${d.p_win} above p_podium ${d.p_podium}`);
      }
      if (d.p_podium > d.p_top10 + SUM_TOLERANCE) {
        at(`driver ${d.driverId} has p_podium ${d.p_podium} above p_top10 ${d.p_top10}`);
      }
      if (d.position_distribution.length !== n) {
        at(
          `driver ${d.driverId} has a ${d.position_distribution.length}-long position_distribution ` +
            `for a ${n}-driver field`,
        );
      }
      const row = sumsTo(d.position_distribution, 1);
      if (!row.ok) {
        at(`driver ${d.driverId} position_distribution sums to ${row.actual}, expected 1`);
      }
    }

    // Exactly one driver wins, three finish on the podium, ten in the top ten.
    const win = sumsTo(
      p.drivers.map((d) => d.p_win),
      1,
    );
    if (!win.ok) at(`p_win sums to ${win.actual} across ${n} drivers, expected 1`);

    const podium = sumsTo(
      p.drivers.map((d) => d.p_podium),
      Math.min(3, n),
    );
    if (!podium.ok) at(`p_podium sums to ${podium.actual}, expected ${Math.min(3, n)}`);

    const top10 = sumsTo(
      p.drivers.map((d) => d.p_top10),
      Math.min(10, n),
    );
    if (!top10.ok) at(`p_top10 sums to ${top10.actual}, expected ${Math.min(10, n)}`);

    if (p.result) {
      const predicted = new Set(p.drivers.map((d) => d.driverId));
      for (const r of p.result.drivers) {
        if (!predicted.has(r.driverId)) {
          at(`result includes driver ${r.driverId}, who has no prediction`);
        }
      }
      const finishers = p.result.drivers
        .map((r) => r.actual_position)
        .filter((x): x is number => x !== null);
      if (new Set(finishers).size !== finishers.length) {
        at("two drivers share a finishing position");
      }
      if (p.result.scored_at < p.generated_at) {
        at("result was scored before the prediction was generated");
      }
    }
  });

function label(p: { season: number; round: number; snapshot: string }): string {
  return `${p.season} R${p.round} ${p.snapshot}`;
}

// -------------------------------------------------------------- site metadata
const raceRefSchema = z.object({
  race_id: z.int().positive(),
  season: z.int().min(1950).max(2100),
  round: z.int().min(1).max(30),
  name: z.string().min(1),
  slug: z.string().regex(/^[a-z0-9]+(-[a-z0-9]+)*$/),
  circuit_id: z.int().positive(),
  starts_at: isoDateTime,
});

/**
 * Counts the methodology and data pages quote, produced by the pipeline.
 *
 * Here rather than written into a template because a figure typed by hand is a
 * figure nobody notices going stale, and the project's rule is that every
 * number on the site comes from validated data or the build fails.
 */
export const pipelineSummarySchema = z.object({
  tables: z.record(
    z.string(),
    z.object({ rows: z.int().min(0), by_source: z.record(z.string(), z.int().min(0)) }),
  ),
  corrections: z.object({
    total: z.int().min(0),
    by_evidence: z.record(z.string(), z.int().min(0)),
  }),
  unresolved_conflicts: z.int().min(0),
  validation: z.object({
    passed: z.int().min(0).nullable(),
    failed: z.int().min(0).nullable(),
  }),
  seasons: z.object({ first: z.int(), last: z.int() }),
  enrichment_first_season: z.int(),
});

export const siteMetaSchema = z.object({
  data_version: z.string().min(1),
  generated_at: isoDateTime,
  is_mock: z.boolean(),
  pipeline: pipelineSummarySchema.nullable().default(null),
  last_completed_race: raceRefSchema.nullable(),
  next_race: raceRefSchema
    .extend({
      sessions: z
        .array(
          z.object({
            name: z.enum([
              "Practice 1",
              "Practice 2",
              "Practice 3",
              "Sprint Qualifying",
              "Sprint Shootout",
              "Sprint",
              "Qualifying",
              "Race",
            ]),
            starts_at: isoDateTime,
          }),
        )
        .min(1),
    })
    .nullable(),
});

export type Reference = z.infer<typeof referenceSchema>;
export type Prediction = z.infer<typeof predictionSchema>;
export type DriverPrediction = z.infer<typeof driverPredictionSchema>;
export type SiteMeta = z.infer<typeof siteMetaSchema>;
export type PipelineSummary = z.infer<typeof pipelineSummarySchema>;
export type Driver = z.infer<typeof driverSchema>;
export type Team = z.infer<typeof teamSchema>;
export type Race = z.infer<typeof raceSchema>;
export type BaselineScore = z.infer<typeof baselineScoreSchema>;
export type Circuit = z.infer<typeof circuitSchema>;

/**
 * Cross-file integrity: a prediction may only reference drivers, teams and
 * races that exist. Checked separately because no single file can see this.
 */
export function checkReferentialIntegrity(ref: Reference, predictions: Prediction[]): string[] {
  const drivers = new Set(ref.drivers.map((d) => d.driverId));
  const teams = new Set(ref.teams.map((t) => t.team_entity_id));
  const races = new Set(ref.races.map((r) => r.race_id));
  const errors: string[] = [];

  for (const p of predictions) {
    const where = label(p);
    if (!races.has(p.race_id))
      errors.push(`${where}: race_id ${p.race_id} is not in reference races`);
    for (const d of p.drivers) {
      if (!drivers.has(d.driverId))
        errors.push(`${where}: driverId ${d.driverId} is not in reference drivers`);
      if (!teams.has(d.team_entity_id)) {
        errors.push(`${where}: team_entity_id "${d.team_entity_id}" is not in reference teams`);
      }
    }
  }
  return errors;
}

/** Throw with every problem listed, not just the first. */
export function parseOrThrow<T>(schema: z.ZodType<T>, value: unknown, source: string): T {
  const result = schema.safeParse(value);
  if (result.success) return result.data;
  const lines = result.error.issues.map((i) => {
    const path = i.path.length ? ` at ${i.path.join(".")}` : "";
    return `  - ${i.message}${path}`;
  });
  throw new Error(`${source} failed validation:\n${lines.join("\n")}`);
}
