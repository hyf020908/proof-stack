# syntax=docker/dockerfile:1.7

FROM python:3.11.11-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /build

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY packages ./packages
RUN python -m pip wheel --wheel-dir /wheels . "psycopg[binary]>=3.2,<4"

FROM python:3.11.11-slim-bookworm AS runtime

ENV PATH=/home/proofstack/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

RUN groupadd --gid 10001 proofstack \
    && useradd --uid 10001 --gid proofstack --create-home --shell /usr/sbin/nologin proofstack
COPY --from=builder /wheels /wheels
RUN python -m pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels
COPY --chown=proofstack:proofstack alembic.ini ./alembic.ini
COPY --chown=proofstack:proofstack migrations ./migrations
COPY --chown=proofstack:proofstack examples ./examples
COPY docker/api-entrypoint.sh /usr/local/bin/proofstack-api-entrypoint
RUN chmod 0555 /usr/local/bin/proofstack-api-entrypoint \
    && mkdir -p /var/lib/proofstack/artifacts /var/lib/proofstack/workspaces \
    && chown -R proofstack:proofstack /var/lib/proofstack

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2).read()"]
ENTRYPOINT ["proofstack-api-entrypoint"]
CMD ["uvicorn", "proofstack_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
