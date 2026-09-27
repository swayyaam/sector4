/**
 * The dataset must be valid, and invalid data must stop the build.
 *
 * The second half matters as much as the first: a validator that never rejects
 * anything gives false confidence. Each case below mutates a good file in one
 * specific way and asserts the exact failure.
 */
import { describe, expect, it } from "vitest";
import {
  checkReferentialIntegrity,
  parseOrThrow,
  predictionSchema,
  referenceSchema,
  siteMetaSchema,
  type Prediction,
} from "../src/lib/schema";
import {
  buildDataset,
  driverById,
  driversByWinProbability,
  loadDataset,
  logLossSummary,
  preferredSnapshot,
  scoredPredictions,
  teamById,
} from "../src/lib/data";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const MOCK = resolve(import.meta.dirname, "..", "src", "data", "mock");
const good = () =>
  JSON.parse(readFileSync(resolve(MOCK, "prediction-2026-15-post_qualifying.json"), "utf8"));

/**
 * The fixture, loaded explicitly.
 *
 * `loadDataset()` prefers real pipeline output once it exists, so a test that
 * reads it and then asserts something about the fixture is testing whichever
 * happens to be present. These two are kept apart on purpose.
 */
const MOCK_FILES = import.meta.glob("../src/data/mock/*.json", {
  eager: true,
  import: "default",
}) as Record<string, unknown>;

describe("the shipped dataset", () => {
  const data = loadDataset();

  it("loads and validates", () => {
    expect(data.reference.drivers.length).toBeGreaterThan(0);
    expect(data.predictions.length).toBeGreaterThan(0);
  });

  it("the preview banner matches what is actually loaded", () => {
    // The flag is not a setting anyone can forget to flip: it is derived from
    // the files, so real predictions and a sample-data banner cannot coexist.
    const anyMock = data.meta.is_mock || data.predictions.some((p) => p.is_mock);
    expect(data.isMock).toBe(anyMock);
  });

  it("has no dangling references", () => {
    expect(checkReferentialIntegrity(data.reference, data.predictions)).toEqual([]);
  });

  it("every prediction's probabilities sum correctly", () => {
    for (const p of data.predictions) {
      const n = p.drivers.length;
      const sum = (f: (d: (typeof p.drivers)[number]) => number) =>
        p.drivers.reduce((a, d) => a + f(d), 0);
      expect(
        sum((d) => d.p_win),
        `${p.season} R${p.round}`,
      ).toBeCloseTo(1, 5);
      expect(sum((d) => d.p_podium)).toBeCloseTo(Math.min(3, n), 5);
      expect(sum((d) => d.p_top10)).toBeCloseTo(Math.min(10, n), 5);
    }
  });

  it("the two snapshots are never pooled", () => {
    // They are different models measured against different baselines, so any
    // aggregate has to be computed per snapshot. This asserts the data keeps
    // them distinguishable; the pages are responsible for not mixing them.
    for (const p of data.predictions) {
      expect(["pre_weekend", "post_qualifying"]).toContain(p.snapshot);
    }
    const byRace = new Map<number, Set<string>>();
    for (const p of data.predictions) {
      if (!byRace.has(p.race_id)) byRace.set(p.race_id, new Set());
      byRace.get(p.race_id)!.add(p.snapshot);
    }
    for (const [, snaps] of byRace) expect(snaps.size).toBeLessThanOrEqual(2);
  });

  it("a scored prediction carries the baseline it was measured against", () => {
    for (const p of scoredPredictions(data.predictions)) {
      const base = p.result!.baseline;
      if (base === null) continue;
      expect(base.name.length).toBeGreaterThan(0);
      expect(base.log_loss).toBeGreaterThan(0);
    }
  });

  it("lookups cover every referenced id", () => {
    const drivers = driverById(data.reference);
    const teams = teamById(data.reference);
    for (const p of data.predictions) {
      for (const d of p.drivers) {
        expect(drivers.has(d.driverId)).toBe(true);
        expect(teams.has(d.team_entity_id)).toBe(true);
      }
    }
  });

  it("orders drivers by win probability, descending", () => {
    const p = data.predictions[0]!;
    const sorted = driversByWinProbability(p);
    for (let i = 1; i < sorted.length; i++) {
      expect(sorted[i - 1]!.p_win).toBeGreaterThanOrEqual(sorted[i]!.p_win);
    }
  });
});

