/**
 * A locally remembered tenant id, entered by the person using the app, never invented here.
 *
 * The backend has no endpoint that lists a signed-in user's tenants (`docs/13` section 5): a user who
 * belongs to more than one must name one via `X-Tenant-Id`, and the only way this app can learn a real
 * id is if the person types one they already know (from whoever provisioned their membership). This
 * is remembered per browser purely so they do not retype it on every request — it is never treated as
 * authorization by itself: every request still goes to the backend, which is the only thing that
 * decides whether that id is real and whether this user belongs to it.
 */

const STORAGE_KEY = "eidos.tenantId";

export function getStoredTenantId(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredTenantId(tenantId: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, tenantId);
  } catch {
    // Storage may be unavailable (private browsing, quota); the app still works, it just re-asks.
  }
}

/**
 * Forgets the remembered id. Called on sign-out (`components/site/sign-out-button.tsx`): the id belongs
 * to the account that entered it, and the browser may be shared — left behind, it would be sent as the
 * next account's `X-Tenant-Id`, and the backend answers a tenant that account is not a member of with
 * `404 not_found` on every request.
 */
export function clearStoredTenantId(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable means nothing was remembered either.
  }
}
