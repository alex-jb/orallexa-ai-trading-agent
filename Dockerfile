# ── Orallexa API Server (multi-stage) ────────────────────────────
# Stage 1: Build native dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

COPY requirements-docker.txt .
RUN pip install --no-cache-dir --prefix=/install --extra-index-url https://download.pytorch.org/whl/cpu -r requirements-docker.txt

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

# Ensure data dirs exist
RUN mkdir -p memory_data results logs rag_data

EXPOSE 8002

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Add non-root user
RUN adduser --disabled-password --gecos "" orallexa
USER orallexa

# New curl-based healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD curl -fsS http://localhost:8002/healthz || exit 1

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8002"]