describe("the fixture", () => {
  // Loaded explicitly. loadDataset() prefers real pipeline output once it
  // exists, so a test that reads it and then asserts something about the
  // fixture is testing whichever happens to be present.
  const data = buildDataset(MOCK_FILES);

  it("has both snapshots for the next race and results for past ones", () => {
    const next = data.meta.next_race!;
    expect(data.predictions.filter((p) => p.race_id === next.race_id)).toHaveLength(2);
    expect(scoredPredictions(data.predictions).length).toBeGreaterThanOrEqual(5);
  });

  it("shows hits and misses, so the track record exercises both", () => {
    const scored = scoredPredictions(data.predictions);
    const hits = scored.filter((p) => p.result!.winner_hit).length;
    expect(hits).toBeGreaterThan(0);
    expect(hits).toBeLessThan(scored.length);
  });

  it("prefers the post-qualifying snapshot", () => {
    const next = data.meta.next_race!;
    expect(preferredSnapshot(data.predictions, next.race_id)?.snapshot).toBe("post_qualifying");
  });

  it("is flagged as sample data, which is what drives the banner", () => {
    expect(data.isMock).toBe(true);
  });

  it("carries a baseline on every scored race", () => {
    for (const p of scoredPredictions(data.predictions)) {
      expect(p.result!.baseline).not.toBeNull();
    }
  });
});

