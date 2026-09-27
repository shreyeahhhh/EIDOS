# EIDOS frontend

The first user-facing surface of EIDOS (V1.5). A Next.js (App Router) + TypeScript + Tailwind CSS
application that talks to the existing FastAPI backend (`docs/13_product_backend.md` in the repository
root) through this app's own server-side layer — never directly from the browser.

```
Browser → Next.js (this app) → server-side proxy → FastAPI (EIDOS backend) → PostgreSQL
                ↑
          Supabase Auth (session cookies, via @supabase/ssr)
```

The backend remains authoritative for everything: mission validation, tenant membership, execution,
verification. This app never re-implements any of that; it only renders what the backend returns and
forwards the signed-in visitor's own Supabase access token as `Authorization: Bearer <token>`.

## Setup

1. `npm install`
2. Copy `.env.local.example` to `.env.local` and fill in real values:
   - `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` — from the real Supabase
     project's API settings (its publishable/anon key; never the service-role key).
   - `EIDOS_API_BASE_URL` — where the FastAPI backend is reachable from this app's server (not from
     the browser). See `docs/13_product_backend.md` section 12.3 in the repository root for how to run
     it locally (`uvicorn eidos.api.main:create_app_from_environment --factory`), including
     `EIDOS_JWKS_URL`, which must point at the *same* Supabase project as above so the backend can
     verify the tokens this app forwards to it.
3. `npm run dev` and open `http://localhost:3000`.

`.env.local` is git-ignored; never commit a real value into `.env.local.example`.

## Scripts

| Command | Does |
|---|---|
| `npm run dev` | Local development server |
| `npm run build` | Production build (also type-checks) |
| `npm run start` | Serve a production build |
| `npm run lint` | ESLint |
| `npm run typecheck` | `tsc --noEmit` |
| `npm run test` | Vitest (unit/component tests, no external dependency) |

## Information architecture

```
/                    landing — the loop, the manifesto
/login               Supabase email+password sign-in
/missions            dashboard — a local navigation index, not a source of truth
/missions/new        mission creation (protected)
/missions/[id]        the mission workspace — ONE page, not five routes or tabs
```

A mission's workspace is a single scrollable document with in-page sections (Timeline, Plan, Result,
Evidence) and an anchor nav, not separate routes: they all derive from data that is cheap to fetch
together, and splitting them would fragment one story into five loading states. `run_status` and
`mission_status` are never merged — `MissionStatusPair` shows RUN and MISSION as two distinct facts
everywhere a mission's state appears.

## Layout

```
src/
  app/
    page.tsx                       landing / product explanation
    login/page.tsx                  Supabase email+password sign-in
    missions/page.tsx               the dashboard (a local navigation index)
    missions/new/page.tsx           mission creation (protected)
    missions/[id]/page.tsx          the mission workspace (protected)
    api/eidos/[...path]/route.ts    the server-side proxy to FastAPI
  components/
    ui/                            shared primitives (Button, Card, Badge, Field, Callout, Skeleton, EmptyState, ErrorState)
    layout/                        PageHeader, Section — the workspace's only structure
    site/                          header/footer, sign-out
    auth/                          the login form
    mission/                       creation form, dashboard, MissionCard, MissionStatusPair, ExecutionMetrics, the workspace itself, and the two shared access states (no-workspace-access, tenant-required)
    execution/                     ExecutionTimeline (plain-language event descriptions, raw payload behind a disclosure)
    plan/                          PlanGraph (a hand-built SVG DAG, no graph library) and ReplanLineage
    evidence/                      EvidencePanel
    result/                        ResultPanel, VerificationPanel, ArtifactCard
  lib/
    supabase/                      browser and server Supabase clients
    api/                           typed client, hand-written types mirroring the backend, ApiError
    mission-index.ts               the dashboard's client-side navigation index (never a source of truth)
    use-api-resource.ts            a small fetch-state hook (loading/not_ready/error/ready)
    use-mission-status.ts          polls a mission's summary only while its run is genuinely active
    status.ts, tenant.ts, cn.ts
  proxy.ts                         session refresh + route protection (Next's "proxy"/middleware convention)
```

## What this is, and is not

