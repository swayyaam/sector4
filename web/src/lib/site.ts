/** Where the code and every published prediction live. Commit links point here. */
export const REPO = "https://github.com/swayyaam/sector4";

export function commitUrl(sha: string): string {
  return `${REPO}/commit/${sha}`;
}
