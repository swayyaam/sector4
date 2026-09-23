import type { APIRoute } from "astro";
import { loadDataset } from "../lib/data";

/**
 * Hand-rolled rather than an integration: the site has six fixed pages and one
 * page per predicted race, and the list has to leave out the Open Graph images
 * and the 404, which a directory crawl would happily include.
 */
export const GET: APIRoute = ({ site }) => {
  const origin = site!.href.replace(/\/$/, "");
  const { reference, predictions, meta } = loadDataset();
  const predicted = new Set(predictions.map((p) => p.race_id));

  const entries: { path: string; priority: string; changefreq: string }[] = [
    { path: "/", priority: "1.0", changefreq: "daily" },
    { path: "/track-record/", priority: "0.8", changefreq: "weekly" },
    { path: "/methodology/", priority: "0.5", changefreq: "monthly" },
    { path: "/credits/", priority: "0.3", changefreq: "monthly" },
    { path: "/privacy/", priority: "0.2", changefreq: "monthly" },
    { path: "/terms/", priority: "0.2", changefreq: "monthly" },
    ...reference.races
      .filter((r) => predicted.has(r.race_id))
      .sort((a, b) => b.season - a.season || b.round - a.round)
      .map((r) => ({
        path: `/races/${r.season}/${r.slug}/`,
        priority: "0.7",
        changefreq: "weekly",
      })),
  ];

  const body = [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ...entries.map((e) =>
      [
        "  <url>",
        `    <loc>${origin}${e.path}</loc>`,
        `    <lastmod>${meta.generated_at}</lastmod>`,
        `    <changefreq>${e.changefreq}</changefreq>`,
        `    <priority>${e.priority}</priority>`,
        "  </url>",
      ].join("\n"),
    ),
    "</urlset>",
    "",
  ].join("\n");

  return new Response(body, { headers: { "Content-Type": "application/xml; charset=utf-8" } });
};
