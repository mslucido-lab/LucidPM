# Deployment

## Current state

*(Verified 2026-10-05 via `az containerapp show`.)*

LucidPM runs as the `lucidpm` Azure Container App in `lucido-apps-env` (West US 3, resource group `Lucido-Apps-RG`), using private image `ghcr.io/mslucido-lab/lucidpm:0.4.3` (revision `lucidpm--0000009`). The image uses ODBC Driver 18 and Caddy serves the compiled frontend on port 8080 while proxying Reflex's backend, WebSocket, health, upload, and `/api/*` routes to loopback-only port 8000.

- **URL:** `https://lucidpm.lucidoproperties.net` (custom domain, Azure-managed cert; Cycle 5.4). The original `lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io` address still works.
- **Access:** Microsoft Entra ID built-in auth, single-tenant `lucidpm` app registration with assignment required (Handoff 72). The old IP allowlist was removed; Entra is the only perimeter.
- **Database:** Azure SQL `lucidpm-sql-24899` — `TenantCRM` (Prod) and `TenantCRM_Test`. The Test/Prod toggle is enabled. **Azure SQL is the only database**; the local SQL Server copies are retired (confirmed 2026-10-05).
- **Storage:** generated packages and source/section PDFs live in Azure Blob Storage (H67–H69, H71).
- **Scale:** `minReplicas 0` — scales to zero when idle; a cold request takes up to about a minute.

### Local development uses the same databases

Running the app locally (`reflex run`, configured by the ignored `.env`) connects to the **same** Azure SQL databases as the deployed app, as the least-privilege `lucidpm_app` user. So:

- Develop and test unreleased code with the app toggled to **Test** (`TenantCRM_Test`).
- A schema script takes effect for the deployed app immediately. Keep schema changes additive (new tables/columns) so the currently deployed image keeps working, and apply them before releasing code that depends on them.
- Schema scripts need the SQL admin login (`lucidpm_app` cannot run DDL). The H70 DDL trigger logs them automatically.

## Releasing a new version

Releases are manual — there is no CI. From the repo root in PowerShell, with Docker Desktop running and the release commit checked out on a **clean working tree** (the build copies the working directory, so uncommitted files would ship):

```powershell
# 1. Build. REFLEX_API_URL is baked into the frontend bundle at build time — it is NOT
#    read from the Container App's env vars. Omitting it breaks PDF/download links (H71).
docker build --build-arg REFLEX_API_URL=https://lucidpm.lucidoproperties.net `
  -t ghcr.io/mslucido-lab/lucidpm:<version> .

# 2. Push (docker login ghcr.io first if needed, with a token that has write:packages).
docker push ghcr.io/mslucido-lab/lucidpm:<version>

# 3. Deploy — creates a new revision. Env vars, secrets, auth, domain and scale settings
#    carry over (update merges rather than replaces).
az containerapp update -n lucidpm -g Lucido-Apps-RG --image ghcr.io/mslucido-lab/lucidpm:<version>

# 4. Confirm the new revision is running.
az containerapp revision list -n lucidpm -g Lucido-Apps-RG -o table
```

Then on `https://lucidpm.lucidoproperties.net`: sign in, open a Rent Roll PDF, download a lease package (the links that break if `REFLEX_API_URL` is wrong), and spot-check the changed feature on Test, then Prod.

**Rollback:** re-run step 3 with the previous tag. Before releasing, note the current tag from `az containerapp show -n lucidpm -g Lucido-Apps-RG --query "properties.template.containers[0].image"`.

Up to `0.4.2`, images were built with `REFLEX_API_URL` set to the `*.azurecontainerapps.io` address. Building with the custom domain makes browser API calls same-origin (the Cycle 5.4 optional follow-up).

## Running the image locally

Build with the local browser-facing URL and run it against Azure SQL with the ignored `.env.docker` file, which supplies SQL authentication and the Fernet key without adding secrets to the image or command history:

```powershell
docker build --build-arg REFLEX_API_URL=http://localhost:8080 -t lucidpm:dev .
docker run --env-file .env.docker -p 8080:8080 lucidpm:dev
```

## History

- Local disk paths for document storage were replaced by Azure Blob Storage (H67–H69, H71).
- The Fernet key moved out of `dbo.AppSettings` into the `LUCIDPM_FERNET_KEY` environment variable and was rotated (Handoff 63).
- The interactive Windows file picker was retired (Cycle 0.2 / Handoff 62).
- Gate evidence: `docs/cycle-3.2-validation.md`, `docs/cycle-4.2-validation.md`, `docs/h71-validation.md`.
