# LucidoPM — ChatGPT Handoff 65
*Push the Cycle 3.1 image to private GHCR, deploy it to Azure Container Apps on a temporary,
IP-restricted URL — Gate 3*
*Prepared: 2026-09-11*
*Azure Migration — Stage 3, Cycle 3.2. HIGH risk (roadmap). Builds directly on Handoff 64
(Cycle 3.1, committed `3bcf3f8`, PASSED locally).*

---

## What This Is

Roadmap **Cycle 3.2** (`Undelivered Handoffs/Azure Migration Roadmap.md`, Stage 3) — **Gate 3**.
Publish the image Handoff 64 built and validated locally to Azure Container Apps, on the existing
shared environment, reachable over a real HTTPS ingress for the first time.

**This is not a Codex code-diff handoff** — Cycle 3.2 is overwhelmingly Azure/GitHub account
operations (GHCR tokens, `az containerapp create`, ingress config), not application code. It's
written up as a numbered handoff because of its risk and because each step needs to be traceable, the
same reasoning that applied to Cycles 1.1/1.2/2.1. Each step below is tagged with who executes it:
**[Mark]** (needs his own GitHub/Azure identity — not something that should flow through an assistant
session), **[Claude via `az`]** (executable here, same as this session's SQL user / firewall / alert
work), or **[Mark verifies]** (browser-only, can't be scripted).

**Scope constraint:**
- Temporary `*.azurecontainerapps.io` hostname only — no custom domain (Stage 5.4).
- **No Microsoft Entra authentication** — that's Stage 5.3. This deployment therefore has **zero
  built-in auth in front of it**, which is why IP-restricting ingress is a required step here, not
  optional (see below).
- **Points at `TenantCRM_Test` only**, locked via `LUCIDPM_SINGLE_DB` — not Prod, and not the
  Test/Prod toggle. Reduces blast radius for a deployment with no auth layer yet; Prod access waits
  for Stage 5 alongside Entra.
- No production data cutover, no schema changes. `TenantCRM_Test` already holds a full verified copy
  of the data (Cycle 2.1) — nothing to migrate or bootstrap.

**Resolves the H64-flagged open decision** (baked absolute `REFLEX_API_URL`): the shared Container
Apps environment `lucido-apps-env` already exists (proven by the live `portfolio-manager` app in it),
and an environment's default domain suffix is fixed, not per-app — confirmed live:
`az containerapp env show` returns `icyocean-a1d9520f.westus3.azurecontainerapps.io` regardless of
which app queries it. That means **this deployment's FQDN is fully predictable before the Container
App is even created** (`lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io`, following the
`portfolio-manager.icyocean-a1d9520f.westus3.azurecontainerapps.io` pattern already live). So: no
same-origin/relative-URL spike needed this cycle — rebuild with the real FQDN baked in via
`--build-arg`, the same mechanism Cycle 3.1 already proved, just pointed at the right value. (This
shortcut only holds because we're reusing the *existing* environment; if `lucido-apps-env` were ever
recreated, or Stage 5.4's custom domain lands, the URL changes again — same tradeoff noted in H64,
now just resolved for *this* cycle rather than deferred.)

---

## Current State

**Cycle 3.1 image** (`Completed Handoffs/LucidoPM_ChatGPT_Handoff_64_ContainerizeReflexODBC.md`,
commit `3bcf3f8`): builds and runs locally, validated end-to-end against Azure SQL. `docker build
--build-arg REFLEX_API_URL=http://localhost:8080 -t lucidpm:dev .` — that `localhost:8080` value is
exactly what needs to change for a real deployment; everything else about the image is unchanged.

**No GHCR repository exists yet for LucidPM.** Confirmed via `az containerapp show` on the sibling
app: Portfolio Manager's registry config is
`{server: ghcr.io, username: mslucido-lab, passwordSecretRef: ghcrio-mslucido-lab}` — so the GHCR
namespace to publish under is **`ghcr.io/mslucido-lab/lucidpm`**, matching the knowledge-share's
stated pattern (`ghcr.io/mslucido-lab/<image>`, one repo per app, private).

**Shared Container Apps environment `lucido-apps-env`** (westus3) already exists and hosts
`portfolio-manager` — confirmed live:
```
az containerapp env show -g Lucido-Apps-RG -n lucido-apps-env
  → defaultDomain: icyocean-a1d9520f.westus3.azurecontainerapps.io, staticIp: 4.242.214.9
az containerapp list -g Lucido-Apps-RG
  → portfolio-manager.icyocean-a1d9520f.westus3.azurecontainerapps.io
```
**Do not create a second environment.**

**No LucidPM Container App exists yet.**

**IP-restriction precedent:** Portfolio Manager currently has **zero** ingress access restrictions
(`az containerapp ingress access-restriction list` → `[]`) but **full Entra enforcement**
(`platform.enabled: true`, `unauthenticatedClientAction: RedirectToLoginPage`). This is consistent
with the knowledge-share's own account of PM's bring-up (*"enable and test Microsoft Entra
authentication while ingress is still restricted... only remove a temporary IP restriction after Entra
sign-in works"*) — i.e., PM likely had a temporary restriction during its own Cycle-3.2-equivalent,
removed once Entra was proven. LucidPM doesn't have Entra yet, so the restriction stays on through
this whole cycle — there is no "remove it" step here.

**Contained SQL user `lucidpm_app`** (`db/azure_app_user.sql`, both DBs, `db_datareader` +
`db_datawriter`) and the Fernet key are already proven working inside this exact image (Cycle 3.1
validation) — no changes needed to either.

---

## The Fix

### Step 1 — GHCR tokens **[Mark]**

Two **separate** GitHub Personal Access Tokens (classic or fine-grained), per the knowledge-share's
explicit warning — a developer publish token must never be the Azure registry credential:

1. **Publish token** — scope `write:packages` (+ `read:packages`). Used interactively on Mark's own
   machine only, never stored in this repo or passed through an assistant session:
   ```powershell
   docker login ghcr.io -u <github-username>
   # paste the publish PAT as the password when prompted
   ```
2. **Pull token** — scope `read:packages` **only**. This becomes the Container App's registry
   credential (Step 3). Generate it, but don't use it for anything else.

After the first push (Step 2), set the `lucidpm` package's visibility to **Private** in GitHub's
package settings — it defaults to inheriting repo visibility, which may not be what's wanted for a
package holding this app's build.

### Step 2 — Build with the real FQDN + push **[Mark]**

```powershell
docker build --build-arg REFLEX_API_URL=https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io `
  -t ghcr.io/mslucido-lab/lucidpm:0.1.0 `
  -t ghcr.io/mslucido-lab/lucidpm:latest .

docker push ghcr.io/mslucido-lab/lucidpm:0.1.0
docker push ghcr.io/mslucido-lab/lucidpm:latest
```

This is the **same Dockerfile, same Caddyfile, same entrypoint.sh** from Cycle 3.1 — only the
build-arg value changes. If this build fails where the local `localhost:8080` one didn't, the bug is
almost certainly unrelated to this cycle (regression in the unchanged Dockerfile), not something new
to design around.

### Step 3 — Create the Container App **[Claude via `az`, on request]**

```bash
az containerapp create \
  --name lucidpm \
  --resource-group Lucido-Apps-RG \
  --environment lucido-apps-env \
  --image ghcr.io/mslucido-lab/lucidpm:0.1.0 \
  --registry-server ghcr.io \
  --registry-username mslucido-lab \
  --registry-password "<the READ-ONLY pull PAT from Step 1>" \
  --target-port 8080 \
  --ingress external \
  --min-replicas 1 --max-replicas 1 \
  --secrets sql-password="<lucidpm_app password>" fernet-key="<the current LUCIDPM_FERNET_KEY>" \
  --env-vars \
      LUCIDPM_SQL_SERVER=lucidpm-sql-24899.database.windows.net \
      LUCIDPM_SQL_AUTH=sql \
      LUCIDPM_SQL_USER=lucidpm_app \
      LUCIDPM_SQL_PASSWORD=secretref:sql-password \
      LUCIDPM_SQL_TRUST_CERT=no \
      LUCIDPM_TEST_DB=TenantCRM_Test \
      LUCIDPM_SINGLE_DB=TenantCRM_Test \
      LUCIDPM_FERNET_KEY=secretref:fernet-key \
      LUCIDPM_ENV=cloud
```

Notes:
- `--min-replicas 1` **initially** — not for a schema-bootstrap step (LucidPM has none; unlike PM's
  Flask `bootstrap` command, `TenantCRM_Test`'s schema+data is already fully loaded from Cycle 2.1) —
  purely so there's a live replica to `az containerapp exec` into for a first sanity check (Step 4)
  before testing scale-to-zero deliberately in Step 6.
- `LUCIDPM_SINGLE_DB=TenantCRM_Test` **hides the Test/Prod toggle entirely** for this deployment —
  the app can't reach `TenantCRM` (Prod) at all from here, by design (see Scope constraint above).
- No `LUCIDPM_SQL_CONNECT_RETRIES`/`_RETRY_BACKOFF` override — the committed defaults (`8`/`4`, tuned
  in Cycle 2.2 from real measurements) apply here unchanged.
- `--target-port 8080` matches Caddy's port from Cycle 3.1, not Reflex's internal `8000` — Container
  Apps ingress talks to Caddy, exactly like `docker run -p 8080:8080` did locally.

### Step 4 — Restrict ingress to Mark's IP(s) **[Claude via `az`, on request]** — do this immediately

No Entra exists yet for this app, so this is the only thing standing between the internet and a
Reflex app with no login screen, pointed at real (if Test-only) tenant data. Mirrors the
`Mark-Office`/home-IP pattern already used for the SQL firewall this Azure Migration:

```bash
az containerapp ingress access-restriction set \
  --name lucidpm --resource-group Lucido-Apps-RG \
  --rule-name Mark-Home --ip-address <Mark's home /32> --action Allow --rule-type Public

az containerapp ingress access-restriction set \
  --name lucidpm --resource-group Lucido-Apps-RG \
  --rule-name Mark-Office --ip-address <Mark's office /32> --action Allow --rule-type Public
```

Access-restriction rules are **allow-list once any rule exists** — adding the first `Allow` rule
implicitly denies everyone else, there's no separate "enable restriction mode" toggle. Confirm this
behavior (`az containerapp ingress access-restriction list`) right after adding the first rule, before
assuming it's live.

### Step 5 — First sanity check **[Mark verifies]**

Open `https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io/` in a browser (from an allowed
IP). Confirm:
- Valid HTTPS cert (Container Apps provisions this automatically for the `*.azurecontainerapps.io`
  domain — no action needed, just confirm it's not showing a warning).
- The real compiled app loads.
- **The core Gate 3 risk:** click something that requires the websocket event channel (the DB banner,
  a page navigation). This is the first time it's been proven through a **real** ingress/load-balancer
  hop — Cycle 3.1 only proved it through a direct local `docker run -p`, which is not the same code
  path as traffic actually routed through Azure's front door.
- A PDF download works.

### Step 6 — Scale-to-zero + cold-start measurement **[Claude via `az`, then Mark verifies]**

```bash
az containerapp update --name lucidpm --resource-group Lucido-Apps-RG --min-replicas 0
az containerapp replica list --name lucidpm --resource-group Lucido-Apps-RG
```

Wait out the idle cooldown (Azure's default is 5 minutes), confirm the replica list is empty, then
**[Mark]** make one browser request and time it. This stacks **two possible cold starts** — the
container scaling from zero, and (if `TenantCRM_Test` has also auto-paused) the Azure SQL serverless
resume Cycle 2.2 already measured (~20-80s alone). Record the combined number honestly; don't assume
they're independent/additive without checking — the container might finish starting well before SQL
resumes, or the reverse.

### Step 7 — Record the result

New `docs/cycle-3.2-validation.md`, mirroring `docs/cycle-2.2-validation.md`'s format — the Validation
Checklist below maps directly onto it.

---

## Do Not Touch

- **No Entra, no custom domain, no production cutover** — Stages 5.3/5.4/5, not this cycle.
- **No Prod DB access from this deployment.** `LUCIDPM_SINGLE_DB=TenantCRM_Test` is load-bearing here,
  not a suggestion — don't loosen it to restore the toggle "for convenience."
- **`lucidadmin`.** Stays unused for anything but the Cycle-2.2-era local smoke test. This deployment
  uses `lucidpm_app`, same as Cycle 3.1's local validation.
- **Don't skip Step 4**, even to "just quickly check" something. There's a real window between a
  Container App going live and access restrictions taking effect if done out of order — do Step 4
  immediately after Step 3, before the first real browser check.
- **Don't reuse the write:packages PAT as the Container App's registry credential** — Step 1's whole
  point is keeping those separate.
- **Don't create a second Container Apps environment.** Reuse `lucido-apps-env`.
- **The Dockerfile/Caddyfile/entrypoint.sh from Cycle 3.1** — unchanged by this cycle. If something
  that worked locally breaks here, look at the *deployment* config (env vars, ingress, registry) before
  suspecting the image itself.

---

## Validation Checklist — Gate 3 GO/NO-GO

- [ ] Image pulls successfully; Container App revision reaches `Healthy`/`Running`.
- [ ] `az containerapp ingress access-restriction list` shows the expected `Allow` rules and nothing
      else reachable — confirmed from a non-listed network (e.g. cellular, not the office/home wifi)
      that the app is **not** reachable.
- [ ] `https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io/` loads over HTTPS with a valid
      cert, from an allowed IP.
- [ ] **Websocket event channel confirmed working through real Container Apps ingress** — this is the
      one thing Cycle 3.1 could not prove and this cycle exists to answer.
- [ ] A PDF download works (proves `/api/*` routing through the real ingress too).
- [ ] `TenantCRM_Test` data loads correctly; confirm `TenantCRM` (Prod) is **not** reachable from this
      deployment (no toggle visible, and — if curious — confirm the app genuinely can't connect to
      Prod even if coaxed, since `LUCIDPM_SINGLE_DB` should make the DB name in code irrelevant).
- [ ] Scale-to-zero confirmed (`replica list` empty after idle cooldown) and cold-start time recorded
      (container-scale + possible SQL-resume, stacked).
- [ ] No free-tier compute alert fired during testing (`LucidPM-TenantCRM_Test-free-compute-low`).
- [ ] `docs/cycle-3.2-validation.md` written, mirroring the Cycle 2.2 doc.

**Done when:** all of the above pass. **G3 — GO** means the app is confirmed running correctly behind
real Container Apps ingress, websocket included, with cold-start behavior characterized. **NO-GO**
triggers if the websocket channel doesn't survive ingress (the roadmap's long-flagged risk) or
cold-start proves unworkable even after this measurement — either feeds a follow-up handoff, doesn't
reopen H64.

**After Gate 3 passes:** Stage 4 (blob storage — one PDF survives a container restart) is next, and
completes the POC.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  docs\cycle-3.2-validation.md   ← new, Step 7, mirrors docs\cycle-2.2-validation.md
```

No application-code files change in this cycle. Reference material already in the repo:
```
Completed Handoffs\LucidoPM_ChatGPT_Handoff_64_ContainerizeReflexODBC.md   ← the image this cycle deploys
Undelivered Handoffs\lucidpm-cloud-migration-knowledge-share.md            ← PM's proven deployment sequence,
                                                                               GHCR/token/Entra/scale-to-zero patterns
docs\cycle-2.2-validation.md                                                ← cold-resume timing this cycle's
                                                                               measurement builds on
db\azure_app_user.sql                                                       ← lucidpm_app, reused unchanged
```
