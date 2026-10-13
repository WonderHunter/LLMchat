# syntax=docker/dockerfile:1

# --- Interface : compilée puis copiée dans l'image finale -----------------------------
FROM node:22-slim AS frontend
WORKDIR /app/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# --- Application : le backend sert l'API et l'interface compilée ----------------------
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.28 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --locked --no-dev
COPY backend/app ./app
COPY --from=frontend /app/frontend/dist /app/frontend/dist

# La base SQLite vit dans un volume, hors de l'image.
RUN useradd --no-create-home --uid 10001 llmchat && mkdir /data && chown llmchat /data
USER llmchat
ENV DATABASE_URL=sqlite:////data/llmchat.db
VOLUME /data

EXPOSE 8642
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
    CMD ["/app/backend/.venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8642/api/health', timeout=4)"]

# --proxy-headers : l'adresse du visiteur vient du reverse proxy (X-Forwarded-For), sans quoi
# la limitation des tentatives de connexion verrait tout le monde sous la même adresse.
# N'exposer ce port qu'au reverse proxy, jamais directement à Internet.
CMD ["/app/backend/.venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8642", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
