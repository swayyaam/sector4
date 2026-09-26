/**
 * Formatting. One implementation each, so a probability or an instant is never
 * rendered two different ways on two different pages.
 */

/** 0.1786 -> "17.9%". One decimal, per DESIGN.md. */
export function percent(p: number, decimals = 1): string {
  if (!Number.isFinite(p)) throw new RangeError(`not a finite probability: ${p}`);
  return `${(p * 100).toFixed(decimals)}%`;
}

/** A probability as a bar width relative to the column maximum, never to 100%. */
export function barWidth(p: number, columnMax: number): number {
  if (columnMax <= 0) return 0;
  return Math.max(0, Math.min(100, (p / columnMax) * 100));
}

/** 4.62 -> "4.6". Expected finishing position. */
export function position(n: number): string {
  return n.toFixed(1);
}

/** 1 -> "1st", 2 -> "2nd", 11 -> "11th". */
export function ordinal(n: number): string {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
  switch (n % 10) {
    case 1:
      return `${n}st`;
    case 2:
      return `${n}nd`;
    case 3:
      return `${n}rd`;
    default:
      return `${n}th`;
  }
}

/** Log loss and Brier to three decimals, the precision the differences live at. */
export function score(n: number): string {
  return n.toFixed(3);
}

export function driverName(d: { forename: string; surname: string }): string {
  return `${d.forename} ${d.surname}`;
}

/** "Verstappen" for tight columns; the code where there is even less room. */
export function shortDriverName(d: { surname: string; code: string | null }): string {
  return d.surname;
}

/** "qualifying order" -> "Qualifying order", for a label that starts a line. */
export function sentenceStart(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}
