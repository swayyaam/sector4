"""Record / verify checksums of every file in data/processed/.

Phase 1 promised deterministic transforms: the same inputs must produce
byte-identical outputs. That promise is what lets us change the environment
(e.g. the pandas major version FastF1 requires) and *prove* the verified
dataset did not move, rather than assuming it.

    python src/checksum_processed.py record   # write the baseline
    python src/checksum_processed.py verify   # compare against it
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
BASELINE = ROOT / "data" / "checksums_v0.1-data.json"


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
        total = sum(v["bytes"] for v in cur.values())
        print(f"recorded {len(cur)} files ({total/1e6:.1f} MB) -> {BASELINE}")
        return 0

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


if __name__ == "__main__":
    raise SystemExit(main())
