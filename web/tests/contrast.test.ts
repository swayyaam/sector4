/**
 * Contrast guard.
 *
 * DESIGN.md declares where every colour may go (the roles table) and states a
 * contrast ratio for every text/surface pairing that declaration allows (the
 * contrast table). Those claims are only worth something if they are checked,
 * so this test recomputes each one from the shipped tokens. Changing a colour
 * that drops any pairing below AA fails the build rather than quietly shipping
 * unreadable text.
 *
 * It guards five things:
 *   1. tokens.css and DESIGN.md agree on every colour and motion value
 *   2. every colour has a declared role, so nothing escapes the table by
 *      never being mentioned
 *   3. every text colour is measured on every surface it is declared to
 *      appear on, not just the white canvas
 *   4. every measured pairing clears AA for normal text, and the documented
 *      ratio is the real ratio
 *   5. no stylesheet sets text in a colour that has no text role
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative, resolve as resolvePath } from "node:path";
import { describe, expect, it } from "vitest";
import { AA_LARGE, AA_NORMAL, AAA_NORMAL, contrastRatio, wcagLevel } from "../src/lib/contrast";
import {
  loadTokens,
  type DocumentedPairing,
  normaliseTokenName,
  parseContrastTable,
  parseCssColours,
  parseRoles,
  type Role,
  textColourUses,
} from "../src/lib/tokens";

const { css, design, pairings, roles, cssMotion, designMotion } = loadTokens();

const MINIMUM: Record<string, number> = {
  AAA: AAA_NORMAL,
  AA: AA_NORMAL,
  "AA-large": AA_LARGE,
};

function resolve(name: string): string {
  const hex = css[name];
  if (!hex) {
    throw new Error(
      `DESIGN.md references colour "${name}" but tokens.css has no --colour-${name}. ` +
        `Known: ${Object.keys(css).sort().join(", ")}`,
    );
  }
  return hex;
}

/** Pairings the roles table requires that the contrast table does not measure. */
function missingCoverage(rows: DocumentedPairing[], declared: Role[]): string[] {
  const measured = new Set(rows.map((p) => `${p.foreground} on ${p.background}`));
  const gaps: string[] = [];
  for (const r of declared) {
    if (!r.roles.includes("text")) continue;
    for (const bg of r.surfaces) {
      if (!measured.has(`${r.token} on ${bg}`)) gaps.push(`${r.token} on ${bg}`);
    }
  }
  return gaps.sort();
}

const textTokens = new Set(roles.filter((r) => r.roles.includes("text")).map((r) => r.token));
const surfaceTokens = new Set(roles.filter((r) => r.roles.includes("surface")).map((r) => r.token));

describe("design tokens", () => {
  it("parses the full palette from tokens.css", () => {
    expect(Object.keys(css).length).toBeGreaterThanOrEqual(13);
  });

  it("tokens.css and DESIGN.md agree on every colour", () => {
    const drift: string[] = [];
    for (const [name, hex] of Object.entries(design)) {
      const inCss = css[name];
      if (inCss && inCss !== hex) drift.push(`${name}: DESIGN.md ${hex} vs tokens.css ${inCss}`);
    }
    expect(drift, "a colour changed in one file but not the other").toEqual([]);
  });

  it("every colour in DESIGN.md exists in tokens.css, and nothing extra ships", () => {
    expect(Object.keys(design).filter((n) => !(n in css))).toEqual([]);
    expect(
      Object.keys(css).filter((n) => !(n in design)),
      "tokens.css defines a colour DESIGN.md does not know about",
    ).toEqual([]);
  });

  it("tokens.css and DESIGN.md agree on every motion value", () => {
    expect(Object.keys(designMotion).length).toBeGreaterThanOrEqual(9);
    expect(cssMotion).toEqual(designMotion);
  });

  it("reduced motion zeroes every duration, the stagger and the rise", () => {
    const text = readFileSync(resolvePath(__dirname, "..", "src", "styles", "tokens.css"), "utf8");
    const reduced = text.slice(text.indexOf("@media (prefers-reduced-motion: reduce)"));
    for (const name of ["quick", "base", "enter", "fill", "stagger"]) {
      expect(reduced, `--motion-${name} is not zeroed`).toMatch(
        new RegExp(`--motion-${name}:\\s*0ms;`),
      );
    }
    expect(reduced).toMatch(/--motion-rise:\s*0px;/);
  });
});

