/**
 * The privacy policy's technical claims are enforced by a build guard. These
 * tests prove the guard notices each kind of change that would make a claim
 * false, and stays quiet about the things that are not requests at all.
 */
import { afterEach, describe, expect, it } from "vitest";
import { scanCss, scanHtml, scanScript } from "../integrations/privacy-scan.mjs";
import publishGuards from "../integrations/publish-guards.mjs";
import { LEGAL, lastUpdated, missingForRelease } from "../src/lib/legal";

describe("the privacy scan flags", () => {
  it.each([
    ['<script src="https://cdn.example.com/a.js"></script>', "cdn.example.com"],
    ['<script src="//cdn.example.com/a.js"></script>', "cdn.example.com"],
    ['<link rel="stylesheet" href="https://fonts.googleapis.com/css2">', "fonts.googleapis.com"],
    ['<link rel="preconnect" href="https://fonts.gstatic.com">', "fonts.gstatic.com"],
    ['<img src="https://example.com/pixel.gif">', "example.com"],
    ['<img srcset="/a.png 1x, https://cdn.example.com/b.png 2x">', "cdn.example.com"],
    ['<iframe src="https://www.youtube.com/embed/x"></iframe>', "youtube.com"],
    ["<style>body{background:url(https://example.com/bg.png)}</style>", "example.com"],
    ["<style>@import url('https://example.com/x.css');</style>", "example.com"],
  ])("an external load: %s", (html, host) => {
    const found = scanHtml(html);
    expect(found.join(" ")).toContain(host);
  });

  it.each([
    "localStorage.setItem('a', '1')",
    "sessionStorage.getItem('a')",
    "document.cookie = 'a=1'",
    "fetch('/api')",
    "navigator.sendBeacon('/b', x)",
    "new XMLHttpRequest()",
    "new WebSocket('wss://x')",
    "indexedDB.open('x')",
    "navigator.serviceWorker.register('/sw.js')",
  ])("a storage or network API in a script: %s", (code) => {
    expect(scanScript(code)).not.toEqual([]);
    expect(scanHtml(`<script type="module">${code}</script>`)).not.toEqual([]);
  });
});

describe("the privacy scan allows", () => {
  it.each([
    '<link rel="canonical" href="https://sector4.example/">',
    '<link rel="icon" href="/favicon.svg" type="image/svg+xml">',
    '<link rel="preload" href="/fonts/inter-var.woff2" as="font" crossorigin>',
    '<a href="https://github.com/swayyaam/sector4">source</a>',
    '<meta property="og:image" content="https://sector4.example/og/default.png">',
    '<script type="application/ld+json">{"url":"https://sector4.example/","x":"fetch("}</script>',
    '<script type="module">const d = new Date(el.dateTime); el.textContent = d.toLocaleString();</script>',
  ])("%s", (html) => {
    expect(scanHtml(html)).toEqual([]);
  });

  it("self-hosted CSS", () => {
    expect(scanCss("@font-face{src:url(/fonts/inter-var.woff2)}")).toEqual([]);
  });
});

describe("the release guard", () => {
  const before = process.env.VERCEL_ENV;
  afterEach(() => {
    if (before === undefined) delete process.env.VERCEL_ENV;
    else process.env.VERCEL_ENV = before;
  });
  const start = publishGuards().hooks["astro:build:start"] as (opts: {
    logger: { info: (m: string) => void };
  }) => void;
  const logger = { info: () => undefined };

  it("does nothing outside a production deployment", () => {
    delete process.env.VERCEL_ENV;
    expect(() => start({ logger })).not.toThrow();
    process.env.VERCEL_ENV = "preview";
    expect(() => start({ logger })).not.toThrow();
  });

  it("refuses production while a legal fact is missing, and names it", () => {
    process.env.VERCEL_ENV = "production";
    const missing = missingForRelease();
    if (missing.length === 0) {
      expect(() => start({ logger })).not.toThrow();
    } else {
      expect(() => start({ logger })).toThrow(new RegExp(missing[0]!));
    }
  });
});

describe("legal facts", () => {
  it("parse, and print one date for both pages", () => {
    expect(LEGAL.operator).toBe("Swayam Mishra");
    expect(lastUpdated()).toMatch(/^\d{1,2} [A-Z][a-z]+ \d{4}$/);
  });

  it("list exactly the facts still missing", () => {
    expect(missingForRelease({ ...LEGAL, contact_email: null, jurisdiction_city: null })).toEqual([
      "contact_email",
      "jurisdiction_city",
    ]);
    expect(
      missingForRelease({ ...LEGAL, contact_email: "a@example.com", jurisdiction_city: "X" }),
    ).toEqual([]);
  });
});
