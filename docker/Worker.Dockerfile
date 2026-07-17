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
COPY --chown=proofstack:proofstack examples ./examples
RUN mkdir -p /var/lib/proofstack/artifacts /var/lib/proofstack/workspaces \
    && chown -R proofstack:proofstack /var/lib/proofstack

USER 10001:10001
HEALTHCHECK --interval=20s --timeout=3s --start-period=15s --retries=5 \
    CMD ["python", "-c", "import os; os.kill(1, 0)"]
CMD ["proofstack-worker"]
