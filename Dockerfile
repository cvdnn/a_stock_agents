# ==============================================================================
# A-Stock Agents Production Dockerfile
# Multi-Agent Quantitative Research & Decision System for A-Shares
# ==============================================================================

FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    A_STOCK_AGENTS_ROOT=/app \
    A_STOCK_SERVER_HOST=0.0.0.0 \
    A_STOCK_SERVER_PORT=6300 \
    PYTHONPATH="/app/scripts:/app"

WORKDIR /app

# Install system dependencies (curl for healthchecks, ca-certificates for HTTPS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency specifications first to leverage Docker layer caching
COPY requirements.txt pyproject.toml ./

# Install Python dependencies
# You can append -i https://pypi.tuna.tsinghua.edu.cn/simple for faster build in mainland China
ARG PIP_INDEX_URL=""
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; \
    else \
        pip install --no-cache-dir -r requirements.txt; \
    fi

# Create non-root user and setup directories
RUN useradd -m -u 1000 -s /bin/bash appuser && \
    mkdir -p /app/output /app/config /app/reports /app/backups && \
    chown -R appuser:appuser /app

# Copy application files
COPY --chown=appuser:appuser AGENTS.md README.md ./
COPY --chown=appuser:appuser bin ./bin
COPY --chown=appuser:appuser config ./config
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser web ./web
COPY --chown=appuser:appuser .agents ./.agents
COPY --chown=appuser:appuser docker-entrypoint.sh ./docker-entrypoint.sh

RUN chmod +x ./docker-entrypoint.sh ./bin/astock

# Switch to non-root user
USER appuser

EXPOSE 6300

# Healthcheck monitoring the /api/health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:6300/api/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD []
