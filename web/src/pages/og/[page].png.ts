import type { APIRoute, GetStaticPaths } from "astro";
import { loadDataset } from "../../lib/data";
import { pngResponse, renderCard, type CardSpec } from "../../lib/og";

/** The cards that do not belong to one race. Keyed by the page they front. */
const CARDS: Record<string, Omit<CardSpec, "isMock">> = {
  default: {
    eyebrow: "Formula 1",
    title: "Predictions, scored in public",
    subtitle:
      "Win, podium and top-ten probabilities — and an honest record of how they turned out.",
  },
  "track-record": {
    eyebrow: "Track record",
    title: "Every prediction, including the misses",
    subtitle: "Log loss, Brier score and podium hits for each race, scored against the result.",
  },
  methodology: {
    eyebrow: "Methodology",
    title: "How the numbers are made",
    subtitle: "The data, the snapshots, the scoring rules, and what the model cannot see.",
  },
  credits: {
    eyebrow: "Credits",
    title: "Sources and licences",
    subtitle: "Every dataset, typeface and outline this project builds on.",
  },
};

export const getStaticPaths: GetStaticPaths = () =>
  Object.keys(CARDS).map((page) => ({ params: { page } }));

export const GET: APIRoute = async ({ params }) => {
  const spec = CARDS[params.page!];
  if (!spec) return new Response("Not found", { status: 404 });
  return pngResponse(await renderCard({ ...spec, isMock: loadDataset().isMock }));
};
