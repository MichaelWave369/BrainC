# BrainC — Multi-stage production Dockerfile
# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY api/requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.11-slim AS runtime

# Non-root user
RUN groupadd -r braincbrain && useradd -r -g braincbrain -d /app -s /bin/false braincbrain

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application
COPY api/ ./api/
COPY model/ ./model/
COPY scripts/ ./scripts/
COPY ui/ ./ui/

# Create required directories
RUN mkdir -p memory workspace/notes logs backups \
    && chown -R braincbrain:braincbrain /app

USER braincbrain

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
