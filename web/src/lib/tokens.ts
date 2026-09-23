/**
 * Read the design tokens from the files that actually define them.
 *
 * The colour values live in two places by necessity: src/styles/tokens.css is
 * what ships to the browser, and DESIGN.md is the human source of truth. Rather
 * than pick one and let the other drift, both are parsed and compared, so a
 * change to either without the other is a test failure.
 */
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
export const TOKENS_CSS = resolve(HERE, "..", "styles", "tokens.css");
export const DESIGN_MD = resolve(HERE, "..", "..", "..", "DESIGN.md");

/** `--colour-accent: #0060f0;` -> { accent: "#0060f0" } */
export function parseCssColours(css: string): Record<string, string> {
  const out: Record<string, string> = {};
  const re = /--colour-([a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g;
  for (const m of css.matchAll(re)) {
    if (m[1] && m[2]) out[m[1]] = m[2].toLowerCase();
  }
  return out;
}

/** The `colors:` block of DESIGN.md's front matter. */
export function parseDesignColours(md: string): Record<string, string> {
  const start = md.indexOf("\ncolors:");
  if (start === -1) throw new Error("DESIGN.md has no colors: block");
  const rest = md.slice(start + 1);
  const end = rest.search(/\n[a-z][a-z-]*:\s*\n/);
  const block = end === -1 ? rest : rest.slice(0, end);
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/^\s{2}([a-z0-9-]+):\s*"(#[0-9a-fA-F]{6})"\s*$/gm)) {
    if (m[1] && m[2]) out[m[1]] = m[2].toLowerCase();
  }
  return out;
}

export interface DocumentedPairing {
  foreground: string;
  background: string;
  ratio: number;
  levels: string[];
  raw: string;
}

/**
 * Rows of DESIGN.md's accessibility contrast table, e.g.
 * `| {colors.ink} on {colors.canvas} | 18.42:1 | AA, AAA |`
 */
export function parseContrastTable(md: string): DocumentedPairing[] {
  const heading = md.indexOf("## Accessibility");
  if (heading === -1) throw new Error("DESIGN.md has no Accessibility section");
  const section = md.slice(heading);
  const out: DocumentedPairing[] = [];
  const row = /^\|\s*(.+?)\s+on\s+(.+?)\s*\|\s*([\d.]+):1\s*\|\s*(.+?)\s*\|$/gm;
  for (const m of section.matchAll(row)) {
    const [, fg, bg, ratio, levels] = m;
    if (!fg || !bg || !ratio || !levels) continue;
    out.push({
      foreground: normaliseTokenName(fg),
      background: normaliseTokenName(bg),
      ratio: Number.parseFloat(ratio),
      levels: levels.split(",").map((s) => s.trim()),
      raw: m[0],
    });
  }
  return out;
}

export interface Role {
  token: string;
  roles: string[];
  /** Surfaces a text colour is declared to appear on. Empty for non-text. */
  surfaces: string[];
}

/**
 * The roles table in DESIGN.md's Accessibility section, e.g.
 * `| {colors.text-muted} | text | canvas, canvas-soft, field |`
 *
 * This is what makes coverage checkable: the contrast table can only be
 * complete relative to a declaration of where each colour is allowed to go.
 */
export function parseRoles(md: string): Role[] {
  const heading = md.indexOf("### Roles");
  if (heading === -1) throw new Error("DESIGN.md has no Roles table");
  const section = md.slice(heading, md.indexOf("\n### ", heading + 1));
  const out: Role[] = [];
  const row = /^\|\s*`\{colors\.([a-z0-9-]+)\}`\s*\|\s*([a-z, ]+?)\s*\|\s*(.+?)\s*\|$/gm;
  for (const m of section.matchAll(row)) {
    const [, token, roles, surfaces] = m;
    if (!token || !roles || !surfaces) continue;
    out.push({
      token,
      roles: roles.split(",").map((s) => s.trim()),
      surfaces:
        surfaces.trim() === "—" ? [] : surfaces.split(",").map((s) => normaliseTokenName(s)),
    });
  }
  return out;
}

/** The `motion:` block of DESIGN.md's front matter, values as written. */
export function parseDesignMotion(md: string): Record<string, string> {
  const start = md.indexOf("\nmotion:");
  if (start === -1) throw new Error("DESIGN.md has no motion: block");
  const rest = md.slice(start + 1);
  const end = rest.search(/\n[a-z][a-z-]*:\s*\n/);
  const block = end === -1 ? rest : rest.slice(0, end);
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/^\s{2}([a-z0-9-]+):\s*"?([^"\n]+?)"?\s*$/gm)) {
    if (m[1] && m[2]) out[m[1]] = m[2];
  }
  return out;
}

/** `--motion-quick: 120ms;` from the root block only, not the reduced-motion override. */
export function parseCssMotion(css: string): Record<string, string> {
  const root = css.slice(0, css.indexOf("@media"));
  const out: Record<string, string> = {};
  for (const m of root.matchAll(/--motion-([a-z0-9-]+)\s*:\s*([^;]+);/g)) {
    if (m[1] && m[2]) out[m[1]] = m[2].trim();
  }
  return out;
}

/**
 * Every colour token used as a text colour in a stylesheet or component, with
 * where it was found. `color:` only: backgrounds and borders are surfaces and
 * lines, and a bar fill is not text.
 */
export function textColourUses(source: string, file: string): { token: string; at: string }[] {
  const out: { token: string; at: string }[] = [];
  const lines = source.split("\n");
  lines.forEach((line, i) => {
    for (const m of line.matchAll(/(?:^|[\s;{])color\s*:\s*var\(--colour-([a-z0-9-]+)\)/g)) {
      if (m[1]) out.push({ token: m[1], at: `${file}:${i + 1}` });
    }
  });
  return out;
}

/** "`{colors.action}`" and "canvas" both resolve to "action" / "canvas". */
export function normaliseTokenName(label: string): string {
  const braced = /\{colors\.([a-z0-9-]+)\}/.exec(label);
  if (braced && braced[1]) return braced[1];
  return label.replace(/[`*]/g, "").trim();
}

export function loadTokens(): {
  css: Record<string, string>;
  design: Record<string, string>;
  pairings: DocumentedPairing[];
  roles: Role[];
  cssMotion: Record<string, string>;
  designMotion: Record<string, string>;
} {
  const cssText = readFileSync(TOKENS_CSS, "utf8");
  const mdText = readFileSync(DESIGN_MD, "utf8");
  return {
    css: parseCssColours(cssText),
    design: parseDesignColours(mdText),
    pairings: parseContrastTable(mdText),
    roles: parseRoles(mdText),
    cssMotion: parseCssMotion(cssText),
    designMotion: parseDesignMotion(mdText),
  };
}
