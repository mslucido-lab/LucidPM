# Deployment

## Current state

LucidPM has a Docker image definition for local container validation. The image uses ODBC Driver 18 and the contained Azure SQL user, with Caddy serving the compiled frontend on port 8080 and proxying Reflex's backend, WebSocket, health, upload, and `/api/*` routes to its loopback-only port 8000. The image has not been pushed to a registry and no Azure Container App exists yet.

## Containerization

Build the local image with the browser-facing API URL baked into the frontend bundle:

```powershell
docker build --build-arg REFLEX_API_URL=http://localhost:8080 -t lucidpm:dev .
```

Run it against Azure SQL with the ignored `.env.docker` file. That file supplies SQL authentication and the Fernet key without adding secrets to the image or command history:

```powershell
docker run --env-file .env.docker -p 8080:8080 lucidpm:dev
```

The build is local-only for Cycle 3.1. Publishing to GHCR, Azure Container Apps ingress, and Microsoft Entra authentication belong to Cycle 3.2 and later. The compiled frontend currently uses an absolute API URL, so Cycle 3.2 must either rebuild per deployment URL or validate a same-origin URL strategy.

## Known blockers for cloud hosting

- Local disk paths for document storage (`C:\Dell Inspirion\TenantCRM\LeaseDocuments\...`) are not a cloud storage strategy.
- ~~The Fernet key for config secrets was stored in `dbo.AppSettings` alongside the ciphertext it protects~~ — moved to the `LUCIDPM_FERNET_KEY` environment variable and rotated in Handoff 63.

The interactive Windows file picker was retired in Cycle 0.2 / Handoff 62.
