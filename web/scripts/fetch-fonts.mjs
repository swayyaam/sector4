/**
 * Download the two typefaces into the repo.
 *
 * Self-hosted rather than linked: a third-party font request is a render-
 * blocking round trip to another origin, and it leaks every visitor's IP to
 * that origin. Both families are SIL OFL, so redistributing them here is fine.
 * Only the latin subset is taken, which is what the site renders.
 */
import { writeFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const OUT = join(dirname(fileURLToPath(import.meta.url)), "..", "public", "fonts");
const UA =
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";

const FAMILIES = [
  { css: "Inter:wght@400;600;700", name: "inter" },
  { css: "JetBrains+Mono:wght@500", name: "jetbrains-mono" },
];

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
console.log(`fonts -> ${OUT}`);
