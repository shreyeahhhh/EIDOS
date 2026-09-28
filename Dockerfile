# EIDOS backend (eidos.api) — production image. Built and run by Render; not validated with a local
# `docker build` in this environment (no Docker installed here — see progress.md, V1.6).
#
# Single stage: psycopg[binary] ships prebuilt wheels and eidos has no C extension of its own, so no
# build toolchain is needed at runtime. The frontend (frontend/) is deployed separately, to Vercel; it
# has no Dockerfile, and the build context below never includes it (.dockerignore).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# setuptools needs pyproject.toml's declared readme to exist to build the package; src/ is the package
# itself. Nothing else (tests/, docs/, frontend/, decisions.md, .env*) is copied in — .dockerignore
# denies everything not explicitly needed, so no secret, dev file or local path can reach the image.
COPY pyproject.toml README.md ./
COPY src ./src

# Only the extras a running server needs: the HTTP boundary (api) and PostgreSQL (postgres). Never the
# dev group — no pytest, no langgraph, no a2a in the production image.
RUN pip install --no-cache-dir ".[api,postgres]"

# A non-root runtime user (defence in depth; the process itself opens no file and writes nothing local).
RUN useradd --create-home --uid 10001 eidos
USER eidos

EXPOSE 8000
# Render sets $PORT at runtime; 8000 is only the fallback for a manual `docker run` elsewhere.
ENV PORT=8000

# Configuration is entirely the environment (eidos.api.main; D-233/D-234) — nothing is baked in here,
# and a missing or malformed variable stops the process before it serves anything, naming the variable,
# never a value. Migrations are idempotent (a transaction-level advisory lock, a per-version skip
# check — eidos.persistence.migrate) and applying them before every start is exactly docs/13's own
# documented two-step production startup (12.3), now run as the one command a container needs.
CMD ["sh", "-c", "python -m eidos.persistence.migrate && exec uvicorn eidos.api.main:create_app_from_environment --factory --host 0.0.0.0 --port ${PORT}"]
