# Cycle 3.2 / Gate 3 ? LucidPM on Azure Container Apps

**Goal:** prove the Cycle 3.1 container image works behind real Azure Container Apps ingress, remains limited to `TenantCRM_Test`, wakes from zero replicas, and keeps the Reflex event channel working.

- App: `lucidpm` in resource group `Lucido-Apps-RG`, shared environment `lucido-apps-env` (West US 3).
- Temporary URL: `https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io`.
- Image: private `ghcr.io/mslucido-lab/lucidpm:0.1.0`.
- Configuration: SQL-auth `lucidpm_app`, `LUCIDPM_SINGLE_DB=TenantCRM_Test`, and Container Apps secret references for the SQL password, Fernet key, and GHCR pull credential. No secret values are recorded here.

## A. Deployment and perimeter

- [x] Private GHCR image pulled and the Container App provisioned successfully. Revision `lucidpm--0000001` reached `Succeeded`.
- [x] Ingress was created with IP restrictions already present. The Azure CLI YAML wrapper returned an unrelated Boolean-conversion `400`; the same prepared resource body was successfully created with an ARM `PUT` through `az rest`, including the restriction in the initial resource request. There was no unrestricted create-then-restrict deployment.
- [x] Current allow rules: `Mark-Office` (`72.183.200.115/32`) and `Mark-Home` (`47.184.19.248/32`).
- [x] A cellular-network request, outside both allow rules, was denied.
- [x] The temporary Container Apps URL loads over HTTPS from an allowed network.

## B. Application behavior through real ingress

- [x] The app loaded and navigation between screens worked through Container Apps ingress. This confirms the Reflex websocket event channel survives the real Azure routing path.
- [x] The database banner reads **TEST** and Test data loads. `LUCIDPM_SINGLE_DB=TenantCRM_Test` hides the Test/Prod switch, so this temporary deployment cannot select Production.
- [x] Rent Roll PDF downloaded successfully through `/api/rent-roll-pdf`.
- [x] No application errors were reported during the deployed-app walkthrough. Some pages were slow on the first load.

## C. Scale-to-zero and cold start

- [x] `minReplicas` was set to `0`.
- [x] After browser tabs were closed and the idle cooldown elapsed, `az containerapp replica list -n lucidpm -g Lucido-Apps-RG -o table` returned no rows.
- [x] A first request from the Home allowlisted network started the app successfully. Time to load and display a Test-database list was approximately **one minute**.

The measurement combines Container Apps scale-up with any Azure SQL serverless resume. It is usable for this temporary single-user deployment, while later performance work should continue to account for this cold path.

## D. Cost guardrail

- [x] No Azure free-tier compute alert fired during deployment or validation.

## Gate 3 ? Result: **GO** ? Date: 2026-09-11

The private GHCR image runs correctly behind Azure Container Apps ingress. The real websocket path, Test-only database lock, IP perimeter, Rent Roll PDF route, scale-to-zero behavior, and cold-start recovery all passed.

**Next:** Stage 4 ? move a lease PDF to blob storage and verify it survives a container restart, completing the POC.
