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
} from "../src/lib/schema";
import {
  driverById,
  driversByWinProbability,
  loadDataset,
  preferredSnapshot,
  scoredPredictions,
  teamById,
} from "../src/lib/data";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const MOCK = resolve(import.meta.dirname, "..", "src", "data", "mock");
const good = () =>
  JSON.parse(readFileSync(resolve(MOCK, "prediction-2026-15-post_qualifying.json"), "utf8"));

describe("the shipped dataset", () => {
  const data = loadDataset();

  it("loads and validates", () => {
    expect(data.reference.drivers.length).toBeGreaterThan(0);
    expect(data.predictions.length).toBeGreaterThanOrEqual(7);
  });

  it("is flagged as mock, which drives the preview banner", () => {
    expect(data.isMock).toBe(true);
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
