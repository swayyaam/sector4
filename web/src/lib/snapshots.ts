/**
 * The two snapshots, named once.
 *
 * They are different models measured against different baselines, so every
 * page that summarises results does it per snapshot and never averages the
 * two together.
 */
import type { Prediction } from "./schema";

export type Snapshot = Prediction["snapshot"];

/** Post-qualifying first: the sharper call, and the one a race-day reader wants. */
export const SERIES: Snapshot[] = ["post_qualifying", "pre_weekend"];

/**
 * Named for when each one is published, in words a fan uses. The data keeps
 * its own identifiers (`pre_weekend`, `post_qualifying`); only the labels
 * change.
 */
export const SNAPSHOT_LABEL: Record<Snapshot, string> = {
  pre_weekend: "Before practice",
  post_qualifying: "After qualifying",
};

export const SNAPSHOT_BLURB: Record<Snapshot, string> = {
  pre_weekend:
    "Published before the first practice session, so it knows nothing from this weekend yet.",
  post_qualifying:
    "Published after qualifying, so it knows where everyone qualified and how quick they were in practice.",
};

/** The baseline each snapshot is scored beside: one that saw the same information. */
export const BASELINE_FOR: Record<Snapshot, string> = {
  pre_weekend: "championship order",
  post_qualifying: "qualifying order",
};

/**
 * The same baselines in a sentence a fan can follow: a simple rule anyone
 * could apply, which the model has to beat to be worth reading.
 */
export const BASELINE_PLAIN: Record<Snapshot, string> = {
  pre_weekend:
    "giving each driver the chance of winning that their championship position has had in past races",
  post_qualifying:
    "giving each driver the chance of winning that their qualifying position has had in past races",
};

/**
 * Aggregates across races wait until a series has this many scored. Fewer is
 * too few to summarise, and a season figure from one or two races would be
 * read as more than it is.
 */
export const SCORED_SUMMARY_MINIMUM = 4;
