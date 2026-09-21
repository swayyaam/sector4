"""Scrape formula1.com starting-grid pages to settle `pit_lane_start`.

Jolpica reports the grid slot but not whether a driver actually started from the
pit lane, so for 2025+ that fact has to come from somewhere else. The official
starting-grid page carries it as a free-text note ("X required to start from
pit lane after ..."), so we parse the grid table and the note together.

Decision rule, deliberately conservative:
  * a driver named in a sentence mentioning "pit lane"  -> True
  * page parsed, grid found, no pit-lane sentence       -> False for everyone
  * page missing, unparseable, or a pit-lane sentence we
    cannot attribute to a specific driver               -> None (left null)

Raw HTML is cached under data/raw/f1_grids/ so reruns cost nothing.
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "raw" / "f1_grids"
OUT = ROOT / "data" / "processed" / "pit_lane_starts.csv"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

RACES: dict[int, list[tuple[int, int, str]]] = {
    2024: [(21, 1249, "brazil")],                    # only the disputed one
    2025: [(1, 1254, "australia"), (2, 1255, "china"), (3, 1256, "japan"), (4, 1257, "bahrain"),
           (5, 1258, "saudi-arabia"), (6, 1259, "miami"), (7, 1260, "emilia-romagna"),
           (8, 1261, "monaco"), (9, 1262, "spain"), (10, 1263, "canada"), (11, 1264, "austria"),
           (12, 1277, "great-britain"), (13, 1265, "belgium"), (14, 1266, "hungary"),
           (15, 1267, "netherlands"), (16, 1268, "italy"), (17, 1269, "azerbaijan"),
           (18, 1270, "singapore"), (19, 1271, "united-states"), (20, 1272, "mexico"),
           (21, 1273, "brazil"), (22, 1274, "las-vegas"), (23, 1275, "qatar"),
           (24, 1276, "abu-dhabi")],
    2026: [(1, 1279, "australia"), (2, 1280, "china"), (3, 1281, "japan"), (4, 1284, "miami"),
           (5, 1285, "canada"), (6, 1286, "monaco"), (7, 1287, "barcelona-catalunya"),
           (8, 1288, "austria"), (9, 1289, "great-britain"), (10, 1290, "belgium"),
           (11, 1291, "hungary"), (12, 1292, "netherlands"), (13, 1293, "italy"),
           (14, 1294, "spain")],
}

ROW_RE = re.compile(r"(?<!\d)(\d{1,2})\s+(\d{1,2})\s+([A-Za-zÀ-ÿ'’\-\.]+(?:\s+[A-Za-zÀ-ÿ'’\-\.]+)*?)\s+([A-Z]{3})\s+")


def fetch(year: int, rid: int, slug: str) -> str | None:
    CACHE.mkdir(parents=True, exist_ok=True)
    cp = CACHE / f"{year}_{rid}_{slug}.html"
    if cp.exists():
        return cp.read_text(encoding="utf-8", errors="ignore")
    url = f"https://www.formula1.com/en/results/{year}/races/{rid}/{slug}/starting-grid"
    for attempt in range(4):
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        except requests.RequestException as e:
            print(f"    network error: {e}")
        else:
            if r.status_code == 200:
                cp.write_text(r.text, encoding="utf-8")
                return r.text
            print(f"    HTTP {r.status_code} for {url}")
            if r.status_code == 404:
                return None
        time.sleep(2 * (attempt + 1))
    return None


def to_text(raw: str) -> str:
    t = re.sub(r"<script.*?</script>", " ", raw, flags=re.S)
    t = re.sub(r"<style.*?</style>", " ", t, flags=re.S)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"\s+", " ", t)


def parse(text: str) -> tuple[list[dict], list[str], str]:
    """Return (grid rows, pit-lane sentences, the note block)."""
    grid, seen = [], set()
    for m in ROW_RE.finditer(text):
        pos, num, name, code = int(m.group(1)), int(m.group(2)), m.group(3).strip(), m.group(4)
        if not 1 <= pos <= 24 or code in seen:
            continue
        seen.add(code)
        grid.append({"grid": pos, "number": num, "name": name, "code": code})
    note = ""
    nm = re.search(r"\bNote\s*[-–:]\s*(.{0,600}?)(?:OUR PARTNERS|Download the Official)", text, re.S)
    if nm:
        note = nm.group(1).strip()
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", note) if "pit lane" in s.lower()]
    return grid, sentences, note


def main() -> int:
    rows, problems = [], []
    for year, races in RACES.items():
        for rnd, rid, slug in races:
            raw = fetch(year, rid, slug)
            if raw is None:
                problems.append((year, rnd, slug, "page unavailable"))
                print(f"  {year} R{rnd:<2} {slug:<22} PAGE UNAVAILABLE")
                continue
            text = to_text(raw)
            grid, sentences, note = parse(text)
            if len(grid) < 15:
                problems.append((year, rnd, slug, f"parsed only {len(grid)} grid rows"))
                print(f"  {year} R{rnd:<2} {slug:<22} PARSE FAILED ({len(grid)} rows)")
                continue
            pit: dict[str, bool] = {}
            unattributed = []
            # Drivers named anywhere in the note block. Used only as a fallback
            # when a pit-lane sentence carries no name of its own, e.g. Miami
            # 2026: "Hadjar granted permission to race after being disqualified
            # from Qualifying. Required to start from the pit lane after ..."
            named_in_note = [g["code"] for g in grid
                             if re.search(rf"\b{re.escape(g['name'].split()[-1])}\b", note, re.I)]
            for s in sentences:
                hit = [g["code"] for g in grid
                       if re.search(rf"\b{re.escape(g['name'].split()[-1])}\b", s, re.I)]
                if hit:
                    for c in hit:
                        pit[c] = True
                elif len(named_in_note) == 1:
                    pit[named_in_note[0]] = True
                    print(f"      (attributed an unnamed pit-lane sentence to {named_in_note[0]}, "
                          f"the only driver named in the note)")
                else:
                    unattributed.append(s)
            for g in grid:
                val = pit.get(g["code"], None if unattributed else False)
                rows.append({"year": year, "round": rnd, "f1_race_id": rid, "slug": slug,
                             "grid": g["grid"], "code": g["code"], "name": g["name"],
                             "pit_lane_start": val})
            flag = f"  PIT LANE: {sorted(pit)}" if pit else ""
            if unattributed:
                flag += f"  UNATTRIBUTED: {unattributed}"
                problems.append((year, rnd, slug, f"unattributed pit-lane sentence: {unattributed}"))
            print(f"  {year} R{rnd:<2} {slug:<22} {len(grid)} rows{flag}")
            time.sleep(0.4)

    import csv
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["year", "round", "f1_race_id", "slug", "grid", "code",
                                          "name", "pit_lane_start"])
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote {len(rows)} grid rows -> {OUT}")
    t = sum(1 for r in rows if r["pit_lane_start"] is True)
    f_ = sum(1 for r in rows if r["pit_lane_start"] is False)
    n = sum(1 for r in rows if r["pit_lane_start"] is None)
    print(f"  pit_lane_start: {t} True, {f_} False, {n} still null")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print("   ", p)
    (CACHE / "problems.json").write_text(json.dumps(problems, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
