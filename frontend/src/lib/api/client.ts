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

async function request<T>(path: string, init: RequestInit, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const tenantId = options.tenantId ?? getStoredTenantId();
  if (tenantId) headers.set("X-Tenant-Id", tenantId);
  if (options.idempotencyKey) headers.set("Idempotency-Key", options.idempotencyKey);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");

  const response = await fetch(`/api/eidos${path}`, { ...init, headers });
  if (!response.ok) {
    throw await toApiError(response);
  }
  return (await response.json()) as T;
}

export function createMission(spec: MissionSpec, options: RequestOptions = {}): Promise<CreatedMission> {
  return request<CreatedMission>("/missions", { method: "POST", body: JSON.stringify(spec) }, options);
}

export function startMission(missionId: string, options: RequestOptions = {}): Promise<StartedMission> {
  return request<StartedMission>(`/missions/${missionId}/start`, { method: "POST" }, options);
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
