/**
 * Download the typeface into the repo.
 *
 * Self-hosted rather than linked: a third-party font request is a render-
 * blocking round trip to another origin, and it leaks every visitor's IP to
 * that origin. Inter is SIL OFL, so redistributing it here is fine.
 * Only the latin subset is taken, which is what the site renders.
 */
import { writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, "..", "public", "fonts");
// Satori cannot read woff2, and these never reach the browser, so the build
// copies live outside public/ where nothing can serve them by accident.
const OG_OUT = join(HERE, "..", "src", "assets", "fonts");
const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

const FAMILIES = [{ css: "Inter:wght@400;600;700", name: "inter" }];

mkdirSync(OUT, { recursive: true });

for (const fam of FAMILIES) {
  const url = `https://fonts.googleapis.com/css2?family=${fam.css}&display=swap`;
  const css = await fetch(url, { headers: { "User-Agent": UA } }).then((r) => r.text());

  // Keep only the latin block; the site has no other scripts to render.
  const blocks = css.split("/* ").filter((b) => b.startsWith("latin */"));
  if (!blocks.length) throw new Error(`no latin subset found for ${fam.name}`);

  for (const block of blocks) {
    const weight = /font-weight:\s*(\d+)/.exec(block)?.[1] ?? "400";
    const src = /url\((https:[^)]+\.woff2)\)/.exec(block)?.[1];
    if (!src) continue;
    // Google serves Inter as one variable font for every weight, so the three
    // weight requests return byte-identical files. Store it once.
    const variable = fam.name === "inter";
    const file = variable ? `${fam.name}-var.woff2` : `${fam.name}-${weight}.woff2`;
    const path = join(OUT, file);
    if (existsSync(path)) {
      console.log(`  ${file} already present`);
      continue;
    }
    const buf = Buffer.from(await fetch(src).then((r) => r.arrayBuffer()));
    writeFileSync(path, buf);
    console.log(`  ${file}  ${(buf.length / 1024).toFixed(1)} KB`);
  }
}

// ---------------------------------------------------------------- build only
// The same family again as TrueType, for the Open Graph card renderer.
// Requested without a modern User-Agent, which is what makes Google serve ttf.
mkdirSync(OG_OUT, { recursive: true });

const OG_FACES = [
  { family: "Inter", weight: 400, file: "inter-400.ttf" },
  { family: "Inter", weight: 700, file: "inter-700.ttf" },
];

const ogCss = await fetch("https://fonts.googleapis.com/css2?family=Inter:wght@400;700", {
  headers: { "User-Agent": "Wget/1.21" },
}).then((r) => r.text());

const faces = ogCss.split("@font-face").slice(1);
for (const face of OG_FACES) {
  const path = join(OG_OUT, face.file);
  if (existsSync(path)) {
    console.log(`  ${face.file} already present`);
    continue;
  }
  const block = faces.find(
    (b) =>
      b.includes(`font-family: '${face.family}'`) &&
      new RegExp(`font-weight: ${face.weight}\\b`).test(b),
  );
  const src = block && /url\((https:[^)]+\.ttf)\)/.exec(block)?.[1];
  if (!src) throw new Error(`no ttf for ${face.family} ${face.weight}`);
  const buf = Buffer.from(await fetch(src).then((r) => r.arrayBuffer()));
  writeFileSync(path, buf);
  console.log(`  ${face.file}  ${(buf.length / 1024).toFixed(1)} KB`);
}

console.log(`fonts -> ${OUT}`);
console.log(`og fonts -> ${OG_OUT}`);
