FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
RUN apt-get update \
    && apt-get install --yes --no-install-recommends tar \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir . \
    && groupadd --system --gid 10001 securityops \
    && useradd --system --uid 10001 --gid securityops --no-create-home --shell /usr/sbin/nologin securityops \
    && mkdir -p /var/lib/securityops/documents \
    && chown -R securityops:securityops /var/lib/securityops

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
