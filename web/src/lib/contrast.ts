/**
 * WCAG 2.1 relative luminance and contrast ratio.
 *
 * Pure functions with no dependencies so they can be unit tested directly and
 * reused by the token guard, chart code, and any future team-colour tinting.
 */

export type Hex = string;

/** WCAG minimum contrast ratios. */
export const AA_NORMAL = 4.5;
export const AA_LARGE = 3;
export const AAA_NORMAL = 7;

export function parseHex(hex: Hex): [number, number, number] {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex.trim());
  if (!m || !m[1]) throw new Error(`not a 6-digit hex colour: ${hex}`);
  const n = m[1];
  return [
    Number.parseInt(n.slice(0, 2), 16),
    Number.parseInt(n.slice(2, 4), 16),
    Number.parseInt(n.slice(4, 6), 16),
  ];
}

/** sRGB channel (0-255) to linear light. */
function channel(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG relative luminance, 0 (black) to 1 (white). */
export function relativeLuminance(hex: Hex): number {
  const [r, g, b] = parseHex(hex);
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG contrast ratio, 1 to 21. Order of arguments does not matter. */
export function contrastRatio(a: Hex, b: Hex): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const [hi, lo] = la > lb ? [la, lb] : [lb, la];
  return (hi + 0.05) / (lo + 0.05);
}

/** Highest WCAG level a pairing satisfies for normal-size text. */
export function wcagLevel(a: Hex, b: Hex): "AAA" | "AA" | "AA-large" | "fail" {
  const r = contrastRatio(a, b);
  if (r >= AAA_NORMAL) return "AAA";
  if (r >= AA_NORMAL) return "AA";
  if (r >= AA_LARGE) return "AA-large";
  return "fail";
}

export function meets(a: Hex, b: Hex, minimum: number): boolean {
  return contrastRatio(a, b) >= minimum;
}
