/**
 * Letting a mission read web pages (D-238). The backend reads the `https` addresses written in the goal itself, at most three,
 * and only when the mission names the `web_fetch` action and has a tool-call budget. This mirrors those rules just enough to say,
 * before a request is sent, what will and will not be read; the backend remains the only authority and refuses anything else.
 */
export const WEB_FETCH_ACTION = "web_fetch";
/** The tool-call budget a web-reading mission asks for: the backend reads at most three pages per call, and Research makes one call per plan. */
export const WEB_FETCH_MAX_TOOL_CALLS = 3;
export const MAX_WEB_ADDRESSES = 3;

const ADDRESS = /https?:\/\/[^\s<>"'`\\]+/gi;
const TRAILING = /[.,;:!?)\]}>"']+$/;

/** The web addresses written in `goal`, in order, once each (the same pattern the backend uses). */
export function webAddressesIn(goal: string): string[] {
  const found = new Set<string>();
  for (const match of goal.matchAll(ADDRESS)) found.add(match[0].replace(TRAILING, ""));
  return [...found];
}

/** One plain sentence about what reading the web will do for this goal, or `null` when there is nothing to warn about. */
export function webAccessNote(goal: string): string | null {
  const addresses = webAddressesIn(goal);
  if (addresses.length === 0) return "Add the page's full https:// address to your goal — EIDOS reads only the addresses written there.";
  if (addresses.length > MAX_WEB_ADDRESSES) {
    return `Your goal names ${addresses.length} addresses; at most ${MAX_WEB_ADDRESSES} are read, so none would be. Name fewer.`;
  }
  const insecure = addresses.filter((address) => !/^https:\/\//i.test(address));
  if (insecure.length > 0) return "Only https:// addresses are read. An http:// address would be refused.";
  return null;
}
