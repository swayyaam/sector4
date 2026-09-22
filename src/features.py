"""Phase 2 Part B: features for race prediction.

Two rules shape everything here.

**Every feature is computed from a cut.** A feature for race R may only see
races strictly before R, plus — at the post-qualifying snapshot — R's own
practice and qualifying. Nothing from R's race, ever. This is enforced by
construction and tested by rebuilding the whole feature frame against a
truncated dataset and requiring byte-identical output (tests/test_features.py).

**Every feature must be computable for a race that has not happened.** That is
the point of the exercise: the entrant list, every rolling window and every
circuit statistic are derived from completed races and from sessions that
precede the race being predicted. Nothing reads a result that does not exist
yet, so the same code path serves training and prediction.

Two snapshots, matching what the site publishes:

* ``pre_weekend`` — before any car runs. Form, reliability, circuit history.
* ``post_qualifying`` — adds this weekend's practice and qualifying.

Decisions recorded in CLAUDE.md and ENRICHMENT_REPORT.md that bind here:

* 2018 tyre compounds are absolute names and are never mapped onto the relative
  scheme. Compound features are 2019 onward; 2018 gets null.
* The 2020 Austrian and 2018 Bahrain Grands Prix are excluded from lap-derived
  features only, not from the dataset or the targets. Same for the 2018 Italian
  Grand Prix's tyre fields, which FastF1 could not parse.
* Reserve and FP1-only drivers are excluded from team practice pace by default.
* Race duration reconstructed from laps must account for red-flag suspensions
  and post-race time penalties.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

ROOT = Path(__file__).resolve().parents[1]
PROCESSED = ROOT / "data" / "processed"
ENRICHED = ROOT / "data" / "enriched"

FIRST_SEASON = 2018
PRE, POST = "pre_weekend", "post_qualifying"

# Races whose FastF1 lap timing disagrees with our tables badly enough to be
# unusable. Established in ENRICHMENT_REPORT.md §2. Excluded from lap-derived
# features only; their results and targets stay in the dataset.
LAP_UNUSABLE = {
    (2020, "Austrian Grand Prix"),
    (2018, "Bahrain Grand Prix"),
}
# 2018 is the only season using absolute compound names. See §5.
FIRST_RELATIVE_COMPOUND_SEASON = 2019


@dataclass(frozen=True)
class Feature:
    """One column, and the one-line reason it exists."""

    name: str
    group: str
    snapshot: str          # earliest snapshot at which it can be computed
    why: str
    nullable: bool = True


FEATURES: tuple[Feature, ...] = (
    # ---------------------------------------------------------------- context
    Feature("round_index", "Context", PRE,
            "Form means less in round 2 than round 20; the model needs to know where it is.",
            nullable=False),
    Feature("seasons_into_regs_era", "Context", PRE,
            "History across a regulation reset is weak evidence, and 2026 is a reset.",
            nullable=False),
    Feature("circuit_prior_races", "Context", PRE,
            "How much circuit history exists at all; a new venue has none and must say so.",
            nullable=False),
    Feature("circuit_overtaking_difficulty", "Context", PRE,
            "Mean |grid − finish| in prior runnings: where position change is rare, the grid decides the race."),
    Feature("circuit_dnf_rate", "Context", PRE,
            "Prior retirement share here; a circuit that eats cars widens every outcome."),

    # ----------------------------------------------------------- driver form
    Feature("driver_races_started", "Driver form", PRE,
            "Experience, and the denominator that says how much the other driver features are worth.",
            nullable=False),
    Feature("driver_finish_pos_mean_5", "Driver form", PRE,
            "Recent finishing position is the single most direct read on current pace."),
    Feature("driver_points_rate_5", "Driver form", PRE,
            "Points weight the sharp end, where finishing position compresses."),
    Feature("driver_dnf_rate_10", "Driver form", PRE,
            "Feeds the DNF target directly and discounts the others."),
    Feature("driver_standing_position", "Driver form", PRE,
            "Season-long standing, which survives one bad weekend better than a 5-race window."),
    Feature("driver_standing_points", "Driver form", PRE,
            "The standing position alone hides whether the gap is one point or a hundred."),

    # ------------------------------------------------------------- team form
    Feature("team_finish_pos_mean_5", "Team form", PRE,
            "The car sets the range a driver can finish in; keyed on team_entity_id, not constructorId."),
    Feature("team_points_rate_5", "Team form", PRE,
            "Team scoring rate separates a quick car from a lucky one."),
    Feature("team_dnf_rate_10", "Team form", PRE,
            "Reliability is a property of the car more than the driver."),
    Feature("team_standing_position", "Team form", PRE,
            "Constructor standing, the season-long version of team pace."),
    Feature("team_standing_points", "Team form", PRE,
            "Same reason as the driver equivalent: position hides the size of the gap."),

    # -------------------------------------------------------- circuit history
    Feature("driver_circuit_races", "Circuit history", PRE,
            "How many prior runnings this driver has here; without it the mean below is unreadable.",
            nullable=False),
    Feature("driver_circuit_finish_mean", "Circuit history", PRE,
            "Some drivers are reliably better at some tracks than their general form implies."),
    Feature("team_circuit_races", "Circuit history", PRE,
            "The denominator for the team's circuit mean.", nullable=False),
    Feature("team_circuit_finish_mean", "Circuit history", PRE,
            "Car characteristics suit some circuits; this is the cheapest read on that."),

    # --------------------------------------------------------- practice pace
    Feature("practice_laps", "Practice", POST,
            "Running completed: a driver who lost Friday is less predictable, and it gates the pace features.",
            nullable=False),
    Feature("practice_best_lap_gap_ms", "Practice", POST,
            "Best practice lap against the session best: single-lap pace before qualifying confirms it."),
    Feature("practice_long_run_pace_gap_ms", "Practice", POST,
            "Median green-flag long-run lap against the field: the closest thing to race pace we can see."),
    Feature("practice_long_run_laps", "Practice", POST,
            "How much long-run evidence exists behind the number above.", nullable=False),

    # ------------------------------------------------------------ qualifying
    Feature("quali_position", "Qualifying", POST,
            "Where the driver actually qualified — the strongest single predictor of finishing position.",
            nullable=False),
    Feature("quali_gap_to_pole_ms", "Qualifying", POST,
            "Position is ordinal; the gap says whether second is alongside or half a second adrift."),
    Feature("quali_teammate_gap_ms", "Qualifying", POST,
            "Same car, same day: the cleanest available separation of driver from machine."),
    Feature("quali_reached_q3", "Qualifying", POST,
            "A hard threshold the raw position blurs across a grid of twenty.", nullable=False),

    # --------------------------------------------------------- relative form
    Feature("driver_vs_teammate_finish_mean_5", "Relative form", PRE,
            "Absolute form conflates driver and car; the same car on the same day is the control."),
    Feature("driver_vs_team_points_share_5", "Relative form", PRE,
            "Which half of the garage is scoring, on a scale that survives a change of car."),
    Feature("team_finish_pos_trend_5", "Relative form", PRE,
            "Slope, not level: whether the car is improving or falling back, which upgrades and a new reg era decide."),
    # ----------------------------------------------------- tyre (2019 onward)
    Feature("practice_compounds_run", "Tyre", POST,
            "How much of the allocation was explored; null before 2019, where names are absolute."),
    Feature("practice_softest_long_run_gap_ms", "Tyre", POST,
            "Long-run pace on the softest compound run, comparable only under the relative scheme."),
)

# Considered and rejected, so the same idea is not re-proposed:
#
# circuit_grid_to_finish_correlation -- corr(grid, finish) in prior runnings at
#   the circuit. Measured |r| = 0.958 against circuit_overtaking_difficulty on
#   the full frame. It is the same quantity seen from the other side: where the
#   grid predicts the finish, mean position change is small. Two collinear
#   columns is noise, not information, so only the mean-absolute version stays.
#
# grid_position -- knowable before lights out, but there is no penalty feed, so
#   it could only be trained on and not served. See ENRICHMENT_REPORT.md.

FEATURE_NAMES: tuple[str, ...] = tuple(f.name for f in FEATURES)
KEYS: tuple[str, ...] = ("raceId", "driverId", "snapshot")


def features_for(snapshot: str) -> tuple[str, ...]:
    """Columns available at a snapshot. Pre-weekend is a strict subset."""
    if snapshot == PRE:
        return tuple(f.name for f in FEATURES if f.snapshot == PRE)
    return FEATURE_NAMES


# ---------------------------------------------------------------------- data
def _rd(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, keep_default_na=False, na_values=[r"\N", ""], low_memory=False)


def load_tables() -> dict[str, pd.DataFrame]:
    """Every table the builder reads, loaded once.

    Returned rather than held in module state so a test can hand back a
    truncated copy and prove the builder never looked past its cut.
    """
    # The whole history, not just the FastF1 window. Form, circuit history and
    # standings come from the Ergast schema, which runs back to 1950 at the
    # same quality; clipping them to 2018 would have left every 2018 race with
    # no circuit history at all for no reason. Only the features that read
    # FastF1 are bounded by what FastF1 covers.
    races = _rd(PROCESSED / "races.csv").copy()
    # One monotonic key for "strictly before". Dates carry timezones and
    # rescheduled rounds; (year, round) does not.
    races["order"] = races["year"] * 100 + races["round"]

    laps = pd.concat(
        [_rd(p) for p in sorted((ENRICHED / "laps").glob("*.csv"))], ignore_index=True
    ) if (ENRICHED / "laps").is_dir() else pd.DataFrame()

    return {
        "races": races,
        "results": _rd(PROCESSED / "results.csv"),
        "qualifying": _rd(PROCESSED / "qualifying.csv"),
        "driver_standings": _rd(PROCESSED / "driver_standings.csv"),
        "constructor_standings": _rd(PROCESSED / "constructor_standings.csv"),
        "laps": laps,
    }


def _is_dnf(position_text: pd.Series) -> pd.Series:
    """Retired, as Ergast encodes it.

    Not 'status says Retired': twenty rows from 2018 onward carry a retirement
    status and still hold a classified position, because the car covered enough
    of the distance. positionText is the classification, which is what a DNF
    target means.
    """
    return position_text.astype(str) == "R"


def _quali_ms(df: pd.DataFrame) -> pd.Series:
    """Best of Q1/Q2/Q3 in milliseconds."""
    from transform import parse_duration_ms

    cols = [df[c].map(lambda v: parse_duration_ms(v) if isinstance(v, str) else None)
            for c in ("q1", "q2", "q3")]
    return pd.concat(cols, axis=1).min(axis=1, skipna=True)


def _prior(tables: dict[str, pd.DataFrame], order: int) -> pd.DataFrame:
    """Race results strictly before `order`, with year/round/circuit attached."""
    races = tables["races"]
    earlier = races[races["order"] < order]
    res = tables["results"].merge(
        earlier[["raceId", "year", "round", "circuitId", "order", "name"]], on="raceId"
    )
    res = res.sort_values("order")
    res["is_dnf"] = _is_dnf(res["positionText"])
    return res


def entrants(tables: dict[str, pd.DataFrame], race: pd.Series, snapshot: str) -> pd.DataFrame:
    """Who is in the field, without reading the race that is being predicted.

    Post-qualifying the answer is the qualifying classification. Pre-weekend
    there is nothing from this weekend to read, so it is the field that started
    the most recent completed race — which is what anyone predicting on a
    Tuesday would use, and is available for a race that has not run.
    """
    if snapshot == POST:
        q = tables["qualifying"]
        got = q[q["raceId"] == race["raceId"]][["driverId", "constructorId", "team_entity_id"]]
        if len(got):
            return got.drop_duplicates("driverId").reset_index(drop=True)

    prior = _prior(tables, int(race["order"]))
    if prior.empty:
        return pd.DataFrame(columns=["driverId", "constructorId", "team_entity_id"])
    last = prior[prior["order"] == prior["order"].max()]
    started = last[last["positionText"].astype(str) != "W"]
    return (started[["driverId", "constructorId", "team_entity_id"]]
            .drop_duplicates("driverId").reset_index(drop=True))


_ROLLING_COLS = ("finish_mean", "points_rate", "dnf_rate", "n_seen")


def _rolling(prior: pd.DataFrame, key: str, n: int) -> pd.DataFrame:
    """Mean finish, points rate and DNF rate over each entity's last n races.

    Returns an empty but correctly shaped frame when there is no history at
    all -- the first race of the dataset, or a driver's debut. The merge then
    leaves nulls, which is the honest answer, rather than raising.
    """
    if prior.empty:
        return pd.DataFrame(columns=[key, *_ROLLING_COLS])
    out = []
    for ident, g in prior.groupby(key, sort=False):
        g = g.sort_values("order")
        tail = g.tail(n)
        pos = pd.to_numeric(tail["positionOrder"], errors="coerce")
        finished = tail[~tail["is_dnf"]]
        out.append({
            key: ident,
            "finish_mean": pd.to_numeric(finished["positionOrder"], errors="coerce").mean(),
            "points_rate": pd.to_numeric(tail["points"], errors="coerce").mean(),
            "dnf_rate": float(tail["is_dnf"].mean()) if len(tail) else None,
            "n_seen": int(len(g)),
            "_unused_pos": pos.mean(),
        })
    return pd.DataFrame(out)


def _teammate_finish(prior: pd.DataFrame) -> pd.DataFrame:
    """Each classified finish beside the mean of that driver's teammates'.

    Restricted to races where both sides were classified: a comparison against
    a teammate who retired on lap 1 measures the retirement, not the driver.
    """
    fin = prior[~prior["is_dnf"]].copy()
    fin["pos"] = pd.to_numeric(fin["positionOrder"], errors="coerce")
    fin = fin[fin["pos"].notna()]
    g = fin.groupby(["raceId", "team_entity_id"])["pos"]
    fin["_sum"], fin["_n"] = g.transform("sum"), g.transform("count")
    fin = fin[fin["_n"] > 1]
    fin["mate_pos"] = (fin["_sum"] - fin["pos"]) / (fin["_n"] - 1)
    return fin[["raceId", "driverId", "order", "pos", "mate_pos", "team_entity_id", "points"]]


def _relative_form(prior: pd.DataFrame, n: int) -> pd.DataFrame:
    """Driver against the other side of the same garage, over the last n races."""
    cols = ["driverId", "driver_vs_teammate_finish_mean_5", "driver_vs_team_points_share_5"]
    if prior.empty:
        return pd.DataFrame(columns=cols)
    pairs = _teammate_finish(prior)
    rows = []
    for did, g in pairs.groupby("driverId", sort=False):
        tail = g.sort_values("order").tail(n)
        rows.append({"driverId": did,
                     "driver_vs_teammate_finish_mean_5": float((tail["pos"] - tail["mate_pos"]).mean())
                     if len(tail) else None})
    out = pd.DataFrame(rows) if rows else pd.DataFrame(columns=["driverId", cols[1]])

    # Points share uses every race, retirement included: a driver who retires
    # scores nothing, and that is a fact about the season rather than noise.
    pts = prior[["raceId", "driverId", "team_entity_id", "order"]].copy()
    pts["points"] = pd.to_numeric(prior["points"], errors="coerce").fillna(0.0)
    # Team total per race, joined on rather than recomputed per driver: the
    # nested version was quadratic and dominated the test suite's runtime.
    team_race = pts.groupby(["raceId", "team_entity_id"])["points"].sum().rename("team_points")
    pts = pts.merge(team_race, on=["raceId", "team_entity_id"], how="left")
    tail = (pts.sort_values("order").groupby("driverId", sort=False).tail(n)
            .groupby("driverId")[["points", "team_points"]].sum().reset_index())
    tail["driver_vs_team_points_share_5"] = (
        tail["points"] / tail["team_points"]).where(tail["team_points"] > 0)
    sh = tail[["driverId", "driver_vs_team_points_share_5"]]
    return out.merge(sh, on="driverId", how="outer") if len(out) else sh


def _team_trend(prior: pd.DataFrame, n: int) -> pd.DataFrame:
    """Slope of the team's mean finishing position over its last n races.

    Negative means improving, because a smaller position is a better one.
    """
    if prior.empty:
        return pd.DataFrame(columns=["team_entity_id", "team_finish_pos_trend_5"])
    fin = prior[~prior["is_dnf"]].copy()
    fin["pos"] = pd.to_numeric(fin["positionOrder"], errors="coerce")
    per_race = fin.groupby(["team_entity_id", "order"])["pos"].mean().reset_index()
    rows = []
    for team, g in per_race.groupby("team_entity_id", sort=False):
        tail = g.sort_values("order").tail(n)
        if len(tail) < 3:          # two points make a line through noise
            rows.append({"team_entity_id": team, "team_finish_pos_trend_5": None})
            continue
        x = range(len(tail))
        slope = pd.Series(list(x)).corr(tail["pos"].reset_index(drop=True))
        sd_x, sd_y = pd.Series(list(x)).std(), tail["pos"].std()
        rows.append({"team_entity_id": team,
                     "team_finish_pos_trend_5": float(slope * sd_y / sd_x)
                     if sd_x and sd_y and pd.notna(slope) else 0.0})
    return pd.DataFrame(rows)


def _standing_before(tables: dict[str, pd.DataFrame], race: pd.Series, table: str,
                     key: str) -> pd.DataFrame:
    """Championship standing entering the race: the standing after the last
    race before it. For round 1 of a season there is no such row, which is a
    real absence and stays null."""
    races = tables["races"]
    same_season = races[(races["year"] == race["year"]) & (races["order"] < race["order"])]
    if same_season.empty:
        return pd.DataFrame(columns=[key, "standing_position", "standing_points"])
    last_id = int(same_season.sort_values("order").iloc[-1]["raceId"])
    st = tables[table]
    got = st[st["raceId"] == last_id]
    return pd.DataFrame({
        key: got[key],
        "standing_position": pd.to_numeric(got["position"], errors="coerce"),
        "standing_points": pd.to_numeric(got["points"], errors="coerce"),
    })


# ------------------------------------------------------------------ practice
LONG_RUN_MIN_LAPS = 5
# Reserve and FP1-only runners are out of team practice pace by default. Part D
# flips this to test whether the default is right; see MODEL_REPORT.md.
INCLUDE_RESERVES_IN_PRACTICE = False
_SOFTEST_FIRST = ("SOFT", "MEDIUM", "HARD")


def practice_frame(tables: dict[str, pd.DataFrame], race: pd.Series) -> pd.DataFrame:
    """Per-driver practice pace for one race weekend.

    Reserve and FP1-only runners are dropped by default: their laps are on a
    different programme and would drag a team's practice pace toward whatever
    the young driver was asked to do. Part D tests whether that is right.
    """
    laps = tables["laps"]
    empty = pd.DataFrame(columns=["driverId", "practice_laps", "practice_best_lap_gap_ms",
                                  "practice_long_run_pace_gap_ms", "practice_long_run_laps",
                                  "practice_compounds_run", "practice_softest_long_run_gap_ms"])
    if laps.empty or (race["year"], race["name"]) in LAP_UNUSABLE:
        return empty

    f = laps[(laps["raceId"] == race["raceId"])
             & laps["session"].isin(["Practice 1", "Practice 2", "Practice 3"])
             & laps["driverId"].notna()].copy()
    if f.empty:
        return empty
    f["driverId"] = f["driverId"].astype(int)
    if "is_race_driver" in f.columns and not INCLUDE_RESERVES_IN_PRACTICE:
        f = f[f["is_race_driver"].astype(str).str.lower().isin(["true", "1"])]
    if f.empty:
        return empty

    f["LapTimeMs"] = pd.to_numeric(f["LapTimeMs"], errors="coerce")
    accurate = f["IsAccurate"].astype(str).str.lower().isin(["true", "1"])
    green = pd.to_numeric(f["TrackStatus"], errors="coerce") == 1
    clean = f[accurate & green & f["LapTimeMs"].notna()]

    rows = []
    for did, g in f.groupby("driverId", sort=False):
        c = clean[clean["driverId"] == did]
        best = c["LapTimeMs"].min() if len(c) else None
        stints = c.groupby(["session", "Stint"])["LapTimeMs"]
        long_runs = [s for _, s in stints if len(s) >= LONG_RUN_MIN_LAPS]
        pace = pd.concat(long_runs).median() if long_runs else None
        n_long = int(sum(len(s) for s in long_runs))
        rows.append({"driverId": int(did), "practice_laps": int(len(g)),
                     "_best": best, "_pace": pace, "practice_long_run_laps": n_long})
    out = pd.DataFrame(rows)
    if out.empty:
        return empty

    # Relative to the field, not absolute: circuits differ by twenty seconds a lap.
    out["practice_best_lap_gap_ms"] = out["_best"] - out["_best"].min()
    out["practice_long_run_pace_gap_ms"] = out["_pace"] - out["_pace"].min()

    # Compound features exist only under the relative naming scheme.
    if int(race["year"]) >= FIRST_RELATIVE_COMPOUND_SEASON and "Compound" in clean.columns:
        dry = clean[clean["Compound"].isin(_SOFTEST_FIRST)]
        n_comp = dry.groupby("driverId")["Compound"].nunique().rename("practice_compounds_run")
        softest = []
        for did, g in dry.groupby("driverId", sort=False):
            got = next((c for c in _SOFTEST_FIRST if (g["Compound"] == c).any()), None)
            sub = g[g["Compound"] == got] if got else g.iloc[0:0]
            runs = [s for _, s in sub.groupby(["session", "Stint"])["LapTimeMs"]
                    if len(s) >= LONG_RUN_MIN_LAPS]
            softest.append({"driverId": int(did),
                            "_soft": pd.concat(runs).median() if runs else None})
        s = pd.DataFrame(softest)
        out = out.merge(n_comp.reset_index(), on="driverId", how="left")
        if len(s):
            out = out.merge(s, on="driverId", how="left")
            out["practice_softest_long_run_gap_ms"] = out["_soft"] - out["_soft"].min()
    for col in ("practice_compounds_run", "practice_softest_long_run_gap_ms"):
        if col not in out.columns:
            out[col] = pd.NA
    return out.drop(columns=[c for c in ("_best", "_pace", "_soft") if c in out.columns])


# ---------------------------------------------------------------- qualifying
def qualifying_frame(tables: dict[str, pd.DataFrame], race: pd.Series) -> pd.DataFrame:
    cols = ["driverId", "quali_position", "quali_gap_to_pole_ms",
            "quali_teammate_gap_ms", "quali_reached_q3"]
    q = tables["qualifying"]
    got = q[q["raceId"] == race["raceId"]].copy()
    if got.empty:
        return pd.DataFrame(columns=cols)
    got["best_ms"] = _quali_ms(got)
    got["quali_position"] = pd.to_numeric(got["position"], errors="coerce")
    got["quali_gap_to_pole_ms"] = got["best_ms"] - got["best_ms"].min()
    got["quali_reached_q3"] = got["q3"].notna().astype(int)

    gaps = []
    for _, g in got.groupby("team_entity_id", sort=False):
        for _, row in g.iterrows():
            mate = g[g["driverId"] != row["driverId"]]["best_ms"]
            gaps.append({"driverId": row["driverId"],
                         "quali_teammate_gap_ms": (row["best_ms"] - mate.min())
                         if len(mate) and pd.notna(row["best_ms"]) else None})
    return got[cols[:2] + cols[2:3] + cols[4:]].merge(pd.DataFrame(gaps), on="driverId", how="left")[cols]


# ------------------------------------------------------------------- builder
def build_race(tables: dict[str, pd.DataFrame], race: pd.Series, snapshot: str) -> pd.DataFrame:
    """Feature rows for one race at one snapshot."""
    field = entrants(tables, race, snapshot)
    if field.empty:
        return pd.DataFrame(columns=list(KEYS) + list(FEATURE_NAMES))
    df = field.copy()
    df["raceId"] = int(race["raceId"])
    df["snapshot"] = snapshot

    prior = _prior(tables, int(race["order"]))

    # ---- context
    df["round_index"] = int(race["round"])
    era_start = tables["races"].loc[tables["races"]["regs_era"] == race["regs_era"], "year"].min()
    df["seasons_into_regs_era"] = int(race["year"]) - int(era_start)
    here = prior[prior["circuitId"] == race["circuitId"]]
    df["circuit_prior_races"] = int(here["raceId"].nunique())
    if len(here):
        grid = pd.to_numeric(here["grid"], errors="coerce")
        fin = pd.to_numeric(here["positionOrder"], errors="coerce")
        moved = (grid - fin).abs()[grid > 0]
        df["circuit_overtaking_difficulty"] = float(moved.mean()) if len(moved) else None
        df["circuit_dnf_rate"] = float(here["is_dnf"].mean())
    else:
        df["circuit_overtaking_difficulty"] = None
        df["circuit_dnf_rate"] = None

    # ---- driver and team form
    for key, prefix, n_short, n_long in (("driverId", "driver", 5, 10),
                                         ("team_entity_id", "team", 5, 10)):
        short = _rolling(prior, key, n_short)[[key, "finish_mean", "points_rate", "n_seen"]]
        long = _rolling(prior, key, n_long)[[key, "dnf_rate"]]
        short = short.rename(columns={"finish_mean": f"{prefix}_finish_pos_mean_5",
                                      "points_rate": f"{prefix}_points_rate_5",
                                      "n_seen": f"{prefix}_races_started"})
        long = long.rename(columns={"dnf_rate": f"{prefix}_dnf_rate_10"})
        df = df.merge(short, on=key, how="left").merge(long, on=key, how="left")
    df["driver_races_started"] = pd.to_numeric(df["driver_races_started"], errors="coerce").fillna(0).astype(int)
    df = df.drop(columns=["team_races_started"], errors="ignore")

    # ---- driver against the rest of their own garage
    df = df.merge(_relative_form(prior, 5), on="driverId", how="left")
    df = df.merge(_team_trend(prior, 5), on="team_entity_id", how="left")

    # ---- standings entering the race
    for table, key, prefix in (("driver_standings", "driverId", "driver"),
                               ("constructor_standings", "constructorId", "team")):
        st = _standing_before(tables, race, table, key)
        st = st.rename(columns={"standing_position": f"{prefix}_standing_position",
                                "standing_points": f"{prefix}_standing_points"})
        df = df.merge(st, on=key, how="left")

    # ---- circuit history
    for key, prefix in (("driverId", "driver"), ("team_entity_id", "team")):
        if len(here):
            g = here.groupby(key)
            hist = pd.DataFrame({
                f"{prefix}_circuit_races": g.size(),
                f"{prefix}_circuit_finish_mean": g.apply(
                    lambda x: pd.to_numeric(x.loc[~x["is_dnf"], "positionOrder"],
                                            errors="coerce").mean(), include_groups=False),
            }).reset_index()
            df = df.merge(hist, on=key, how="left")
        else:
            df[f"{prefix}_circuit_races"] = 0
            df[f"{prefix}_circuit_finish_mean"] = None
        df[f"{prefix}_circuit_races"] = pd.to_numeric(
            df[f"{prefix}_circuit_races"], errors="coerce").fillna(0).astype(int)

    # ---- this weekend, only once qualifying has happened
    if snapshot == POST:
        df = df.merge(practice_frame(tables, race), on="driverId", how="left")
        df = df.merge(qualifying_frame(tables, race), on="driverId", how="left")
        df["practice_laps"] = pd.to_numeric(df["practice_laps"], errors="coerce").fillna(0).astype(int)
        df["practice_long_run_laps"] = pd.to_numeric(df["practice_long_run_laps"], errors="coerce").fillna(0).astype(int)

    for f in FEATURES:
        if f.name not in df.columns:
            df[f.name] = pd.NA

    cols = list(features_for(snapshot))
    out = df[list(KEYS) + cols].copy()
    # Every feature is numeric. Coercing here keeps dtypes stable whether a
    # column came back full, partly null, or entirely absent for this race --
    # which is what makes two builds comparable cell by cell.
    for c in cols:
        out[c] = pd.to_numeric(out[c], errors="coerce").astype("Float64")
    return out.sort_values("driverId").reset_index(drop=True)


def build(race_ids: list[int] | None = None, snapshot: str = POST,
          tables: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    """Feature frame for the given races. Deterministic and order-independent."""
    tables = tables if tables is not None else load_tables()
    races = tables["races"]
    if race_ids is not None:
        races = races[races["raceId"].isin(race_ids)]
    else:
        # Rows are only produced where the enrichment exists, even though the
        # history feeding them reaches further back.
        races = races[races["year"] >= FIRST_SEASON]
    frames = [build_race(tables, r, snapshot) for _, r in races.sort_values("order").iterrows()]
    frames = [f for f in frames if len(f)]
    if not frames:
        return pd.DataFrame(columns=list(KEYS) + list(features_for(snapshot)))
    return pd.concat(frames, ignore_index=True)