describe("bad data fails the build", () => {
  const expectReject = (mutate: (p: ReturnType<typeof good>) => void, match: RegExp) => {
    const p = good();
    mutate(p);
    expect(() => parseOrThrow(predictionSchema, p, "test")).toThrow(match);
  };

  it("rejects p_win that does not sum to 1", () => {
    expectReject((p) => {
      p.drivers[0].p_win += 0.1;
    }, /p_win sums to/);
  });

  it("rejects p_podium that does not sum to 3", () => {
    expectReject((p) => {
      p.drivers[0].p_podium += 0.5;
    }, /p_podium sums to/);
  });

  it("rejects p_top10 that does not sum to 10", () => {
    expectReject((p) => {
      p.drivers[0].p_top10 = 0;
    }, /p_top10 sums to/);
  });

  it("rejects a position_distribution that does not sum to 1", () => {
    expectReject((p) => {
      p.drivers[0].position_distribution[0] += 0.2;
    }, /position_distribution sums to/);
  });

  it("rejects a position_distribution of the wrong length", () => {
    expectReject((p) => {
      p.drivers[0].position_distribution.pop();
    }, /position_distribution/);
  });

  it("rejects a probability above 1", () => {
    expectReject((p) => {
      p.drivers[0].p_dnf = 1.5;
    }, /failed validation/);
  });

  it("rejects a negative probability", () => {
    expectReject((p) => {
      p.drivers[0].p_dnf = -0.1;
    }, /failed validation/);
  });

  it("rejects p_win above p_podium, which no real model can produce", () => {
    expectReject((p) => {
      p.drivers[0].p_win = 0.9;
      p.drivers[0].p_podium = 0.1;
    }, /above p_podium/);
  });

  it("rejects p_podium above p_top10", () => {
    expectReject((p) => {
      p.drivers[0].p_podium = 0.9;
      p.drivers[0].p_top10 = 0.2;
    }, /above p_top10/);
  });

  it("rejects a duplicate driver", () => {
    expectReject((p) => {
      p.drivers[1].driverId = p.drivers[0].driverId;
    }, /appears twice/);
  });

  it("rejects a malformed commit sha", () => {
    expectReject((p) => {
      p.commit_sha = "not-a-sha";
    }, /failed validation/);
  });

  it("rejects a non-ISO generated_at", () => {
    expectReject((p) => {
      p.generated_at = "last Tuesday";
    }, /failed validation/);
  });

  it("rejects an unknown snapshot name", () => {
    expectReject((p) => {
      p.snapshot = "during_race";
    }, /failed validation/);
  });

  it("rejects a result scored before the prediction was made", () => {
    const p = good();
    p.result = {
      scored_at: "2020-01-01T00:00:00Z",
      drivers: [{ driverId: p.drivers[0].driverId, actual_position: 1, status: "Finished" }],
      log_loss: 1,
      brier: 0.5,
      winner_hit: true,
      podium_hits: 1,
    };
    expect(() => parseOrThrow(predictionSchema, p, "test")).toThrow(/scored before/);
  });

  it("rejects a result naming a driver with no prediction", () => {
    const p = good();
    p.result = {
      scored_at: "2026-09-26T14:00:00Z",
      drivers: [{ driverId: 99999, actual_position: 1, status: "Finished" }],
      log_loss: 1,
      brier: 0.5,
      winner_hit: false,
      podium_hits: 0,
    };
    expect(() => parseOrThrow(predictionSchema, p, "test")).toThrow(/no prediction/);
  });

  it("rejects two drivers sharing a finishing position", () => {
    const p = good();
    p.result = {
      scored_at: "2026-09-26T14:00:00Z",
      drivers: [
        { driverId: p.drivers[0].driverId, actual_position: 1, status: "Finished" },
        { driverId: p.drivers[1].driverId, actual_position: 1, status: "Finished" },
      ],
      log_loss: 1,
      brier: 0.5,
      winner_hit: true,
      podium_hits: 1,
    };
    expect(() => parseOrThrow(predictionSchema, p, "test")).toThrow(/share a finishing position/);
  });

  // A winner the snapshot never listed: pre-weekend carries the last race's
  // starters forward, so a returning driver can win without a prediction.
  const unpredictedWinner = (p: ReturnType<typeof good>) => ({
    scored_at: "2026-09-26T14:00:00Z",
    drivers: [
      { driverId: 99999, actual_position: 1, status: "Finished" },
      ...p.drivers.map((d: { driverId: number }, i: number) => ({
        driverId: d.driverId,
        actual_position: i + 2,
        status: "Finished",
      })),
    ],
    unpredicted_starters: [99999],
    log_loss: null as number | null,
    log_loss_undefined: "winner_not_in_field" as string | null,
    brier: 1.2,
    winner_hit: false,
    podium_hits: 1,
  });

  it("accepts an unpredicted winner with no log loss and the reason declared", () => {
    const p = good();
    p.result = unpredictedWinner(p);
    expect(() => parseOrThrow(predictionSchema, p, "test")).not.toThrow();
  });

  it("rejects a floor standing in for an unpredicted winner's log loss", () => {
    const p = good();
    p.result = { ...unpredictedWinner(p), log_loss: 20.7233, log_loss_undefined: null };
    expect(() => parseOrThrow(predictionSchema, p, "test")).toThrow(
      /prediction says winner_not_in_field/,
    );
  });

  it("rejects a missing log loss without a reason", () => {
    const p = good();
    p.result = { ...unpredictedWinner(p), log_loss_undefined: null };
    expect(() => parseOrThrow(predictionSchema, p, "test")).toThrow(/null exactly when/);
  });

  it("rejects a withheld log loss when the winner was given a probability", () => {
    const p = good();
    const winner = p.drivers[0].driverId;
    p.result = {
      scored_at: "2026-09-26T14:00:00Z",
      drivers: p.drivers.map((d: { driverId: number }, i: number) => ({
        driverId: d.driverId,
        actual_position: d.driverId === winner ? 1 : i + 2,
        status: "Finished",
      })),
      log_loss: null,
      log_loss_undefined: "winner_not_in_field",
      brier: 0.5,
      winner_hit: false,
      podium_hits: 1,
    };
    expect(() => parseOrThrow(predictionSchema, p, "test")).toThrow(/prediction says null/);
  });

  it("rejects a called winner that was given no probability", () => {
    const p = good();
    p.result = { ...unpredictedWinner(p), winner_hit: true };
    expect(() => parseOrThrow(predictionSchema, p, "test")).toThrow(/cannot have called/);
  });

  it("reports every problem at once, not just the first", () => {
    const p = good();
    p.commit_sha = "nope";
    p.drivers[0].p_dnf = 2;
    try {
      parseOrThrow(predictionSchema, p, "test");
      throw new Error("should have thrown");
    } catch (e) {
      const msg = (e as Error).message;
      expect(msg.split("\n").length).toBeGreaterThanOrEqual(3);
    }
  });
});

