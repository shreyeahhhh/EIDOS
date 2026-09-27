import { NextResponse, type NextRequest } from "next/server";

import { getAccessToken } from "@/lib/supabase/server";
import type { ApiErrorEnvelope } from "@/lib/api/types";

/**
 * The only bridge between the browser and FastAPI. It runs on this app's own server, so the browser
 * never needs FastAPI's origin and no CORS is added there (the approved architecture). It forwards
 * the signed-in visitor's own Supabase access token as `Authorization: Bearer <token>` — nothing more
 * privileged ever passes through here, and `EIDOS_API_BASE_URL` (backend-only, never `NEXT_PUBLIC_*`)
 * never reaches client-side code.
 *
 * This proxy adds no logic of its own: FastAPI's status code, body and the one error shape
 * (`{"error": {...}}`) pass through untouched, so the typed client's error handling stays exactly the
 * backend's contract.
 */

function unauthenticated(): NextResponse<ApiErrorEnvelope> {
  return NextResponse.json(
    { error: { code: "unauthenticated", message: "Sign in to continue." } },
    { status: 401, headers: { "WWW-Authenticate": "Bearer" } },
  );
}

function backendUnavailable(): NextResponse<ApiErrorEnvelope> {
  return NextResponse.json(
    { error: { code: "storage_unavailable", message: "The service could not be reached right now." } },
    { status: 503 },
  );
}

async function forward(request: NextRequest, segments: string[]): Promise<NextResponse> {
  const baseUrl = process.env.EIDOS_API_BASE_URL;
  if (!baseUrl) {
    console.error("EIDOS_API_BASE_URL is not configured; the frontend cannot reach the backend.");
    return backendUnavailable();
  }

  const path = segments.map(encodeURIComponent).join("/");
  const isHealthz = segments.length === 1 && segments[0] === "healthz";

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  const tenantId = request.headers.get("x-tenant-id");
  if (tenantId) headers.set("x-tenant-id", tenantId);
  const idempotencyKey = request.headers.get("idempotency-key");
  if (idempotencyKey) headers.set("idempotency-key", idempotencyKey);

  if (!isHealthz) {
    const accessToken = await getAccessToken();
    if (!accessToken) return unauthenticated();
    headers.set("authorization", `Bearer ${accessToken}`);
  }

  const targetUrl = `${baseUrl.replace(/\/$/, "")}/v1/${path}${request.nextUrl.search}`;
  const hasBody = request.method !== "GET" && request.method !== "HEAD";

  let upstream: Response;
  try {
    upstream = await fetch(targetUrl, {
      method: request.method,
      headers,
      body: hasBody ? await request.arrayBuffer() : undefined,
      cache: "no-store",
    });
  } catch (error) {
    console.error("EIDOS backend request failed", error);
    return backendUnavailable();
  }

  const responseHeaders = new Headers();
  const upstreamContentType = upstream.headers.get("content-type");
  if (upstreamContentType) responseHeaders.set("content-type", upstreamContentType);
  const wwwAuthenticate = upstream.headers.get("www-authenticate");
  if (wwwAuthenticate) responseHeaders.set("www-authenticate", wwwAuthenticate);

  const body = await upstream.arrayBuffer();
  return new NextResponse(body, { status: upstream.status, headers: responseHeaders });
}

type RouteContext = { params: Promise<{ path: string[] }> };

export async function GET(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return forward(request, path);
}

export async function POST(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return forward(request, path);
}
