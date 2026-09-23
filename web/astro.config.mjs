// @ts-check
import { defineConfig } from "astro/config";
import publishGuards from "./integrations/publish-guards.mjs";

/**
 * The public origin, used for canonical links, the sitemap, robots.txt and
 * Open Graph image URLs.
 *
 * On Vercel it is the project's production domain, which Vercel sets on every
 * build as VERCEL_PROJECT_PRODUCTION_URL: the custom domain once one is
 * attached, the vercel.app domain until then. Preview builds get the
 * production value too, so a preview never names itself as canonical. No
 * domain is written here, so attaching one needs no code change, only a
 * redeploy.
 *
 * Anywhere else (local builds, CI) it is the local preview server, because
 * those builds are never published.
 */
function siteUrl() {
  const production = process.env.VERCEL_PROJECT_PRODUCTION_URL;
  if (production) return `https://${production}`;
  if (process.env.VERCEL) {
    throw new Error(
      "Building on Vercel without VERCEL_PROJECT_PRODUCTION_URL. Enable system environment " +
        "variables in the project settings; without them every canonical URL would be wrong.",
    );
  }
  return "http://localhost:4321";
}

export default defineConfig({
  site: siteUrl(),
  output: "static",
  trailingSlash: "always",
  // The whole stylesheet is under 10KB per page. Inlining it removes the one
  // render-blocking request on the critical path; a separate file would only
  // pay off across many page views, and the pages are mostly-unique HTML anyway.
  build: { inlineStylesheets: "always" },
  // Scripts are emitted as files rather than inlined, so the Content Security
  // Policy can be script-src 'self' with no inline allowance. They are about
  // a kilobyte, cached as immutable, and not on the critical rendering path.
  vite: { build: { assetsInlineLimit: 0 } },
  compressHTML: true,
  devToolbar: { enabled: false },
  integrations: [publishGuards()],
});
