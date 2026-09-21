"""Record / verify checksums of every file in data/processed/.

Phase 1 promised deterministic transforms: the same inputs must produce
byte-identical outputs. That promise is what lets us change the environment
(e.g. the pandas major version FastF1 requires) and *prove* the verified
dataset did not move, rather than assuming it.

    python src/checksum_processed.py record    # write baseline + snapshot the files
    python src/checksum_processed.py verify    # sha256 comparison
    python src/checksum_processed.py classify  # value-level diff vs the snapshot

`classify` answers the question a checksum cannot: when the bytes differ, is it
only how values are *rendered* (pandas 3 changed the default string dtype and
float formatting), or did an actual value change? A value-level difference
would mean the pandas version alters the Phase 1 logic, not just its output
formatting, which is worth knowing regardless of which environment we keep.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
BASELINE = ROOT / "data" / "checksums_v0.1-data.json"
SNAPSHOT = ROOT / "data" / "processed_v0.1_snapshot"


def digest(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot() -> dict[str, dict]:
    out = {}
    for p in sorted(DATA.rglob("*.csv")):
        rel = p.relative_to(DATA).as_posix()
        out[rel] = {"sha256": digest(p), "bytes": p.stat().st_size}
    return out


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "verify"
    cur = snapshot()
    if mode == "record":
        BASELINE.write_text(json.dumps(cur, indent=2, sort_keys=True))
        if SNAPSHOT.exists():
            shutil.rmtree(SNAPSHOT)
        shutil.copytree(DATA, SNAPSHOT)
        total = sum(v["bytes"] for v in cur.values())
        print(f"recorded {len(cur)} files ({total/1e6:.1f} MB) -> {BASELINE}")
        print(f"snapshot copied -> {SNAPSHOT} (gitignored; enables a value-level diff)")
        return 0

    if mode == "classify":
        return classify()

    if not BASELINE.exists():
        print(f"no baseline at {BASELINE}; run `record` first")
        return 2
    old = json.loads(BASELINE.read_text())
    missing = sorted(set(old) - set(cur))
    added = sorted(set(cur) - set(old))
    changed = sorted(f for f in set(old) & set(cur) if old[f]["sha256"] != cur[f]["sha256"])
    print(f"baseline: {len(old)} files   current: {len(cur)} files")
    for label, items in [("MISSING", missing), ("ADDED", added), ("CHANGED", changed)]:
        if items:
            print(f"  {label} ({len(items)}):")
            for f in items[:20]:
                if label == "CHANGED":
                    print(f"    {f}  {old[f]['bytes']}B -> {cur[f]['bytes']}B")
                else:
                    print(f"    {f}")
    if not (missing or added or changed):
        print("IDENTICAL — every file matches the baseline byte for byte")
        return 0
    print(f"\nDIFFERENT: {len(missing)} missing, {len(added)} added, {len(changed)} changed")
    return 1


def _read(p: Path):
    import pandas as pd
    return pd.read_csv(p, keep_default_na=False, na_values=[r"\N", ""], low_memory=False)


def _cells_equal(a, b) -> bool:
    import pandas as pd
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a) == str(b)


def classify() -> int:
    """For every file whose bytes changed, say whether any *value* changed."""
    import pandas as pd
    if not SNAPSHOT.exists():
        print(f"no snapshot at {SNAPSHOT}; run `record` before changing the environment")
        return 2
    old_sums = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    cur = snapshot()
    changed = sorted(f for f in set(old_sums) & set(cur) if old_sums[f]["sha256"] != cur[f]["sha256"])
    if not changed:
        print("no files changed — nothing to classify")
        return 0

    formatting_only, value_diffs, structural = [], [], []
    for rel in changed:
        a_path, b_path = SNAPSHOT / rel, DATA / rel
        try:
            a, b = _read(a_path), _read(b_path)
        except Exception as e:
            structural.append((rel, f"unreadable: {e}"))
            continue
        if list(a.columns) != list(b.columns):
            structural.append((rel, f"columns differ: {set(a.columns) ^ set(b.columns)}"))
            continue
        if len(a) != len(b):
            structural.append((rel, f"row count {len(a)} -> {len(b)}"))
            continue
        diffs = []
        for col in a.columns:
            av, bv = a[col].to_numpy(), b[col].to_numpy()
            for i in range(len(av)):
                if not _cells_equal(av[i], bv[i]):
                    diffs.append((i, col, av[i], bv[i]))
                    if len(diffs) >= 20:
                        break
            if len(diffs) >= 20:
                break
        if diffs:
            value_diffs.append((rel, diffs))
        else:
            formatting_only.append(rel)

    print("=" * 78)
    print("VALUE-LEVEL CLASSIFICATION OF CHECKSUM DIFFERENCES")
    print("=" * 78)
    print(f"  files with changed bytes : {len(changed)}")
    print(f"  formatting only          : {len(formatting_only)}")
    print(f"  actual value differences : {len(value_diffs)}")
    print(f"  structural differences   : {len(structural)}")
    if formatting_only:
        print("\n  FORMATTING ONLY (every parsed value identical):")
        for rel in formatting_only:
            a_lines = (SNAPSHOT / rel).read_text().splitlines()
            b_lines = (DATA / rel).read_text().splitlines()
            ex = next((f"      line {i+1}:\n        was: {x[:150]}\n        now: {y[:150]}"
                       for i, (x, y) in enumerate(zip(a_lines, b_lines)) if x != y), "      (no line differs?)")
            print(f"    {rel}")
            print(ex)
    if value_diffs:
        print("\n  !! ACTUAL VALUE DIFFERENCES — the pandas version changes Phase 1 logic:")
        for rel, diffs in value_diffs:
            print(f"    {rel}: {len(diffs)}+ differing cells")
            for i, col, av, bv in diffs[:8]:
                print(f"      row {i} col {col}: {av!r} -> {bv!r}")
    if structural:
        print("\n  !! STRUCTURAL DIFFERENCES:")
        for rel, why in structural:
            print(f"    {rel}: {why}")
    print()
    if value_diffs or structural:
        print("VERDICT: not formatting — values or structure changed.")
        return 1
    print("VERDICT: formatting only — every parsed value is identical.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
