/**
 * Project circuit outlines into inline SVG paths.
 *
 * Source: https://github.com/bacinger/f1-circuits (MIT, (c) 2019-2025 Tomislav
 * Bacinger). Licence checked before use; the notice is recorded in
 * image-credits.json and shown on /credits/.
 *
 * Rendered inline rather than as an image file: each path is a few hundred
 * bytes, so inlining avoids a request and lets the outline take its colour
 * from the design tokens.
 */
import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const MOCK = join(HERE, "..", "src", "data", "mock");
const SRC = "https://raw.githubusercontent.com/bacinger/f1-circuits/master/f1-circuits.geojson";

const VIEW = 1000;
const PAD = 40;

/** Equirectangular projection, scaled to fit a square viewBox. Fine at this size. */
function toPath(coords) {
  const lons = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  // Longitude degrees shrink with latitude; without this correction a circuit
  // far from the equator comes out stretched sideways.
  const k = Math.cos((midLat * Math.PI) / 180);
  const xs = lons.map((l) => l * k);
  const ys = lats.map((l) => -l);
  const [minX, maxX] = [Math.min(...xs), Math.max(...xs)];
  const [minY, maxY] = [Math.min(...ys), Math.max(...ys)];
  const span = Math.max(maxX - minX, maxY - minY) || 1;
  const scale = (VIEW - PAD * 2) / span;
  const offX = (VIEW - (maxX - minX) * scale) / 2;
  const offY = (VIEW - (maxY - minY) * scale) / 2;
  const pt = (i) => [
    ((xs[i] - minX) * scale + offX).toFixed(1),
    ((ys[i] - minY) * scale + offY).toFixed(1),
  ];
  return coords.map((_, i) => `${i === 0 ? "M" : "L"}${pt(i).join(",")}`).join("") + "Z";
}

const geo = JSON.parse(await fetch(SRC).then((r) => r.text()));
const ref = JSON.parse(readFileSync(join(MOCK, "reference.json"), "utf8"));

// Match on locality + country rather than name: the dataset and our own tables
// disagree on names (its "Albert Park Circuit" vs our "Albert Park Grand Prix
// Circuit"), but localities agree.
// Explicit, not fuzzy: our locality and the dataset's disagree for two
// circuits, and a loose match risks drawing the wrong track.
const ALIAS = { montmeló: "barcelona", "monte-carlo": "monaco" };

const byLocality = new Map();
for (const f of geo.features) {
  if (f.geometry?.type !== "LineString") continue;
  byLocality.set(String(f.properties.Location).toLowerCase(), f);
}

let matched = 0;
const unmatched = [];
for (const c of ref.circuits) {
  const key = c.locality.toLowerCase();
  const f =
    byLocality.get(ALIAS[key] ?? key) ??
    byLocality.get(key) ??
    byLocality.get(c.name.toLowerCase()) ??
    [...byLocality.values()].find((x) =>
      String(x.properties.Name).toLowerCase().includes(c.locality.toLowerCase()),
    );
  if (!f) {
    unmatched.push(`${c.circuitRef} (${c.locality})`);
    c.track_path = null;
    c.track_view_box = null;
    c.track_credit_id = null;
    continue;
  }
  c.track_path = toPath(f.geometry.coordinates);
  c.track_view_box = `0 0 ${VIEW} ${VIEW}`;
  c.track_credit_id = "f1-circuits";
  matched++;
}

writeFileSync(join(MOCK, "reference.json"), JSON.stringify(ref, null, 2) + "\n");

const credits = {
  "f1-circuits": {
    kind: "dataset",
    title: "f1-circuits",
    author: "Tomislav Bacinger",
    licence: "MIT",
    licence_url: "https://github.com/bacinger/f1-circuits/blob/master/LICENSE",
    source: "https://github.com/bacinger/f1-circuits",
    notice: "Copyright (c) 2019-2025 Tomislav Bacinger",
    used_for: "Circuit outlines, projected to SVG paths",
  },
};
writeFileSync(join(MOCK, "..", "image-credits.json"), JSON.stringify(credits, null, 2) + "\n");

console.log(`circuit outlines: ${matched}/${ref.circuits.length} matched`);
if (unmatched.length) console.log(`  no geometry for: ${unmatched.join(", ")}`);
console.log(`credits -> src/data/image-credits.json`);
