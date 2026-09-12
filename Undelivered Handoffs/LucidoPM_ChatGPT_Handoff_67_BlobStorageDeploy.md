# LucidoPM — ChatGPT Handoff 67
*Deploy Cycle 4.1's storage abstraction to the live Container App with a scoped Blob credential, and
prove a generated lease PDF survives a scale-to-zero restart — Gate 4, the last gate of the POC*
*Prepared: 2026-09-11*
*Azure Migration — Stage 4, Cycle 4.2. Medium risk. Builds directly on Handoff 66
(Cycle 4.1, committed `cbf2038`, PASSED locally) and reuses the live `lucidpm` Container App from
Handoff 65 (Cycle 3.2, committed `9a9fb79`).*

---

## What This Is

Roadmap **Cycle 4.2** — **Gate 4**, the actual POC-complete decision point. The live `lucidpm`
Container App is still running the pre-storage-abstraction image (`0.1.0`, from Cycle 3.2). This
cycle deploys the Cycle 4.1 code, wires it to Azure Blob Storage with a properly scoped credential
(not the account key used for local validation), and proves the thing Stage 4 exists to prove: a
generated lease package PDF survives the container scaling to zero and back — something local-disk
storage inside an ephemeral Container App replica cannot do.

**Like Handoff 65, this is mostly not a code-diff handoff** — no application code changes this cycle
(H66 already wrote it). It's Azure resource/deployment work, tagged per-step: **[Claude via `az`]**
(executable here, verified live this session), **[Mark]** (needs his own Docker/GHCR session), **[Mark
verifies]** (browser-only).

**Scope constraint:**
- Still locked to `TenantCRM_Test` (`LUCIDPM_SINGLE_DB`, unchanged from Cycle 3.2) — no Prod exposure.
- Still IP-restricted to Office/Home, no Entra (Stage 5.3) — unchanged.
- The Blob credential for this cycle is a **container-scoped SAS token**, not a managed identity.
  Managed identity is the better long-term answer (no secret at rest at all) but requires a code
  change to `AzureBlobStorage.__init__` (swap `from_connection_string` for
  `DefaultAzureCredential`-based auth) — deferred to Stage 5 hardening, alongside Entra and the
  custom domain. The SAS approach needs **zero code changes**: it's still a connection string in the
  same format `AzureBlobStorage` already consumes, just SAS-signed instead of key-signed.

**Two things verified live this session, not assumed:**
1. **User-delegation SAS tokens (`--as-user`) cap at 7 days** — Azure hard limit, confirmed by
   actually trying it (`ERROR: --expiry should be within 7 days from now`). Too short for a standing
   deployment. Use a **key-based container SAS** instead (`--auth-mode key`, no `--as-user`) — these
   support much longer expiries. The account key itself is used once, server-side, to *sign* the
   token; it's never exposed in the output and never reaches the app.
