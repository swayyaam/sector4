/**
 * The facts the privacy policy and terms depend on, in one place.
 *
 * Both pages read these values, so the last-updated date, the operator and the
 * contact address cannot drift apart between them. A value that has not been
 * supplied stays null and renders as visibly unset; the publish guard in
 * integrations/publish-guards.mjs refuses a production build until it is set.
 */
import { z } from "zod";
import raw from "../data/legal.json";

export const legalSchema = z.object({
  operator: z.string().min(1),
  operator_country: z.string().min(1),
  contact_email: z.email().nullable(),
  jurisdiction_city: z.string().min(1).nullable(),
  last_updated: z.iso.date(),
  hosting: z.object({
    provider: z.string().min(1),
    provider_country: z.string().min(1),
    plan: z.string().min(1),
    runtime_log_retention: z.string().min(1),
    privacy_notice: z.url(),
    dpa: z.url(),
  }),
});

export type Legal = z.infer<typeof legalSchema>;

export const LEGAL: Legal = legalSchema.parse(raw);

/** "23 September 2026": the form both pages print, from the one stored date. */
export function lastUpdated(legal: Legal = LEGAL): string {
  return new Date(`${legal.last_updated}T00:00:00Z`).toLocaleDateString("en-GB", {
    day: "numeric",
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

/** Fields a public release cannot ship without. */
export function missingForRelease(legal: Legal = LEGAL): string[] {
  const missing: string[] = [];
  if (!legal.contact_email) missing.push("contact_email");
  if (!legal.jurisdiction_city) missing.push("jurisdiction_city");
  return missing;
}
