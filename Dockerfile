# ---- Stage 1: produce the Reflex frontend static export ----
FROM python:3.12.10-slim-bookworm AS builder
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates unzip unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Reflex reads this at export time and bakes it into the browser bundle.
ARG REFLEX_API_URL=http://localhost:8080
ENV REFLEX_API_URL=$REFLEX_API_URL
RUN reflex export --frontend-only --no-zip

# ---- Stage 2: runtime image ----
FROM python:3.12.10-slim-bookworm
ARG REFLEX_API_URL=http://localhost:8080
ARG CADDY_VERSION=2.11.3

# Microsoft ODBC Driver 18 for Debian 12, plus procps for the explicit
# container-supervision validation (pkill) in H64.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates gnupg2 procps \
    && curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
         | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && curl -o /etc/apt/sources.list.d/mssql-release.list \
         https://packages.microsoft.com/config/debian/12/prod.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends \
         msodbcsql18 unixodbc-dev

RUN curl -fsSL -o /tmp/caddy.tar.gz \
      "https://github.com/caddyserver/caddy/releases/download/v${CADDY_VERSION}/caddy_${CADDY_VERSION}_linux_amd64.tar.gz" \
    && tar -xzf /tmp/caddy.tar.gz -C /usr/local/bin caddy \
    && rm /tmp/caddy.tar.gz \
    && chmod +x /usr/local/bin/caddy \
    && apt-get purge -y --auto-remove curl gnupg2 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin lucidpm
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python -m compileall -q .

COPY --from=builder /app/.web/build/client ./.web/build/client
COPY Caddyfile ./Caddyfile
COPY entrypoint.sh ./entrypoint.sh

RUN chown -R lucidpm:lucidpm /app && chmod +x ./entrypoint.sh
USER lucidpm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LUCIDPM_ENV=cloud \
    REFLEX_API_URL=$REFLEX_API_URL

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/ping').status==200 else 1)"

CMD ["/bin/bash", "/app/entrypoint.sh"]