2. **`az containerapp update --set-env-vars` merges, it doesn't replace** — confirmed via
   `--help` ("Add or update environment variable(s)... Existing environment variables [not named are
   left alone]"). Safe to add the 3 new storage vars without reconstructing the SQL/Fernet ones or
   touching the ingress restrictions from Cycle 3.2. (`--replace-env-vars` is the destructive one —
   don't use it here.)

---

## Current State

**Live Container App** (`az containerapp show -n lucidpm -g Lucido-Apps-RG`): `provisioningState:
Succeeded`, image `ghcr.io/mslucido-lab/lucidpm:0.1.0`, `minReplicas: 0`, ingress restricted to
`Mark-Office` (`72.183.200.115/32`). This image predates Cycle 4.1 — it has no `document_storage.py`,
no `LUCIDPM_STORAGE_BACKEND` support.

**Cycle 4.1 code** (commit `cbf2038`, local checkout): `LucidPM/document_storage.py` +
wiring into `lease_documents_pdf.py` / `lease_package_builder.py` / `LucidPM.py`, validated locally
(`docs/cycle-4.1-validation.md`). Not yet built into an image, not yet deployed.

**Storage account** (`lucidpmdocs24899`, from Handoff 66): private, no public blob access, container
`lucidpm-documents`. The Cycle 4.1 local validation used the full account-key connection string in a
gitignored `.env` — explicitly flagged in H66 as **not** for deployment.

**SAS mechanism verified live** (2026-09-11):
```bash
az storage container generate-sas \
  --account-name lucidpmdocs24899 \
  --name lucidpm-documents \
  --permissions racw \
  --expiry <90-day UTC datetime> \
  --auth-mode key \
  --https-only \
  -o tsv
```
Produces a query string like `se=...&sp=racw&spr=https&sv=...&sr=c&sig=...`. `sp=racw` — read, add,
create, write only. No `d` (delete), no `l` (list) — the app's `AzureBlobStorage` methods
(`upload_blob`, `download_blob`, `get_blob_client().exists()`) never need either. `sr=c` — scoped to
the **container**, not the whole storage account.

---

## The Fix

### Step 1 — generate the scoped Blob credential **[Claude via `az`, on request]**

```bash
expiry=$(date -u -d '+90 days' +%Y-%m-%dT%H:%MZ)
sas=$(az storage container generate-sas \
  --account-name lucidpmdocs24899 --name lucidpm-documents \
  --permissions racw --expiry "$expiry" --auth-mode key --https-only -o tsv)
```
Build the connection string `AzureBlobStorage` expects (same format H66's local `.env` testing
already used, just SAS-signed instead of key-signed):
```
BlobEndpoint=https://lucidpmdocs24899.blob.core.windows.net/;SharedAccessSignature=<the sas value>
```
**Record the expiry date somewhere durable** (`Action Items - Mark.md` or a password-manager note) —
same operational-reminder pattern already established for the GHCR pull token and (eventually) Entra
client secrets. A lapsed SAS means the deployed app can't reach Blob storage until it's regenerated
and re-set as a secret; nothing else breaks (SQL/app logic is unaffected).

### Step 2 — build and push the new image **[Mark]**

Same recipe as Cycle 3.2, same FQDN (unchanged — still `lucido-apps-env`, still the same app name):
```powershell
git pull
git log -1 --oneline   # confirm it shows cbf2038 or later before building

docker build --build-arg REFLEX_API_URL=https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io `
  -t ghcr.io/mslucido-lab/lucidpm:0.2.0 `
  -t ghcr.io/mslucido-lab/lucidpm:latest .

docker push ghcr.io/mslucido-lab/lucidpm:0.2.0
docker push ghcr.io/mslucido-lab/lucidpm:latest
```
Bump the version tag (`0.1.0` → `0.2.0`) — this is a real behavior change (Blob storage support), not
a patch. Keep `:latest` pointed at it too, matching the existing convention.

### Step 3 — wire the new image + credential into the live Container App **[Claude via `az`, on request]**

```bash
# Add the new secret without touching existing ones (sql-password, ghcrio-lucidpm-pull, etc.)
az containerapp secret set -n lucidpm -g Lucido-Apps-RG \
  --secrets blob-connection="BlobEndpoint=https://lucidpmdocs24899.blob.core.windows.net/;SharedAccessSignature=<sas>"

# Update the image and add the 3 storage env vars — --set-env-vars merges, doesn't replace
az containerapp update -n lucidpm -g Lucido-Apps-RG \
  --image ghcr.io/mslucido-lab/lucidpm:0.2.0 \
  --set-env-vars \
    LUCIDPM_STORAGE_BACKEND=azure_blob \
    LUCIDPM_BLOB_CONTAINER=lucidpm-documents \
    LUCIDPM_BLOB_CONNECTION_STRING=secretref:blob-connection
```
**If `az containerapp update` hits a validation error in the same family as Cycle 3.2's
`--yaml`-wrapper Boolean-conversion 400** (unlikely — this is a different code path, plain flags, not
`--yaml` — but flagging it since it already happened once this migration): fall back to fetching the
current resource (`az containerapp show -o json`), merging the new image tag + secret + env vars into
its `properties.template` in place, and sending it back with `az rest --method PUT` — the exact
recovery Cycle 3.2 used.

Confirm the new revision is healthy before proceeding:
```bash
az containerapp revision list -n lucidpm -g Lucido-Apps-RG -o table
```

### Step 4 — generate a package, confirm it lands in Blob **[Mark verifies, then Claude via `az`]**

**[Mark]** Load `https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io/` (from an allowed
IP), generate a lease package from a **text-only-sections** template (avoids the unrelated
stale-`StoredFilePath` issue — same workaround used in every prior validation doc this migration).
Confirm it downloads correctly. Note which lease/package you generated — you'll retrieve this exact
one again in Step 5.

**[Claude via `az`]** Confirm the blob actually landed:
```bash
az storage blob list --account-name lucidpmdocs24899 --container-name lucidpm-documents \
  --auth-mode login -o table
```
Expect a key shaped `Generated/<lease-id>/<timestamp>_<uuid>_<filename>.pdf` (Handoff 66's design).

### Step 5 — scale to zero, then retrieve the same package — the Gate 4 proof **[Claude via `az`, then Mark verifies]**

```bash
az containerapp update -n lucidpm -g Lucido-Apps-RG --min-replicas 0
az containerapp replica list -n lucidpm -g Lucido-Apps-RG -o table
```
Wait out the idle cooldown, confirm the replica list is empty (a fresh container, with zero local
disk continuity from whatever generated the PDF in Step 4).

**[Mark]** Load the app again (this wakes a brand-new replica — time it, same stacking-cold-starts
caveat as Cycle 3.2: container scale-up + possible SQL serverless resume). Navigate back to the
**same** generated package from Step 4 and download it again. **This is Gate 4**: if it downloads
correctly — a fresh container, zero local disk in common with the one that generated it, retrieving
the exact same PDF — that proves Blob storage is what makes generated documents durable across
Container Apps restarts, which local disk alone never could.

Optional, not required for Gate 4: if you want the negative control on record, note (don't need to
re-run) that a `local`-backend generation would have been unrecoverable after this same restart —
that's the premise the whole Stage 4 test is built on, not something to separately prove by breaking
the working deployment.

### Step 6 — record the result

New `docs/cycle-4.2-validation.md`, mirroring the Cycle 2.2/3.2 format.

### Step 7 — `docs/Deployment.md` + roadmap reconcile

Update `docs/Deployment.md`'s "Current state" to mention the Blob-backed generated-document storage
and the image version bump. Mark Gate 4 **PASSED** and **POC COMPLETE** in the roadmap's at-a-glance
table and progress log — this is the milestone the whole roadmap has been counting toward since it
was written.

---

## Do Not Touch

- **The account-key connection string.** Cycle 4.1's local `.env` value stays local — never becomes
  a Container Apps secret. Only the SAS-based connection string from Step 1 does.
- **`LUCIDPM_SINGLE_DB=TenantCRM_Test`** — unchanged. This cycle doesn't touch Prod access.
- **Ingress IP restrictions** — unchanged from Cycle 3.2. Don't loosen them "to make testing easier."
- **Entra, custom domain, production data cutover** — Stages 5.3/5.4/5, not this cycle.
- **Source-PDF storage, the `storage_root` admin screen, the stale-`StoredFilePath` cleanup** — still
  out of scope, still Cycle 5.1's job (unchanged from H66).
- **`--replace-env-vars`** on the Container App update — that flag wipes unnamed env vars; this
  handoff uses `--set-env-vars` specifically because it merges.
- **The SAS expiry** — 90 days from Step 1, must be tracked somewhere durable (see Step 1). Don't
  treat "it worked today" as "it's done forever."

---

## Validation Checklist — Gate 4 GO/NO-GO

- [ ] New image (`0.2.0`) built from a checkout confirmed at `cbf2038` or later, pushed to GHCR.
- [ ] SAS-based connection string generated (90-day expiry, `racw`, container-scoped, HTTPS-only) and
      set as a **new** Container Apps secret — the account-key connection string never deployed.
- [ ] Container App updated to the new image; existing SQL/Fernet env vars and ingress restrictions
      confirmed unchanged (`az containerapp show` — spot-check before and after).
- [ ] New revision reaches `Healthy`.
- [ ] A lease package (text-only template) generated through the live app; confirmed present in
      `lucidpm-documents` at the expected key shape.
- [ ] Container App scaled to zero; `replica list` confirmed empty.
- [ ] **The same generated package downloads correctly from a fresh replica** — the core Gate 4 proof.
- [ ] Cold-start timing noted (container scale-up + possible SQL resume, same stacking as Cycle 3.2).
- [ ] `docs/cycle-4.2-validation.md` written.
- [ ] `docs/Deployment.md` and the roadmap reconciled — Gate 4 PASSED, POC COMPLETE.

**Done when:** all of the above pass. This closes the POC (Stages 0–4). Everything past Gate 4 touches
production data and is a bigger commitment — Stage 5 is Mark's call on when to start, not an automatic
next step the way Cycles 4.1→4.2 were.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  docs\cycle-4.2-validation.md   ← new, Step 6
  docs\Deployment.md              ← Step 7
  Undelivered Handoffs\Azure Migration Roadmap.md   ← Step 7 (Gate 4 / POC COMPLETE)
```

No application-code files change in this cycle — Handoff 66 already wrote all of it.

Azure resources this cycle touches (none newly created — all already exist):
```
Container App:     lucidpm                  (Lucido-Apps-RG, lucido-apps-env)
Storage account:   lucidpmdocs24899         (Handoff 66)
Blob container:    lucidpm-documents        (Handoff 66)
```
