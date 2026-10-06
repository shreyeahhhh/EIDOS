/**
 * The dashboard's navigation index: which missions the signed-in account has created in this browser, remembered locally.
 *
 * The backend has no list-missions endpoint (a deliberate V1.4 limitation) and provisioning is
 * out of band, so there is no way to ask it "what are my missions." This index is never a second
 * source of truth for a mission's *state* — every field the dashboard shows is fetched live from
 * the backend by id — it only remembers *which ids to ask about*. A stale or now-inaccessible id
 * (a real 404) is pruned silently; it was never data, just a pointer.
 *
 * It is kept under the signed-in user's id (`lib/signed-in-user.tsx`, D-249): another account on the
 * same browser has its own, so it neither lists this one's missions nor prunes them (each would answer
 * it 404), and this account finds its list again after signing back in.
 */

const STORAGE_PREFIX = "eidos.missionIndex:";
/** Before D-249 one index was kept for every account on the browser. */
const UNKEYED_STORAGE_KEY = "eidos.missionIndex";
const MAX_ENTRIES = 50;

export interface IndexedMission {
  id: string;
  goal: string;
  createdAt: string;
}

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`;
}

/**
 * The index from before D-249 is taken over by the first account that reads its own, so whoever used this browser keeps their list.
 * If it was really another account's, those ids answer 404 for this one and are pruned, as they always were; the backend never shows
 * one account another's mission.
 */
function adoptUnkeyedIndex(userId: string): void {
  const unkeyed = window.localStorage.getItem(UNKEYED_STORAGE_KEY);
  if (unkeyed === null) return;
  if (window.localStorage.getItem(storageKey(userId)) === null) window.localStorage.setItem(storageKey(userId), unkeyed);
  window.localStorage.removeItem(UNKEYED_STORAGE_KEY);
}

function read(userId: string): IndexedMission[] {
  if (typeof window === "undefined") return [];
  try {
    adoptUnkeyedIndex(userId);
    const raw = window.localStorage.getItem(storageKey(userId));
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (item): item is IndexedMission =>
        typeof item === "object" && item !== null && typeof (item as IndexedMission).id === "string",
    );
  } catch {
    return [];
  }
}

function write(userId: string, entries: IndexedMission[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(userId), JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // Storage may be unavailable (private browsing, quota); the dashboard just has less history.
  }
}

/** Every mission this account remembers, most recently created first. */
export function listIndexedMissions(userId: string): IndexedMission[] {
  return [...read(userId)].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

/** Remembers a mission this account just created. */
export function rememberMission(userId: string, entry: IndexedMission): void {
  const withoutDuplicate = read(userId).filter((item) => item.id !== entry.id);
  write(userId, [entry, ...withoutDuplicate]);
}

/** Drops an id that the backend genuinely no longer has for this account (a real 404) — not an error, just pruning a stale pointer. */
export function forgetMission(userId: string, id: string): void {
  write(userId, read(userId).filter((item) => item.id !== id));
}
