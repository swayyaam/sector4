// @ts-check
/**
 * Two guards on what the build is allowed to publish.
 *
 * 1. Privacy: after every build, the output is scanned for anything the
 *    privacy policy says does not exist (see privacy-scan.mjs). Local builds,
 *    CI and Vercel all run it.
 * 2. Release: a production deployment on Vercel refuses to build while the
 *    legal pages are missing facts they cannot ship without, such as the
 *    contact address. Preview deployments and local builds still build, so
 *    the pages can be reviewed with the gap visible.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";
import { scanCss, scanHtml, scanScript } from "./privacy-scan.mjs";

const LEGAL_JSON = new URL("../src/data/legal.json", import.meta.url);

/** @param {string} dir @returns {string[]} */
function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    return statSync(path).isDirectory() ? walk(path) : [path];
  });
}

/** @returns {import("astro").AstroIntegration} */
export default function publishGuards() {
  return {
    name: "sector4-publish-guards",
    hooks: {
      "astro:build:start": ({ logger }) => {
        if (process.env.VERCEL_ENV !== "production") return;
        const legal = JSON.parse(readFileSync(LEGAL_JSON, "utf8"));
        const missing = ["contact_email", "jurisdiction_city"].filter((k) => !legal[k]);
        if (missing.length) {
          throw new Error(
            `Refusing a production build: src/data/legal.json has no ${missing.join(" or ")}. ` +
              "The privacy policy and terms cannot go live without them.",
          );
        }
        logger.info("legal facts complete");
      },
      "astro:build:done": ({ dir, logger }) => {
        const root = fileURLToPath(dir);
        /** @type {string[]} */
        const problems = [];
        for (const file of walk(root)) {
          const rel = relative(root, file);
          /** @type {string[]} */
          let found = [];
          if (file.endsWith(".html")) found = scanHtml(readFileSync(file, "utf8"));
          else if (/\.m?js$/.test(file)) found = scanScript(readFileSync(file, "utf8"));
          else if (file.endsWith(".css")) found = scanCss(readFileSync(file, "utf8"));
          problems.push(...found.map((p) => `${rel}: ${p}`));
        }
        if (problems.length) {
          throw new Error(
            "The build does something /privacy/ says this site never does. Change the policy " +
              "first, deliberately, then this guard:\n  " +
              [...new Set(problems)].join("\n  "),
          );
        }
        logger.info("privacy claims hold: no third-party loads, no storage, no network calls");
      },
    },
  };
}
