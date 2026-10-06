"use client";

import { toApiError } from "./errors";
import { getStoredTenantId } from "../tenant";
import type {
  CreatedMission,
  EvidenceView,
  EventsPage,
  ExecutionRecord,
  MissionResult,
  MissionSpec,
  MissionSummary,
  StartedMission,
  UserModelChoice,
} from "./types";

/**
 * A typed client over the app's own server-side proxy (`app/api/eidos/[...path]/route.ts`), never
 * over FastAPI directly: the browser only ever talks to this app's own origin, so no CORS is needed
 * on the backend, and the Supabase access token never has to reach client-side code to be forwarded.
 */

interface RequestOptions {
  /** Overrides the remembered tenant id for this one call (used by the tenant-selection retry). */
  tenantId?: string;
  idempotencyKey?: string;
}

/** A generous ceiling, not a real deadline: this app's own longest real calls (mission creation,
 * the event log) return in well under this. Its only job is to turn a genuinely stalled connection
 * into a clean, retryable error instead of a spinner that never resolves. */
const REQUEST_TIMEOUT_MS = 30_000;

async function request<T>(path: string, init: RequestInit, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const tenantId = options.tenantId ?? getStoredTenantId();
  if (tenantId) headers.set("X-Tenant-Id", tenantId);
  if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`/api/eidos${path}`, { ...init, headers, signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  } catch (error) {
    // This app's own server proxy already turns "FastAPI unreachable" into a clean `ApiError`
    // (`storage_unavailable`); this catches the layer below that — the request to this app's own
    // origin never completing at all (offline, DNS, a dropped connection, or the timeout above) —
    // and gives it an equally plain message rather than surfacing a raw `TypeError`/`DOMException`.
    // `AbortSignal.timeout()` rejects `fetch` with a `DOMException` named "TimeoutError" — which is
    // not an `instanceof Error` in every environment, so this checks `.name` directly rather than
    // narrowing on `Error` first.
    const timedOut = typeof error === "object" && error !== null && "name" in error && error.name === "TimeoutError";
    throw new Error(timedOut ? "This took too long and was cancelled. Try again." : "Could not reach the server. Check your connection and try again.");
  }
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

export function createMission(spec: MissionSpec, options: RequestOptions = {}): Promise<CreatedMission> {
  return request<CreatedMission>("/missions", { method: "POST", body: JSON.stringify(spec) }, options);
}

/** Starts a run. With `model` the run uses the user's own provider, model and key (D-246): the key travels in the request body only, never in the address. */
export function startMission(missionId: string, options: RequestOptions & { model?: UserModelChoice } = {}): Promise<StartedMission> {
  const { model, ...requestOptions } = options;
  return request<StartedMission>(`/missions/${missionId}/start`, { method: "POST", ...(model ? { body: JSON.stringify({ model }) } : {}) }, requestOptions);
}

export function getMission(missionId: string, options: RequestOptions = {}): Promise<MissionSummary> {
  return request<MissionSummary>(`/missions/${missionId}`, { method: "GET" }, options);
}

export function getExecution(missionId: string, options: RequestOptions = {}): Promise<ExecutionRecord> {
  return request<ExecutionRecord>(`/missions/${missionId}/execution`, { method: "GET" }, options);
}

export function getEvents(
  missionId: string,
  page: { after?: number; limit?: number } = {},
  options: RequestOptions = {},
): Promise<EventsPage> {
  const params = new URLSearchParams();
  if (page.after !== undefined) params.set("after", String(page.after));
  if (page.limit !== undefined) params.set("limit", String(page.limit));
  const query = params.toString();
  return request<EventsPage>(`/missions/${missionId}/events${query ? `?${query}` : ""}`, { method: "GET" }, options);
}

export function getResult(missionId: string, options: RequestOptions = {}): Promise<MissionResult> {
  return request<MissionResult>(`/missions/${missionId}/result`, { method: "GET" }, options);
}

export function getEvidence(missionId: string, options: RequestOptions = {}): Promise<EvidenceView> {
  return request<EvidenceView>(`/missions/${missionId}/evidence`, { method: "GET" }, options);
}
