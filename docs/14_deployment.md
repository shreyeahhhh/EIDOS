# 14. Deployment (V1.6)

**Status:** DERIVED. Docker and Render/Vercel configuration built and verified by static inspection
(no Docker installed in the build environment; Render performs the actual container build). Live
deployment itself is the owner's own action (Render/Vercel account access), not something built here.
No EIDOS core, contract or API change. D-235 (Groq), D-236 (guard tests) are separate records.

## 14.1 Target architecture

```
        USER
          │
          ▼
      VERCEL
     Next.js (frontend/)
          │
          │ server-side proxy (app/api/eidos/[...path]/route.ts) — no CORS, no direct browser→backend call
          ▼
      RENDER
     FastAPI (this repo's root, Dockerfile)
          │
   ┌──────┴───────┐
   ▼               ▼
SUPABASE        GROQ
PostgreSQL      (production model provider — D-235)
```

Ollama stays local-development-only (nothing about it changes); it is not deployed anywhere. Nothing
new is added beyond what D-235 already built: the same `ModelPort` boundary, a second adapter.

## 14.2 Backend — Docker + Render

`Dockerfile` (repository root) builds a single-stage `python:3.12-slim` image: installs `.[api,postgres]`
only (never the `dev` extras — no pytest, no langgraph, no a2a in production), runs as a non-root user,
and its one `CMD` applies pending migrations (`python -m eidos.persistence.migrate` — idempotent, safe on
every restart) then execs `uvicorn eidos.api.main:create_app_from_environment --factory`, bound to
Render's `$PORT`. `.dockerignore` denies everything except `pyproject.toml`, `README.md` and `src/` — the
frontend, tests, docs and every `.env*` file are structurally unable to reach the image.

`render.yaml` is a Render Blueprint: point Render at this repository and it configures the service from
this file. Every real value (`sync: false` in the file) is entered once, by hand, in Render's own
dashboard — never in git.

**Critical, architectural:** the runtime's `RunManager` assumes exactly one process per database
(decisions.md D-234 — "multi-instance operation needs leases and heartbeats, which are deferred").
**Do not** enable autoscaling or raise this service above 1 instance; nothing in the runtime is safe
for two processes to share one database concurrently. `render.yaml` relies on Render's own default
(1 instance, autoscaling off) rather than asserting a specific Blueprint key for this, to avoid getting
a Render-specific field wrong; verify it in the dashboard after the first deploy.

## 14.3 Environment variables

**Public, frontend-only** (safe in the browser; `NEXT_PUBLIC_*`, inlined at build time):

| Variable | Set in |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Vercel |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` (the anon/publishable key — never the service-role key) | Vercel |

**Server-only, frontend** (never sent to the browser; read only by `app/api/eidos/[...path]/route.ts`):

| Variable | Set in |
|---|---|
| `EIDOS_API_BASE_URL` | Vercel — the Render service's public URL, once known |

**Backend** (`eidos.api.main`; see `docs/13_product_backend.md` section 12.3 for the full, unchanged list):

| Variable | Category | Set in |
|---|---|---|
| `EIDOS_DATABASE_URL` | secret (embeds the Postgres password) | Render |
| `EIDOS_JWKS_URL` | not secret (a public discovery URL) but real per-project | Render |
| `EIDOS_AUTO_PROVISION_WORKSPACES` | config (`true` in `render.yaml`; D-237) | Render |
| `EIDOS_ALLOWED_ACTIONS` | config (`web_fetch` in `render.yaml` turns the web-reading tool on; D-238, `docs/15`) | Render |
| `EIDOS_MODEL_PROVIDER` | config (`groq` in production) | Render |
| `EIDOS_MODEL_BASE_URL` | config (`https://api.groq.com/openai/v1` in production) | Render |
| `GROQ_API_KEY` | **secret** | Render — entered directly in Render's dashboard, never in this repository, never in a commit, never pasted into chat |
| `EIDOS_MODEL_NAME`, `_TEMPERATURE`, `_SEED`, `_MAX_OUTPUT_TOKENS`, `_TIMEOUT_SECONDS` | config | Render |

No backend secret is ever `NEXT_PUBLIC_*`; no frontend file imports anything from `eidos.*`; the two
runtimes share nothing but the deployed backend's public HTTPS URL.

## 14.4 Database migrations

Unchanged from `docs/13` section 12.3: plain, versioned SQL, applied by `eidos.persistence.migrate`
(idempotent — a transaction-level advisory lock and a per-version skip check), now run automatically as
the first half of the container's own `CMD` before every start. A fresh production database (this
project's `eidos` schema, currently absent — see V1.5-C's closeout) is created by the first deploy's
first migration run, from nothing.

## 14.5 Frontend — Vercel

No code change (`frontend/README.md`'s own account already holds — no hardcoded `localhost`, everything
environment-driven). Steps: import this repository into Vercel, set **Root Directory** to `frontend`
(it is a subdirectory, not the repository root), set the three variables above, deploy. Vercel's own
production cookies are HTTPS-only by default, matching `@supabase/ssr`'s expectations with no extra
configuration.

### Sign-up and workspaces (D-237)

