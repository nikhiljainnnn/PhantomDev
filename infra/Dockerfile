# Stage 1: Python deps builder
FROM python:3.11-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends build-essential git && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Frontend builder
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY frontend/package.json ./
RUN npm install --silent
COPY frontend/ .
RUN npm run build

# Stage 3: Production runtime
FROM python:3.11-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git curl && rm -rf /var/lib/apt/lists/*
COPY --from=builder /install /usr/local
COPY --from=frontend-builder /app/dist /app/frontend/dist
COPY orchestrator/ ./orchestrator/
COPY agents/ ./agents/
COPY api/ ./api/
COPY worker/ ./worker/
COPY evaluation/ ./evaluation/
COPY tools/ ./tools/
COPY scripts/ ./scripts/
RUN useradd -m -u 1001 phantomdev && mkdir -p workspace sandbox data/chroma && chown -R phantomdev:phantomdev /app
USER phantomdev
EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--log-level", "info"]