describe("log loss summary", () => {
  const row = (ll: number | null, base: number | null) =>
    ({
      result: {
        log_loss: ll,
        baseline: base === null ? null : { log_loss: base },
      },
    }) as unknown as Prediction;

  it("leaves a race with no log loss out of both means, and counts it", () => {
    const s = logLossSummary([row(0.4, 0.8), row(null, 0.6), row(1.0, 0.7)]);
    expect(s.mean).toBeCloseTo(0.7);
    // The baseline over the same two races, not all three.
    expect(s.baselineMean).toBeCloseTo(0.75);
    expect(s.undefined).toBe(1);
  });

  it("counts a race with no log loss as one the model did not beat", () => {
    const s = logLossSummary([row(0.4, 0.8), row(null, 0.6)]);
    expect(s.modelBetter).toBe(1);
    expect(s.withBaseline).toBe(2);
  });

  it("has no mean at all when no race has a log loss", () => {
    const s = logLossSummary([row(null, 0.6)]);
    expect(s.mean).toBeNull();
    expect(s.baselineMean).toBeNull();
  });
});

describe("reference data integrity", () => {
  const ref = () => JSON.parse(readFileSync(resolve(MOCK, "reference.json"), "utf8"));

  it("rejects a race pointing at a missing circuit", () => {
    const r = ref();
    r.races[0].circuit_id = 99999;
    expect(() => parseOrThrow(referenceSchema, r, "reference")).toThrow(/not in circuits/);
  });

  it("rejects duplicate driver ids", () => {
    const r = ref();
    r.drivers.push({ ...r.drivers[0] });
    expect(() => parseOrThrow(referenceSchema, r, "reference")).toThrow(/duplicate driverId/);
  });

  it("rejects two races sharing a slug in one season", () => {
    const r = ref();
    r.races[1].slug = r.races[0].slug;
    r.races[1].season = r.races[0].season;
    expect(() => parseOrThrow(referenceSchema, r, "reference")).toThrow(/duplicate race slug/);
  });

  it("rejects a team colour that is not a 6-digit hex", () => {
    const r = ref();
    r.teams[0].colour = "red";
    expect(() => parseOrThrow(referenceSchema, r, "reference")).toThrow(/failed validation/);
  });

  it("catches a prediction referencing an unknown driver", () => {
    const data = loadDataset();
    const p = structuredClone(data.predictions[0]!);
    p.drivers[0]!.driverId = 99999;
    expect(checkReferentialIntegrity(data.reference, [p])[0]).toMatch(/not in reference drivers/);
  });

  it("catches a prediction referencing an unknown team", () => {
    const data = loadDataset();
    const p = structuredClone(data.predictions[0]!);
    p.drivers[0]!.team_entity_id = "nope-1999";
    expect(checkReferentialIntegrity(data.reference, [p])[0]).toMatch(/not in reference teams/);
  });
});

describe("site metadata", () => {
  it("validates", () => {
    const m = JSON.parse(readFileSync(resolve(MOCK, "site_meta.json"), "utf8"));
    expect(() => parseOrThrow(siteMetaSchema, m, "site_meta")).not.toThrow();
  });

  it("rejects an unknown session name", () => {
    const m = JSON.parse(readFileSync(resolve(MOCK, "site_meta.json"), "utf8"));
    m.next_race.sessions[0].name = "Warm Up";
    expect(() => parseOrThrow(siteMetaSchema, m, "site_meta")).toThrow(/failed validation/);
  });
});
