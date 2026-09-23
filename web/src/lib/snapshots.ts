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

export const SNAPSHOT_LABEL: Record<Snapshot, string> = {
  pre_weekend: "Pre-weekend",
  post_qualifying: "Post-qualifying",
};

export const SNAPSHOT_BLURB: Record<Snapshot, string> = {
  pre_weekend: "Published before any car runs, so it cannot see qualifying or practice pace.",
  post_qualifying:
    "Published after qualifying. It adds qualifying position and this weekend's practice pace, which is most of what the model knows.",
};

/** The baseline each snapshot is scored beside: one that saw the same information. */
export const BASELINE_FOR: Record<Snapshot, string> = {
  pre_weekend: "championship order",
  post_qualifying: "qualifying order",
};

/**
 * Aggregates across races wait until a series has this many scored. Fewer is
 * too few to summarise, and a season figure from one or two races would be
 * read as more than it is.
 */
export const SCORED_SUMMARY_MINIMUM = 4;
