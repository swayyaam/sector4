import type { APIRoute, GetStaticPaths } from "astro";
import {
  circuitById,
  driverById,
  driversByWinProbability,
  loadDataset,
  preferredSnapshot,
  teamById,
} from "../../../../lib/data";
import { driverName, percent } from "../../../../lib/format";
import { pngResponse, renderCard } from "../../../../lib/og";
import { SNAPSHOT_LABEL } from "../../../../lib/snapshots";
import { formatUtc } from "../../../../lib/time";

export const getStaticPaths: GetStaticPaths = () => {
  const { reference, predictions } = loadDataset();
  const predicted = new Set(predictions.map((p) => p.race_id));
  return reference.races
    .filter((r) => predicted.has(r.race_id))
    .map((r) => ({
      params: { season: String(r.season), slug: r.slug },
      props: { raceId: r.race_id },
    }));
};

export const GET: APIRoute = async ({ props }) => {
  const { raceId } = props as { raceId: number };
  const { reference, predictions, isMock } = loadDataset();
  const race = reference.races.find((r) => r.race_id === raceId)!;
  const circuit = circuitById(reference).get(race.circuit_id)!;
  const drivers = driverById(reference);
  const teams = teamById(reference);
  const snapshot = preferredSnapshot(predictions, raceId)!;

  // The card shows the same three drivers, from the same snapshot, that the
  // page leads with. If the page changes its mind, so does the card.
  const rows = driversByWinProbability(snapshot)
    .slice(0, 3)
    .map((d) => {
      const team = teams.get(d.team_entity_id)!;
      return {
        name: driverName(drivers.get(d.driverId)!),
        team: team.short_name,
        colour: team.colour_on_light,
        value: percent(d.p_win),
      };
    });

  return pngResponse(
    await renderCard({
      eyebrow: `Round ${race.round} of ${race.season}`,
      title: race.name,
      subtitle: `${circuit.name}, ${circuit.locality}, ${circuit.country}`,
      rows,
      // A prediction shown anywhere carries its snapshot and when it was made.
      note: `${SNAPSHOT_LABEL[snapshot.snapshot]} win probability, generated ${formatUtc(snapshot.generated_at)}`,
      isMock,
    }),
  );
};
