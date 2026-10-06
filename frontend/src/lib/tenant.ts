/**
 * A locally remembered tenant id, entered by the person using the app, never invented here.
 *
 * The backend has no endpoint that lists a signed-in user's tenants (`docs/13` section 5): a user who
 * belongs to more than one must name one via `X-Tenant-Id`, and the only way this app can learn a real
 * id is if the person types one they already know (from whoever provisioned their membership). This
 * is remembered per account in this browser purely so they do not retype it on every request — it is
 * never treated as authorization by itself: every request still goes to the backend, which is the only
 * thing that decides whether that id is real and whether this user belongs to it.
 *
 * It is kept under the signed-in user's id (`lib/signed-in-user.tsx`, D-249): another account on the
 * same browser has its own, so it never sends this one's workspace (which the backend would answer with
 * `404 not_found` on every request), and this one finds its own again after signing back in.
 */

const STORAGE_PREFIX = "eidos.tenantId:";
/** Before D-249 one id was kept for every account on the browser. It may be another account's, so it is never read, only removed. */
const UNKEYED_STORAGE_KEY = "eidos.tenantId";

function storageKey(userId: string): string {
  return `${STORAGE_PREFIX}${userId}`;
}

export function getStoredTenantId(userId: string): string | null {
  if (typeof window === "undefined") return null;
  try {
    window.localStorage.removeItem(UNKEYED_STORAGE_KEY);
    return window.localStorage.getItem(storageKey(userId));
  } catch {
    return null;
  }
}

export function setStoredTenantId(userId: string, tenantId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(storageKey(userId), tenantId);
  } catch {
    // Storage may be unavailable (private browsing, quota); the app still works, it just re-asks.
  }
}
