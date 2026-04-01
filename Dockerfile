# ── Orallexa API Server ──────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Remove desktop agent deps that won't work in container
# (sounddevice, pystray, pygame, keyboard need display)

EXPOSE 8002

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8002"]
