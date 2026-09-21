/**
 * Time handling.
 *
 * Everything is stored in UTC and rendered in the viewer's local zone. The
 * conversion cannot happen at build time — the build has no idea where the
 * reader is — so the server renders a stable UTC string inside a <time> element
 * and a tiny island rewrites it on the client. These helpers are the shared
 * half of that, and are pure so they can be tested without a DOM.
 */

export interface Session {
  name: string;
  starts_at: string;
}

export function toDate(iso: string): Date {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) throw new RangeError(`not a valid instant: ${iso}`);
  return d;
}

/** Server-side rendering of an instant: unambiguous, and identical every build. */
export function formatUtc(iso: string): string {
  const d = toDate(iso);
  const date = d.toLocaleDateString("en-GB", {
    weekday: "short",
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  });
  const time = d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
  return `${date}, ${time} UTC`;
}

/** Whole days, hours, minutes between two instants. Never negative. */
export function countdown(
  from: Date,
  to: Date,
): { days: number; hours: number; minutes: number; past: boolean } {
  const ms = to.getTime() - from.getTime();
  if (ms <= 0) return { days: 0, hours: 0, minutes: 0, past: true };
  const minutes = Math.floor(ms / 60000);
  return {
    days: Math.floor(minutes / 1440),
    hours: Math.floor((minutes % 1440) / 60),
    minutes: minutes % 60,
    past: false,
  };
}

/** "3 days, 4 hours" — coarse by design; a live clock is the island's job. */
export function formatCountdown(c: ReturnType<typeof countdown>): string {
  if (c.past) return "Under way or complete";
  const parts: string[] = [];
  if (c.days) parts.push(`${c.days} day${c.days === 1 ? "" : "s"}`);
  if (c.hours) parts.push(`${c.hours} hour${c.hours === 1 ? "" : "s"}`);
  if (!c.days && !c.hours) parts.push(`${c.minutes} minute${c.minutes === 1 ? "" : "s"}`);
  return parts.join(", ");
}

export function isPast(iso: string, now: Date): boolean {
  return toDate(iso).getTime() <= now.getTime();
}
