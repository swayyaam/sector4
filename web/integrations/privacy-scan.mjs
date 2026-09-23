// @ts-check
/**
 * What the privacy policy promises, checked against what the build produced.
 *
 * /privacy/ says the site loads nothing from any other origin, uses no cookies
 * or browser storage, and sends nothing anywhere from the reader's browser.
 * Those are claims about the output, so they are checked against the output:
 * a change that would make one of them false fails the build instead of
 * quietly making the policy untrue.
 */

/** Elements whose URL attributes make the browser fetch something. */
const LOADING =
  /<(script|link|img|iframe|frame|source|video|audio|embed|object|track|input)\b([^>]*)>/gi;
const URL_ATTRS = /\b(src|href|srcset|data|poster|action|formaction)\s*=\s*("([^"]*)"|'([^']*)')/gi;
/** <link> relations that are metadata only and never cause a request. */
const METADATA_RELS = new Set(["canonical", "alternate", "author", "license", "me"]);
const EXTERNAL = /^(https?:)?\/\//i;

/**
 * Browser APIs that read or write storage, or send data off the page. None of
 * them is needed by a static site that only formats times and ticks a clock.
 */
/** @type {Array<[string, RegExp]>} */
const FORBIDDEN_APIS = [
  ["localStorage", /\blocalStorage\b/],
  ["sessionStorage", /\bsessionStorage\b/],
  ["indexedDB", /\bindexedDB\b/],
  ["document.cookie", /\bdocument\s*\.\s*cookie\b/],
  ["cookieStore", /\bcookieStore\b/],
  ["fetch()", /\bfetch\s*\(/],
  ["XMLHttpRequest", /\bXMLHttpRequest\b/],
  ["navigator.sendBeacon", /\bsendBeacon\b/],
  ["WebSocket", /\bWebSocket\b/],
  ["EventSource", /\bEventSource\b/],
  ["service worker", /\bserviceWorker\b/],
  ["dynamic import from a URL", /\bimport\s*\(\s*["'`](https?:)?\/\//],
];

/**
 * @param {string} html
 * @returns {string[]} one line per problem, empty when the page keeps every promise
 */
export function scanHtml(html) {
  const problems = [];
  for (const m of html.matchAll(LOADING)) {
    const tag = (m[1] ?? "").toLowerCase();
    const attrs = m[2] ?? "";
    if (tag === "link") {
      const rel =
        /\brel\s*=\s*["']([^"']+)["']/i.exec(attrs)?.[1]?.toLowerCase().split(/\s+/) ?? [];
      if (rel.length && rel.every((r) => METADATA_RELS.has(r))) continue;
    }
    for (const a of attrs.matchAll(URL_ATTRS)) {
      const value = a[3] ?? a[4] ?? "";
      for (const part of value.split(",")) {
        const url = part.trim().split(/\s+/)[0] ?? "";
        if (EXTERNAL.test(url)) problems.push(`<${tag}> loads ${url}`);
      }
    }
  }
  for (const m of html.matchAll(/url\(\s*["']?((https?:)?\/\/[^"')]+)/gi)) {
    problems.push(`CSS loads ${m[1]}`);
  }
  for (const m of html.matchAll(/@import\s+(url\()?\s*["']?((https?:)?\/\/[^"')\s;]+)/gi)) {
    problems.push(`CSS imports ${m[2]}`);
  }
  // Executable scripts only. JSON-LD is data, never run, and may mention URLs.
  for (const m of html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)) {
    const type = /\btype\s*=\s*["']([^"']+)["']/i.exec(m[1] ?? "")?.[1]?.toLowerCase();
    if (type && type !== "module" && type !== "text/javascript") continue;
    problems.push(...scanScript(m[2] ?? ""));
  }
  return problems;
}

/**
 * @param {string} source
 * @returns {string[]}
 */
export function scanScript(source) {
  return FORBIDDEN_APIS.filter(([, re]) => re.test(source)).map(([name]) => `script uses ${name}`);
}

/**
 * @param {string} css
 * @returns {string[]}
 */
export function scanCss(css) {
  return scanHtml(`<style>${css}</style>`);
}
