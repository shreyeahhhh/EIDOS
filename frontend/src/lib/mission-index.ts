/**
 * The dashboard's navigation index: which missions this browser has created, remembered locally.
 *
 * The backend has no list-missions endpoint (a deliberate V1.4 limitation) and provisioning is
 * out of band, so there is no way to ask it "what are my missions." This index is never a second
 * source of truth for a mission's *state* — every field the dashboard shows is fetched live from
 * the backend by id — it only remembers *which ids to ask about*. A stale or now-inaccessible id
 * (a real 404) is pruned silently; it was never data, just a pointer.
 */

const STORAGE_KEY = "eidos.missionIndex";
const MAX_ENTRIES = 50;

export interface IndexedMission {
  id: string;
  goal: string;
  createdAt: string;
}

function read(): IndexedMission[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
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

function write(entries: IndexedMission[]): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_ENTRIES)));
  } catch {
    // Storage may be unavailable (private browsing, quota); the dashboard just has less history.
  }
}

/** Every remembered mission, most recently created first. */
export function listIndexedMissions(): IndexedMission[] {
  return [...read()].sort((a, b) => b.createdAt.localeCompare(a.createdAt));
}

/** Remembers a mission this browser just created. */
export function rememberMission(entry: IndexedMission): void {
  const withoutDuplicate = read().filter((item) => item.id !== entry.id);
  write([entry, ...withoutDuplicate]);
}

/** Drops an id that the backend genuinely no longer has (a real 404) — not an error, just pruning a stale pointer. */
export function forgetMission(id: string): void {
  write(read().filter((item) => item.id !== id));
}
