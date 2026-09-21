// @ts-check
import { defineConfig } from "astro/config";

export default defineConfig({
  site: "https://sector4.dev",
  output: "static",
  trailingSlash: "always",
  // The whole stylesheet is under 10KB per page. Inlining it removes the one
  // render-blocking request on the critical path; a separate file would only
  // pay off across many page views, and the pages are mostly-unique HTML anyway.
  build: { inlineStylesheets: "always" },
  compressHTML: true,
  devToolbar: { enabled: false },
});