- **Authentication is real Supabase Auth** (`@supabase/ssr`), not a local or fake replacement. There
  is no demo user and no hard-coded tenant anywhere in this app.
- **No CORS is added to the FastAPI backend.** The browser only ever calls this app's own origin
  (`/api/eidos/...`); the server-side proxy is what talks to FastAPI, so `EIDOS_API_BASE_URL` and the
  access token never reach client-side code.
- **There is no list-missions endpoint on the backend** (deliberately out of scope for V1.4). The
  dashboard reads a client-side index of ids this browser has created (`lib/mission-index.ts`) and
  fetches each one live — the index is never a second source of truth, only a pointer; a stale id (a
  real `404`) is pruned silently.
- **`required_capabilities`' four values** (`research`, `architecture`, `security`, `cost`) are fixed
  by which agents this backend build wires up (`KNOWN_CAPABILITIES` in `lib/api/types.ts`), not a
  platform-wide, discoverable vocabulary. Update that constant by hand if the backend's agents change.
- **`allowed_actions`' real vocabulary is operator configuration** on the backend
  (`EIDOS_ALLOWED_ACTIONS`) and defaults to empty; the mission-creation form does not expose it and
  always sends `[]`.
- **No "strategy" is ever shown**, because the backend never exposes one (candidate generation and
  selection are not recorded events). The workspace shows the executed *plan* (`PlanGraph`) and, across
  a replan, why the previous one was abandoned (`ReplanLineage`, read from `PLAN_GENERATED` and
  `REPLAN_TRIGGERED` events) — never which strategies were considered. Each plan version keeps its own
  identity; v1 is never visually mutated into v2.
- **The evidence view is honestly empty** in this deployment: no knowledge base is configured, so
  every citation reads `not_evidence`, and `EvidencePanel` states that plainly rather than hiding it.
  This is a documented backend limitation (V1.4-C), not a bug here.
- **Result and Verification are always shown separately** (`ResultPanel`/`VerificationPanel`): an
  artifact existing is never presented as the same fact as it having been verified, and a verdict is
  its own reason text, never a score or a percentage.

## Status

**V1.5-A** (foundation, real Supabase auth, mission creation) and **V1.5-B** (the mission dashboard and
workspace: timeline, plan graph, replan lineage, result, verification, evidence) are both built and
verified. V1.5-C (hardening + closeout) has not started.

- `npm run typecheck`, `npm run lint`, `npm run test` (43 tests) all pass; `npm run build` succeeds.
- **Exercised live in the browser** against the owner's real Supabase project and a real local FastAPI
  instance over a real disposable PostgreSQL (not a mock): sign-in, session persistence across a
  reload, sign-out revoking access, the correct `403 no_tenant_membership` state before a workspace
  existed, mission creation and start succeeding for real (created fields verified against the
  database), a real replan rendered correctly by `ReplanLineage` and `PlanGraph` (a genuinely linear
  plan shape the selector produced, not a contrived example), the dashboard's stale-id pruning, and the
  empty-dashboard and mission-not-found states.
- **Two real defects found this way and fixed:** `PLAN_COMPILED` fell through to a raw label instead of
  "Plan validated" (it shares every field name with other event payloads, so it has no unique key for
  the `in`-based narrowing the rest of the timeline uses, and needs a literal-equality check instead);
  the mobile header had no breathing room between the wordmark and its first nav link at 375px (fixed
  by hiding the secondary "New mission" link below `sm`).
- A discriminated `EventPayload` union with a bare `{ event_type: string }` fallback member defeats
  `switch`/`===` narrowing entirely (TypeScript cannot exclude a non-literal fallback from any case);
  `"field" in payload` narrows correctly instead and is used throughout `execution-timeline.tsx` and
  `replan-lineage.tsx`.
- Two of the new data hooks reset their state via a render-time key comparison (React's documented
  "adjusting state when a prop changes" pattern) rather than a synchronous `setState` call inside an
  effect body, to satisfy the React Compiler-oriented lint rules `eslint-config-next` 16 now ships.
- **Not exercised**: anything against a real production Postgres or a deployed backend (only a local,
  disposable one was used); a real model provider (V1.4's own limitation, unrelated to the frontend).
