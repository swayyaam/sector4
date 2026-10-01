/**
 * What each published model uses, in a fan's words.
 *
 * Keyed on the version a prediction file records, so a page describes a
 * prediction by the model that actually made it. When a model is replaced,
 * the predictions it made keep an accurate description instead of inheriting
 * the new one's. A version with no entry stops the build.
 */
import type { Snapshot } from "./snapshots";

export const MODEL_PLAIN: Record<string, Partial<Record<Snapshot, string>>> = {
  "minimal4-share-v1": {
    pre_weekend:
      "only the championship standings: each driver's points, and their share of their team's points",
    post_qualifying:
      "where each driver qualified, their practice pace, their championship points and their share of their team's points",
  },
  "pre-form-quali-v1": {
    pre_weekend:
      "each driver's and team's recent finishes, points and retirements, the championship standings, and recent qualifying, all from races before this one",
  },
  "practice-form-v1": {
    post_practice:
      "each driver's and team's recent form, the championship standings, recent qualifying, and this weekend's practice pace before qualifying",
  },
  "mock-v0": {
    pre_weekend: "sample data generated to test the layout, not a real model",
    post_qualifying: "sample data generated to test the layout, not a real model",
  },
};

/**
 * Models whose factors are read from their own coefficients, where two
 * overlapping inputs can pull in opposite directions. Said once beside the
 * factors, so a surprising "hurts" is not mistaken for a bug.
 */
const OVERLAP =
  "Some inputs overlap, so the model weighs them against each other. For the same championship points, more team points mean a stronger teammate, which can count against a driver.";
export const FACTOR_NOTE: Record<string, string> = {
  "pre-form-quali-v1": OVERLAP,
  "practice-form-v1": OVERLAP,
};

export function describeModel(version: string, snapshot: Snapshot): string {
  const plain = MODEL_PLAIN[version]?.[snapshot];
  if (!plain) {
    throw new Error(
      `No plain description for model ${version} at ${snapshot}. Add one to src/lib/models.ts.`,
    );
  }
  return plain;
}
