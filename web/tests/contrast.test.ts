/**
 * Contrast guard.
 *
 * DESIGN.md states a contrast ratio and a WCAG level for every text/surface
 * pairing the system uses. Those claims are only worth something if they are
 * checked, so this test recomputes each one from the shipped tokens. Changing a
 * colour that breaks a documented pairing fails the build rather than quietly
 * shipping unreadable text.
 *
 * It guards three things:
 *   1. tokens.css and DESIGN.md agree on every colour value
 *   2. every documented pairing still meets the WCAG level it claims
 *   3. the documented ratio is actually the ratio, not a stale number
 */
import { describe, expect, it } from "vitest";
import { AA_LARGE, AA_NORMAL, AAA_NORMAL, contrastRatio, wcagLevel } from "../src/lib/contrast";
import {
  loadTokens,
  type DocumentedPairing,
  normaliseTokenName,
  parseContrastTable,
  parseCssColours,
} from "../src/lib/tokens";

const { css, design, pairings } = loadTokens();

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

const LIGHT_SURFACES = ["canvas", "surface-soft", "surface-strong"];
const DARK_SURFACES = ["surface-dark", "surface-dark-elevated"];

/**
 * Surfaces a documented foreground is missing a measurement against.
 *
 * The table is only as good as its coverage. Lighthouse found muted text
 * failing on the soft band while the table said "muted on canvas: AA" and
 * stopped there. A foreground measured on one surface of a group must be
 * measured on all of them, because every surface in a group is used as a
 * section background.
 */
function missingCoverage(rows: DocumentedPairing[], group: string[]): string[] {
  const documented = new Map<string, Set<string>>();
  for (const p of rows) {
    if (!group.includes(p.background)) continue;
    if (!documented.has(p.foreground)) documented.set(p.foreground, new Set());
    documented.get(p.foreground)!.add(p.background);
  }
  const gaps: string[] = [];
  for (const [fg, surfaces] of documented) {
    for (const bg of group) {
      if (!surfaces.has(bg)) gaps.push(`${fg} on ${bg}`);
    }
  }
  return gaps.sort();
}

describe("design tokens", () => {
  it("parses a non-trivial number of colours from tokens.css", () => {
    expect(Object.keys(css).length).toBeGreaterThanOrEqual(20);
  });

  it("tokens.css and DESIGN.md agree on every shared colour", () => {
    const drift: string[] = [];
    for (const [name, hex] of Object.entries(design)) {
      const inCss = css[name];
      if (inCss && inCss !== hex) drift.push(`${name}: DESIGN.md ${hex} vs tokens.css ${inCss}`);
    }
    expect(drift, "a colour changed in one file but not the other").toEqual([]);
  });

  it("every colour named in DESIGN.md exists in tokens.css", () => {
    const missing = Object.keys(design).filter((n) => !(n in css));
    expect(missing, "declared in DESIGN.md but never defined as a CSS token").toEqual([]);
  });
});

describe("documented contrast pairings", () => {
  it("finds the contrast table", () => {
    expect(pairings.length).toBeGreaterThanOrEqual(10);
  });

  it.each(pairings)("$foreground on $background meets $levels", (p) => {
    const actual = contrastRatio(resolve(p.foreground), resolve(p.background));
    const claimed = p.levels.filter((l) => l in MINIMUM);
    expect(claimed.length, `no recognised WCAG level in "${p.levels.join(", ")}"`).toBeGreaterThan(
      0,
    );
    for (const level of claimed) {
      const min = MINIMUM[level]!;
      expect(
        actual,
        `${p.foreground} on ${p.background} claims ${level} (needs ${min}:1) but is ${actual.toFixed(2)}:1`,
      ).toBeGreaterThanOrEqual(min);
    }
  });

  /**
   * The table is only as good as its coverage. Lighthouse found muted text
   * failing on the soft band while the table said "muted on canvas: AA" and
   * stopped there. These two rules make that omission impossible: a foreground
   * measured on one light surface must be measured on all three, and one
   * measured on the dark band must be measured on the elevated dark surface
   * too, because both are used as section backgrounds.
   */
  it("documents every light-surface pairing, not just the canvas", () => {
    expect(missingCoverage(pairings, LIGHT_SURFACES), "undocumented light pairing").toEqual([]);
  });

  it("documents every dark-surface pairing, not just the flat dark band", () => {
    expect(missingCoverage(pairings, DARK_SURFACES), "undocumented dark pairing").toEqual([]);
  });

  it.each(pairings)("$foreground on $background matches its documented ratio", (p) => {
    const actual = contrastRatio(resolve(p.foreground), resolve(p.background));
    expect(
      Math.abs(actual - p.ratio),
      `DESIGN.md says ${p.ratio}:1 but the tokens give ${actual.toFixed(2)}:1`,
    ).toBeLessThan(0.01);
  });
});

