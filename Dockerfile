# ── Orallexa API Server ──────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps for building native packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

# Python deps (docker-specific, no desktop GUI packages)
COPY requirements-docker.txt .
RUN pip install --no-cache-dir -r requirements-docker.txt

# App code
COPY . .

# Ensure data dirs exist
RUN mkdir -p memory_data results logs

EXPOSE 8002

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/api/profile')" || exit 1

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8002"]
