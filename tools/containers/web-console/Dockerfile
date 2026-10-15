# Optional Web-console development/debug image, not a skill Release.
FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    A_STOCK_WORKSPACE_ROOT=/data \
    A_STOCK_SERVER_HOST=0.0.0.0 A_STOCK_SERVER_PORT=6300 \
    PYTHONPATH=/app/skill_bundle/runtime:/app/apps/web-console/backend:/app
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
ARG PIP_INDEX_URL=""
RUN if [ -n "$PIP_INDEX_URL" ]; then \
        pip install --no-cache-dir -i "$PIP_INDEX_URL" -r requirements.txt; \
    else pip install --no-cache-dir -r requirements.txt; fi
RUN useradd -m -u 1000 -s /bin/bash appuser \
    && mkdir -p /data/output /data/local /data/log /data/temp \
    && chown -R appuser:appuser /data /app
COPY --chown=appuser:appuser skill_bundle ./skill_bundle
COPY --chown=appuser:appuser apps/web-console ./apps/web-console
COPY --chown=appuser:appuser tools/containers/web-console/entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh
USER appuser
EXPOSE 6300
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl -f http://127.0.0.1:6300/api/health || exit 1
ENTRYPOINT ["./entrypoint.sh"]
