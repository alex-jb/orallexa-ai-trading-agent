# ── Orallexa API Server (multi-stage) ────────────────────────────
# Stage 1: Build native dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements-docker.txt

# Stage 2: Production runtime (no compiler)
FROM python:3.11-slim

WORKDIR /app

# Copy only installed packages from builder (no gcc/g++ in final image)
COPY --from=builder /install /usr/local

# App code
COPY engine/ engine/
COPY llm/ llm/
COPY core/ core/
COPY skills/ skills/
COPY models/ models/
COPY bot/ bot/
COPY portfolio/ portfolio/
COPY rag/ rag/
COPY eval/ eval/
COPY api_server.py .
COPY app.py .
COPY app_ui.py .

# Ensure data dirs exist and grant ownership to the non-root runtime user
RUN mkdir -p memory_data results logs rag_data \
    && adduser --disabled-password --gecos "" --uid 10001 orallexa \
    && chown -R orallexa:orallexa /app

USER orallexa

EXPOSE 8002

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8002/healthz', timeout=3).status == 200 else 1)" || exit 1

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8002"]
