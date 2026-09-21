/**
 * Open Graph card rendering.
 *
 * Link previews get cached by every platform that touches them, sometimes for
 * weeks, so a card is the one artefact that can outlive the page it came from.
 * That makes two things non-negotiable. It has to be generated from the same
 * validated data as the page, so it cannot drift, and while the site is
 * running on sample data it has to say so as loudly as the banner does — a
 * cached preview must never be mistakable for a real prediction.
 *
 * Build-time only: satori and resvg never reach the browser, and the
 * TrueType faces they need live outside public/ so nothing can serve them.
 */
import { Resvg } from "@resvg/resvg-js";
import satori from "satori";
import tokensCss from "../styles/tokens.css?raw";
import { parseCssColours } from "./tokens";

export const OG_WIDTH = 1200;
export const OG_HEIGHT = 630;

/** The same tokens the site ships. Satori cannot read custom properties. */
const C = parseCssColours(tokensCss);

const colour = (name: string): string => {
  const hex = C[name];
  if (!hex)
    throw new Error(`og card references --colour-${name}, which tokens.css does not define`);
  return hex;
};

/**
 * Fonts come through the bundler rather than off disk. Reading by path works
 * in dev and then fails in the build, where the compiled module no longer
 * sits beside src/assets; globbing makes Vite resolve them at build time.
 */
const FONT_FILES = import.meta.glob("../assets/fonts/*.ttf", {
  eager: true,
  query: "?inline",
  import: "default",
}) as Record<string, string>;

function fontData(file: string): Buffer {
  const key = Object.keys(FONT_FILES).find((k) => k.endsWith(`/${file}`));
  if (!key) {
    throw new Error(`${file} is missing from src/assets/fonts — run \`npm run fonts\``);
  }
  return Buffer.from(FONT_FILES[key]!.split(",")[1]!, "base64");
}

const fonts = [
  {
    name: "Inter",
    data: fontData("inter-400.ttf"),
    weight: 400 as const,
    style: "normal" as const,
  },
  {
    name: "Inter",
    data: fontData("inter-700.ttf"),
    weight: 700 as const,
    style: "normal" as const,
  },
  {
    name: "JetBrains Mono",
    data: fontData("jetbrains-mono-500.ttf"),
    weight: 500 as const,
    style: "normal" as const,
  },
];

// Satori takes React-shaped objects. Building them by hand keeps the renderer
// free of a JSX runtime for three element types.
type Node = { type: string; props: Record<string, unknown> };
const el = (type: string, props: Record<string, unknown>, ...children: unknown[]): Node => ({
  type,
  // An empty children array counts as "more than one child" to satori, which
  // then demands an explicit display on a div that has no children at all.
  // Leaf elements therefore carry no children key.
  props:
    children.length === 0
      ? { ...props }
      : { ...props, children: children.length === 1 ? children[0] : children },
});

export interface CardRow {
  name: string;
  team: string;
  colour: string;
  value: string;
}

export interface CardSpec {
  eyebrow: string;
  title: string;
  subtitle?: string;
  rows?: CardRow[];
  /** Renders the same warning the site banner carries. Never optional in effect. */
  isMock: boolean;
}

function wordmark(): Node {
  return el(
    "div",
    { style: { display: "flex", alignItems: "center", gap: "14px" } },
    el("div", {
      style: {
        width: "14px",
        height: "30px",
        borderRadius: "4px",
        background: colour("action-on-dark"),
      },
    }),
    el(
      "div",
      { style: { fontSize: "30px", fontWeight: 700, color: colour("on-dark") } },
      "Sector 4",
    ),
  );
}

function mockBadge(): Node {
  return el(
    "div",
    {
      style: {
        display: "flex",
        alignItems: "center",
        background: colour("caution-surface"),
        color: colour("caution"),
        fontSize: "22px",
        fontWeight: 700,
        letterSpacing: "0.04em",
        padding: "10px 22px",
        borderRadius: "100px",
      },
    },
    "SAMPLE DATA — NOT A REAL PREDICTION",
  );
}

function row(r: CardRow): Node {
  return el(
    "div",
    { style: { display: "flex", alignItems: "center", gap: "16px", width: "100%" } },
    el("div", {
      style: {
        width: "8px",
        height: "46px",
        borderRadius: "4px",
        background: r.colour,
        flexShrink: 0,
      },
    }),
    el(
      "div",
      { style: { display: "flex", flexDirection: "column", flexGrow: 1, minWidth: 0 } },
      el("div", { style: { fontSize: "27px", color: colour("on-dark") } }, r.name),
      el("div", { style: { fontSize: "19px", color: colour("on-dark-soft") } }, r.team),
    ),
    el(
      "div",
      {
        style: {
          display: "flex",
          justifyContent: "flex-end",
          width: "120px",
          flexShrink: 0,
          fontSize: "30px",
          fontFamily: "JetBrains Mono",
          fontWeight: 500,
          color: colour("on-dark"),
        },
      },
      r.value,
    ),
  );
}

function card(spec: CardSpec): Node {
  // Explicit widths rather than flex-grow: satori will not shrink a text block
  // below its natural width, so a long race name would push the probabilities
  // off the right edge of the card.
  const hasRows = Boolean(spec.rows?.length);
  const left = el(
    "div",
    {
      style: {
        display: "flex",
        flexDirection: "column",
        gap: "18px",
        width: hasRows ? "560px" : "1072px",
      },
    },
    el(
      "div",
      {
        style: {
          fontSize: "22px",
          letterSpacing: "0.08em",
          textTransform: "uppercase",
          color: colour("on-dark-soft"),
        },
      },
      spec.eyebrow,
    ),
    el(
      "div",
      {
        style: {
          fontSize: hasRows ? "60px" : "68px",
          fontWeight: 700,
          lineHeight: 1.05,
          color: colour("on-dark"),
        },
      },
      spec.title,
    ),
    ...(spec.subtitle
      ? [el("div", { style: { fontSize: "28px", color: colour("on-dark-soft") } }, spec.subtitle)]
      : []),
  );

  const body = hasRows
    ? el(
        "div",
        { style: { display: "flex", gap: "48px", alignItems: "flex-end", width: "1072px" } },
        left,
        el(
          "div",
          { style: { display: "flex", flexDirection: "column", gap: "20px", width: "464px" } },
          ...spec.rows!.map(row),
        ),
      )
    : left;

  return el(
    "div",
    {
      style: {
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        justifyContent: "space-between",
        background: colour("surface-dark"),
        fontFamily: "Inter",
        padding: "56px 64px",
      },
    },
    el(
      "div",
      { style: { display: "flex", alignItems: "center", justifyContent: "space-between" } },
      wordmark(),
      ...(spec.isMock ? [mockBadge()] : []),
    ),
    body,
    el(
      "div",
      { style: { fontSize: "20px", color: colour("on-dark-soft") } },
      "Unofficial fan project · not associated with the Formula 1 companies · not betting advice",
    ),
  );
}

export async function renderCard(spec: CardSpec): Promise<Buffer> {
  const svg = await satori(card(spec) as never, { width: OG_WIDTH, height: OG_HEIGHT, fonts });
  return Buffer.from(
    new Resvg(svg, { fitTo: { mode: "width", value: OG_WIDTH } }).render().asPng(),
  );
}

/** One place that turns a PNG into a cacheable response. */
export function pngResponse(body: Buffer): Response {
  return new Response(new Uint8Array(body), {
    headers: {
      "Content-Type": "image/png",
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}
