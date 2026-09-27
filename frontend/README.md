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

## Layout

```
src/
  app/
    page.tsx                     landing / product explanation
    login/page.tsx                Supabase email+password sign-in
    missions/new/page.tsx          mission creation (protected)
    api/eidos/[...path]/route.ts   the server-side proxy to FastAPI
  components/
    ui/                           shared primitives (Button, Card, Badge, Field, Callout, Skeleton)
    site/                         header/footer, sign-out
    auth/                         the login form
    mission/                      the mission-creation form
  lib/
    supabase/                     browser and server Supabase clients
    api/                          typed client, hand-written types mirroring the backend, ApiError
    status.ts, tenant.ts, cn.ts
  proxy.ts                        session refresh + route protection (Next's "proxy"/middleware convention)
```

## What this is, and is not

- **Authentication is real Supabase Auth** (`@supabase/ssr`), not a local or fake replacement. There
  is no demo user and no hard-coded tenant anywhere in this app.
- **No CORS is added to the FastAPI backend.** The browser only ever calls this app's own origin
  (`/api/eidos/...`); the server-side proxy is what talks to FastAPI, so `EIDOS_API_BASE_URL` and the
  access token never reach client-side code.
- **There is no list-missions endpoint on the backend** (deliberately out of scope for V1.4). A
  mission dashboard that lists a tenant's missions (V1.5-B) will need a client-side "recently created"
  index (e.g. `localStorage`) or a future backend endpoint — a product decision for the owner, not
  decided here. Every individual mission's state is still always read live from the backend by id.
- **`required_capabilities`' four values** (`research`, `architecture`, `security`, `cost`) are fixed
  by which agents this backend build wires up (`KNOWN_CAPABILITIES` in `lib/api/types.ts`), not a
  platform-wide, discoverable vocabulary. Update that constant by hand if the backend's agents change.
- **`allowed_actions`' real vocabulary is operator configuration** on the backend
  (`EIDOS_ALLOWED_ACTIONS`) and defaults to empty; the mission-creation form does not expose it and
  always sends `[]`.
- **No "strategy" is ever shown**, because the backend never exposes one (candidate generation and
  selection are not recorded events). What V1.5-B can show is the executed *plan* and, across a
  replan, why the previous one was abandoned — never which strategies were considered.
- **The evidence view is honestly empty** in this deployment: no knowledge base is configured, so
  every citation reads `not_evidence`. This is a documented backend limitation (V1.4-C), not a bug
  here, and nothing in this app claims otherwise.

## Status (V1.5-A)

Foundation, design system, typed API client, real Supabase auth integration (login/logout/session
refresh/route protection), and mission creation are built and verified:

- `npm run typecheck`, `npm run lint`, `npm run test` (15 tests) all pass.
- `npm run build` succeeds (verified locally with placeholder Supabase values; a real project is
  needed for it to mean anything at runtime).
- The server-side proxy was exercised against a **real** local FastAPI instance over a **real**
  disposable PostgreSQL (not a mock): `GET /api/eidos/healthz` round-trips correctly, and a protected
  path with no session correctly short-circuits to `401 unauthenticated` (`WWW-Authenticate: Bearer`)
  without even reaching FastAPI.
- **The whole real-auth chain was then exercised for real** (2026-09-27), against the owner's actual
  Supabase project and a local FastAPI instance configured with its real `EIDOS_JWKS_URL`, over the
  same disposable PostgreSQL: the owner signed in with a real account through the real login form;
  the session persisted across a full page reload; sign-out revoked access (a direct request to a
  protected route redirected back to `/login`); the account had no `tenant_members` row yet, and the
  app correctly showed the "no workspace access" state instead of pretending otherwise (`403
  no_tenant_membership`, exactly as documented); a test membership row was then inserted directly into
  the local disposable database (never Supabase, which holds no such table) for that account's real
  user id, read from its own already-authenticated session (never requested from Supabase with an
  elevated credential); after that, mission creation succeeded for real — the created `mission_id`,
  `tenant_id` and `created_by` all match what is in the database — and starting it ran the mission to
  a real, recorded outcome (`MISSION_CREATED` → `PLAN_GENERATED` → `PLAN_COMPILED` → `NODE_STARTED` →
  two `NODE_SETTLED` → `MISSION_FAILED`, because no real model provider was configured for this local
  smoke test — an honest failure, not a defect). Every item of the "real auth verification" checklist
  holds.
- **Not exercised**: anything against a real production Postgres or a deployed backend (only a local,
  disposable one was used); a real model provider (V1.4's own limitation, unrelated to the frontend).

V1.5-B (dashboard, execution timeline, plan/evidence/result views) and V1.5-C (hardening + closeout)
have not been started.