describe("rules the system states in prose", () => {
  it("the action colour carries white text at AA", () => {
    expect(contrastRatio(resolve("action"), resolve("on-action"))).toBeGreaterThanOrEqual(
      AA_NORMAL,
    );
  });

  it("text colours clear AA on every light surface they can appear on", () => {
    // A hit or miss label sits in a table row, which hovers to surface-soft,
    // and may sit inside a badge on surface-strong. Checking only the canvas
    // missed a real failure once already.
    for (const semantic of ["positive", "negative", "muted", "body", "action"]) {
      for (const surface of ["canvas", "surface-soft", "surface-strong"]) {
        const r = contrastRatio(resolve(semantic), resolve(surface));
        expect(r, `${semantic} on ${surface} is ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(
          AA_NORMAL,
        );
      }
    }
  });

  it("the on-dark outcome colours clear AA on the dark band", () => {
    for (const semantic of [
      "positive-on-dark",
      "negative-on-dark",
      "action-on-dark",
      "on-dark-soft",
    ]) {
      const r = contrastRatio(resolve(semantic), resolve("surface-dark"));
      expect(r, `${semantic} on surface-dark is ${r.toFixed(2)}:1`).toBeGreaterThanOrEqual(
        AA_NORMAL,
      );
    }
  });

  it("muted-soft is documented as failing AA, so nothing may rely on it for content", () => {
    // Pinned deliberately: if someone "fixes" this value they must also remove
    // the warning in DESIGN.md, and if someone uses it for body text the
    // document already forbids it.
    expect(contrastRatio(resolve("muted-soft"), resolve("canvas"))).toBeLessThan(AA_NORMAL);
  });

  it("hairlines are non-text and only need to be visible, not AA", () => {
    for (const line of ["hairline", "hairline-soft"]) {
      expect(contrastRatio(resolve(line), resolve("canvas"))).toBeGreaterThan(1.1);
    }
  });

  it("caution text meets AA on the caution surface", () => {
    expect(contrastRatio(resolve("caution"), resolve("caution-surface"))).toBeGreaterThanOrEqual(
      AA_NORMAL,
    );
  });
});

describe("the guard itself fails when it should", () => {
  it("detects a token that breaks a documented pairing", () => {
    const broken = parseCssColours("--colour-positive: #7fffd4;\n--colour-canvas: #ffffff;");
    expect(contrastRatio(broken["positive"]!, broken["canvas"]!)).toBeLessThan(AA_NORMAL);
  });

  it("detects a stale documented ratio", () => {
    const rows = parseContrastTable(
      "## Accessibility\n\n| Pairing | Ratio | Meets |\n|---|---|---|\n| `{colors.action}` on canvas | 3.00:1 | AA |\n",
    );
    expect(rows).toHaveLength(1);
    const actual = contrastRatio(resolve("action"), resolve("canvas"));
    expect(Math.abs(actual - rows[0]!.ratio)).toBeGreaterThan(0.01);
  });

  it("detects a foreground measured on one surface but not its siblings", () => {
    const rows = parseContrastTable(
      "## Accessibility\n\n| Pairing | Ratio | Meets |\n|---|---|---|\n" +
        "| `{colors.muted}` on canvas | 5.54:1 | AA |\n",
    );
    expect(missingCoverage(rows, LIGHT_SURFACES)).toEqual([
      "muted on surface-soft",
      "muted on surface-strong",
    ]);
  });

  it("normalises both token label forms", () => {
    expect(normaliseTokenName("`{colors.action}`")).toBe("action");
    expect(normaliseTokenName("surface-soft")).toBe("surface-soft");
    expect(normaliseTokenName("on-action")).toBe("on-action");
  });

  it("reports an unknown colour name clearly", () => {
    expect(() => resolve("not-a-token")).toThrow(/tokens.css has no --colour-not-a-token/);
  });
});

describe("wcagLevel", () => {
  it.each([
    ["#000000", "#ffffff", "AAA"],
    ["#6d28d9", "#ffffff", "AAA"],
    ["#6f757e", "#ffffff", "AA"],
    ["#7c828a", "#ffffff", "AA-large"],
    ["#a8acb3", "#ffffff", "fail"],
    ["#eef0f3", "#ffffff", "fail"],
  ])("%s on %s is %s", (a, b, expected) => {
    expect(wcagLevel(a, b)).toBe(expected);
  });
});