The app has `/signup`. To let people use it, in the Supabase dashboard (the owner's settings, not made by this repository):

1. **Authentication → Providers → Email:** sign-ups enabled, and **Confirm email kept ON** (a session is only issued after the address is confirmed).
2. **Authentication → URL Configuration:** set **Site URL** to the Vercel URL and add `https://<your-vercel-domain>/auth/callback` (and `http://localhost:3000/auth/callback` for local work) to **Redirect URLs**.
3. Keep `EIDOS_AUTO_PROVISION_WORKSPACES=true` on Render: the first request from a new account then creates their own workspace. Existing accounts keep the workspace they already have.

Known limit: there is no per-user rate limit, quota or billing. Anyone who can sign up can start missions on the deployment's Groq key, bounded only by the per-tenant active-run limit, the queue cap and the request ceilings — watch Groq usage, and rotate or remove the setting if it is abused.

### Reading web pages (D-238)

With `EIDOS_ALLOWED_ACTIONS=web_fetch` the backend can read the public `https` pages a mission's goal names (see `docs/15_web_fetch.md` for what it will and will not fetch). It needs outbound HTTPS and DNS from Render, nothing else, and no secret. The mission form's "Let EIDOS read the web pages named in my goal" option asks for it per mission.

## 14.6 Production model provider

**Groq**, not Ollama (D-235): Render cannot reasonably host Ollama itself (real RAM/disk for model
weights; not a typical web service), so production inference goes through Groq's hosted,
OpenAI-compatible API instead. This was a full architectural addition (a second `ModelPort` adapter),
not a deployment hack — see decisions.md D-235 for the complete account. Ollama remains exactly what it
was: the local-development adapter, unused and untouched in production.

**Choosing the Groq model, and what a refusal means.** `EIDOS_MODEL_NAME` must be a current Groq model id; none is assumed anywhere in this repository. Groq retires models on a published schedule (`https://console.groq.com/docs/deprecations`). A retired or inaccessible one is refused with `404 The model … does not exist or you do not have access to it`, which a failed mission now shows word for word (D-242). Groq's deprecation list gave `llama-3.3-70b-versatile` a shutdown date of 2026-08-16 (replacement `openai/gpt-oss-120b`), and Groq itself refused it for the owner on 2026-10-02. To see the ids an account may use, from the machine that holds the key (the key is read from the environment and never printed):

```powershell
(Invoke-RestMethod https://api.groq.com/openai/v1/models -Headers @{ Authorization = "Bearer $env:GROQ_API_KEY"; "User-Agent" = "EIDOS" }).data.id | Sort-Object
```

**Rate limits (D-244).** A `429 … tokens per minute (TPM): Limit 8000, Used …, Requested …` means the account's tier allows only that many tokens a minute (a free `on_demand` account: 8,000 for `openai/gpt-oss-120b` at the time of writing). The adapter waits as long as Groq says (up to 30 s a time, at most 3 retries, always inside the call's timeout) and asks again, so a mission slows down instead of failing; if the limit does not lift, the failure carries Groq's own numbers. Groq counts the *maximum output tokens* you allow toward "Requested", so a large `EIDOS_MODEL_MAX_OUTPUT_TOKENS` spends the minute faster than the answers need — keep it as small as the model can still answer in (a reasoning model needs room to think). A free tier will always be slow for a multi-call mission; production wants a paid tier.

Other refusals read the same way: `401 Invalid API Key` is the key; `404 Unknown request URL: POST /chat/completions` is a base URL missing `/openai/v1`. A reasoning model (`openai/gpt-oss-*`) spends output tokens thinking before it answers, so leave `EIDOS_MODEL_MAX_OUTPUT_TOKENS` generous (4096 or more) if a call ends at the output limit with no answer; and Groq's per-minute token allowances differ by account tier, so a fetched page that is large for the tier may be refused as too large — the message will say. **Not verified:** a successful completion from any Groq model with this adapter (no key was used here); the opt-in `python -m pytest -m groq tests/integration/providers/test_groq_real.py` (with `GROQ_API_KEY` and `EIDOS_REAL_GROQ_MODEL` set) is the check.

## 14.7 Known deployment limitations (stated, not hidden)

- **One process only.** See 14.2. A second Render instance pointed at the same database is not safe.
- **`/v1/healthz` is liveness, not readiness.** It does not check database connectivity (documented,
  intentional — `docs/13` section 7: "readiness is a deployment concern"). A healthy process can still
  fail real requests if the database is unreachable; monitor actual request outcomes too, not only this
  check.
- **Render's free tier spins down when idle.** Architecturally safe (a restart's own startup recovery
  marks any interrupted run `interrupted`, never fabricates a result — D-234) but slow to wake; a cost
  decision for the owner, not addressed here.
- **This container was never built with a local `docker build`** — no Docker is installed in this
  environment. It was verified by careful reading against the real `pyproject.toml` and entrypoint, not
  by a real local build. Render performs the first real build.
- **No separate staging environment.** Production points at the same real Supabase project already used
  throughout V1.5's development and QA (with a freshly re-created, empty `eidos` schema — the earlier QA
  schema was fully dropped, decisions.md's V1.5-C record).