describe("roles", () => {
  it("finds the roles table", () => {
    expect(roles.length).toBeGreaterThanOrEqual(13);
  });

  it("every colour has a declared role", () => {
    const declared = new Set(roles.map((r) => r.token));
    expect(Object.keys(design).filter((n) => !declared.has(n))).toEqual([]);
  });

  it("every declared surface is itself a colour with a surface role", () => {
    const bad: string[] = [];
    for (const r of roles) {
      for (const s of r.surfaces) {
        if (!surfaceTokens.has(s)) bad.push(`${r.token} declares ${s}, which is not a surface`);
      }
    }
    expect(bad).toEqual([]);
  });

  it("every text colour declares at least one surface", () => {
    expect(roles.filter((r) => r.roles.includes("text") && r.surfaces.length === 0)).toEqual([]);
  });
});

describe("documented contrast pairings", () => {
  it("finds the contrast table", () => {
    expect(pairings.length).toBeGreaterThanOrEqual(20);
  });

  it("measures every text colour on every surface it can appear on", () => {
    expect(missingCoverage(pairings, roles), "undocumented pairing").toEqual([]);
  });

  it("measures only text colours, on surfaces", () => {
    const stray = pairings
      .filter((p) => !textTokens.has(p.foreground) || !surfaceTokens.has(p.background))
      .map((p) => `${p.foreground} on ${p.background}`);
    expect(stray).toEqual([]);
  });

  it.each(pairings)("$foreground on $background clears AA", (p) => {
    const actual = contrastRatio(resolve(p.foreground), resolve(p.background));
    expect(
      actual,
      `${p.foreground} on ${p.background} is ${actual.toFixed(2)}:1, below AA`,
    ).toBeGreaterThanOrEqual(AA_NORMAL);
  });

  it.each(pairings)("$foreground on $background meets the levels it claims", (p) => {
    const actual = contrastRatio(resolve(p.foreground), resolve(p.background));
    const claimed = p.levels.filter((l) => l in MINIMUM);
    expect(claimed, "every pairing must claim AA").toContain("AA");
    expect(p.levels, "no pairing may rely on the large-text allowance").not.toContain("AA-large");
    for (const level of claimed) {
      const min = MINIMUM[level]!;
      expect(
        actual,
        `${p.foreground} on ${p.background} claims ${level} (needs ${min}:1) but is ${actual.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(min);
    }
  });

  it.each(pairings)("$foreground on $background matches its documented ratio", (p) => {
    const actual = contrastRatio(resolve(p.foreground), resolve(p.background));
    expect(
      Math.abs(actual - p.ratio),
      `DESIGN.md says ${p.ratio}:1 but the tokens give ${actual.toFixed(2)}:1`,
    ).toBeLessThan(0.01);
  });
});

/** Every .css and .astro file under src, for the usage scan. */
function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sources(path);
    return /\.(css|astro)$/.test(name) ? [path] : [];
  });
}

describe("what the stylesheets actually do", () => {
  const SRC = resolvePath(__dirname, "..", "src");
  const uses = sources(SRC).flatMap((f) =>
    textColourUses(readFileSync(f, "utf8"), relative(SRC, f)),
  );

  it("finds text colours in use", () => {
    expect(uses.length).toBeGreaterThan(10);
  });

  it("sets text only in colours that have a text role", () => {
    const bad = uses.filter((u) => !textTokens.has(u.token)).map((u) => `${u.token} at ${u.at}`);
    expect(bad, "text set in a colour the contrast table never measured").toEqual([]);
  });

  it("never sets a hex colour outside tokens.css", () => {
    const inline: string[] = [];
    for (const f of sources(SRC)) {
      if (f.endsWith("tokens.css")) continue;
      readFileSync(f, "utf8")
        .split("\n")
        .forEach((line, i) => {
          if (/#[0-9a-fA-F]{6}\b/.test(line) && !/^\s*(\/\/|\*|\/\*)/.test(line)) {
            inline.push(`${relative(SRC, f)}:${i + 1}`);
          }
        });
    }
    expect(inline).toEqual([]);
  });
});

describe("rules the system states in prose", () => {
  it("the focus ring clears the 3:1 non-text minimum on every surface it sits on", () => {
    for (const bg of ["canvas", "canvas-soft", "field"]) {
      expect(contrastRatio(resolve("ink"), resolve(bg))).toBeGreaterThanOrEqual(3);
    }
    expect(contrastRatio(resolve("on-primary"), resolve("ink"))).toBeGreaterThanOrEqual(3);
  });

  it("the tint ladder keeps its order: canvas, canvas-soft, field", () => {
    const l = (n: string) => contrastRatio(resolve(n), "#000000");
    expect(l("canvas")).toBeGreaterThan(l("canvas-soft"));
    expect(l("canvas-soft")).toBeGreaterThan(l("field"));
  });

  it("the text ladder keeps its order: ink, muted, faint", () => {
    const onCanvas = (n: string) => contrastRatio(resolve(n), resolve("canvas"));
    expect(onCanvas("ink")).toBeGreaterThan(onCanvas("text-muted"));
    expect(onCanvas("text-muted")).toBeGreaterThan(onCanvas("text-faint"));
  });

  it("hairlines are non-text and only need to be visible", () => {
    for (const line of ["hairline", "hairline-soft"]) {
      expect(contrastRatio(resolve(line), resolve("canvas"))).toBeGreaterThan(1.1);
    }
  });
});

describe("the guard itself fails when it should", () => {
  it("detects a token that breaks a pairing", () => {
    const broken = parseCssColours("--colour-text-faint: #adadad;\n--colour-canvas: #ffffff;");
    expect(contrastRatio(broken["text-faint"]!, broken["canvas"]!)).toBeLessThan(AA_NORMAL);
  });

  it("detects a stale documented ratio", () => {
    const rows = parseContrastTable(
      "## Accessibility\n\n| Pairing | Ratio | Meets |\n|---|---|---|\n| `{colors.ink}` on `{colors.canvas}` | 3.00:1 | AA |\n",
    );
    expect(rows).toHaveLength(1);
    const actual = contrastRatio(resolve("ink"), resolve("canvas"));
    expect(Math.abs(actual - rows[0]!.ratio)).toBeGreaterThan(0.01);
  });

  it("detects a text colour measured on one declared surface but not the others", () => {
    const md =
      "## Accessibility\n\n### Roles\n\n| Token | Role | Appears on |\n|---|---|---|\n" +
      "| `{colors.text-muted}` | text | canvas, canvas-soft, field |\n\n### Contrast\n\n" +
      "| Pairing | Ratio | Meets |\n|---|---|---|\n" +
      "| `{colors.text-muted}` on `{colors.canvas}` | 6.69:1 | AA |\n";
    expect(missingCoverage(parseContrastTable(md), parseRoles(md))).toEqual([
      "text-muted on canvas-soft",
      "text-muted on field",
    ]);
  });

  it("detects text set in a colour with no text role", () => {
    const found = textColourUses(".x { color: var(--colour-hairline); }", "x.css");
    expect(found).toEqual([{ token: "hairline", at: "x.css:1" }]);
    expect(textTokens.has("hairline")).toBe(false);
  });

  it("does not mistake a background for text", () => {
    expect(textColourUses(".x { background-color: var(--colour-ink); }", "x.css")).toEqual([]);
  });

  it("normalises both token label forms", () => {
    expect(normaliseTokenName("`{colors.accent}`")).toBe("accent");
    expect(normaliseTokenName("canvas-soft")).toBe("canvas-soft");
  });

  it("reports an unknown colour name clearly", () => {
    expect(() => resolve("not-a-token")).toThrow(/tokens.css has no --colour-not-a-token/);
  });
});

describe("wcagLevel", () => {
  it.each([
    ["#000000", "#ffffff", "AAA"],
    ["#141414", "#ffffff", "AAA"],
    ["#5c5c5c", "#f0f0f0", "AA"],
    ["#707070", "#f0f0f0", "AA-large"],
    ["#adadad", "#ffffff", "fail"],
    ["#f0f0f0", "#ffffff", "fail"],
  ])("%s on %s is %s", (a, b, expected) => {
    expect(wcagLevel(a, b)).toBe(expected);
  });
});
