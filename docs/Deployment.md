# Deployment

## Current state

LucidPM runs as the `lucidpm` Azure Container App in `lucido-apps-env` (West US 3), using private image `ghcr.io/mslucido-lab/lucidpm:0.1.0`. The image uses ODBC Driver 18 and Caddy serves the compiled frontend on port 8080 while proxying Reflex's backend, WebSocket, health, upload, and `/api/*` routes to loopback-only port 8000.

Ingress is limited to Mark's Office and Home IP addresses; Microsoft Entra authentication is Stage 5.3 work. The temporary deployment is locked to `TenantCRM_Test` via `LUCIDPM_SINGLE_DB`, and scales to zero when idle. A cold request takes about one minute to return usable Test data. See `docs/cycle-3.2-validation.md` for Gate 3 evidence.

## Containerization

Build the local image with the browser-facing API URL baked into the frontend bundle:

```powershell
docker build --build-arg REFLEX_API_URL=http://localhost:8080 -t lucidpm:dev .
```

Run it against Azure SQL with the ignored `.env.docker` file. That file supplies SQL authentication and the Fernet key without adding secrets to the image or command history:

```powershell
docker run --env-file .env.docker -p 8080:8080 lucidpm:dev
```

The production build uses the known Container Apps FQDN as `REFLEX_API_URL`; Cycle 3.2 validated that deployment path. Rebuild with the appropriate browser-facing URL when the Stage 5.4 custom domain is introduced.

## Known blockers for cloud hosting

- Local disk paths for document storage (`C:\Dell Inspirion\TenantCRM\LeaseDocuments\...`) are not a cloud storage strategy.
- ~~The Fernet key for config secrets was stored in `dbo.AppSettings` alongside the ciphertext it protects~~ — moved to the `LUCIDPM_FERNET_KEY` environment variable and rotated in Handoff 63.

The interactive Windows file picker was retired in Cycle 0.2 / Handoff 62.
