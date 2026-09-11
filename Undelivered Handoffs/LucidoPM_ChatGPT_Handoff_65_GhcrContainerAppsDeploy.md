# LucidoPM — ChatGPT Handoff 65
*Push the Cycle 3.1 image to private GHCR, deploy it to Azure Container Apps on a temporary,
IP-restricted URL — Gate 3*
*Prepared: 2026-09-11 · revised 2026-09-11 (Codex pre-implementation review, 3 points, all accepted):*
*(1) `AppState.db_label` (`state.py:600-603`) hardcodes `"PRODUCTION"` whenever `SINGLE_DB_NAME` is*
*set — correct for the assumed future use case (lock to Prod) but wrong for this cycle's actual use*
*(`LUCIDPM_SINGLE_DB=TenantCRM_Test`): the deployed app would show a "PRODUCTION" banner while*
*actually on Test data. Small `state.py` fix added as a real step — the doc's earlier "no*
*application-code files change" claim was wrong. (2) The original two-step create-then-restrict*
*design left a real window where the app was externally reachable with no ingress restriction and no*
*Entra. Also, `--rule-type Public` (as drafted) is not a valid `az containerapp ingress*
*access-restriction set` argument — confirmed via `--help`, that command only takes `--action`,*
*`--ip-address`, `--rule-name`, `--description`. Redesigned around `az containerapp create --yaml`*
*with `ipSecurityRestrictions` baked into the initial deployment — atomic, no exposure window. (3)*
*"A PDF download works (e.g. Rent Roll)" was too loose — lease-package PDFs hit the known stale*
*`StoredFilePath` issue and would fail for a reason unrelated to this cycle. Rent Roll PDF is now the*
*named, required Gate 3 check (live-data report, no stored-file dependency).*
*Azure Migration — Stage 3, Cycle 3.2. HIGH risk (roadmap). Builds directly on Handoff 64
(Cycle 3.1, committed `3bcf3f8`, PASSED locally).*

---

## What This Is

Roadmap **Cycle 3.2** (`Undelivered Handoffs/Azure Migration Roadmap.md`, Stage 3) — **Gate 3**.
Publish the image Handoff 64 built and validated locally to Azure Container Apps, on the existing
shared environment, reachable over a real HTTPS ingress for the first time.

**Mostly not a Codex code-diff handoff** — Cycle 3.2 is overwhelmingly Azure/GitHub account
operations (GHCR tokens, `az containerapp create`, ingress config), plus one small, real app-code fix
(Step 0 — a mislabeled DB banner, see below). It's written up as a numbered handoff because of its
risk and because each step needs to be traceable, the same reasoning that applied to Cycles
1.1/1.2/2.1. Each step below is tagged with who executes it: **[Mark]** (needs his own GitHub/Azure
identity — not something that should flow through an assistant session), **[Claude via `az`]**
(executable here, same as this session's SQL user / firewall / alert work), **[Codex or Claude]**
(the `state.py` fix), or **[Mark verifies]** (browser-only, can't be scripted).

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
- One small app-code fix (`state.py`, Step 0): the DB banner must correctly show "TEST" for this
  deployment, not the hardcoded "PRODUCTION" the locked-DB code path currently always shows.

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

**`AppState.db_label` bug** (`LucidPM/state.py:599-603`), confirmed by reading the live code:
```python
@rx.var
def db_label(self) -> str:
    if SINGLE_DB_NAME is not None:
        return "PRODUCTION"
    return "TEST" if self.use_test_db else "PRODUCTION"
```
Written when `LUCIDPM_SINGLE_DB` was designed around locking to *Prod* for a future multi-user
deployment (H58) — a reasonable assumption at the time, but this cycle is the first real use of the
flag, and it locks to **Test**. Unfixed, the deployed app would show a "PRODUCTION" banner while
connected to `TenantCRM_Test` — actively misleading on a page whose whole job is telling the viewer
which database they're looking at. `TEST_DB_NAME` and `PROD_DB_NAME` (module-level constants,
`state.py:52-53`) are already in scope at that point in the file — the fix is a comparison, not new
plumbing.

---

## The Fix

### Step 0 — fix the DB banner **[Codex or Claude]**

`LucidPM/state.py`, current:
```python
    @rx.var
    def db_label(self) -> str:
        if SINGLE_DB_NAME is not None:
            return "PRODUCTION"
        return "TEST" if self.use_test_db else "PRODUCTION"
```
Replace with:
```python
    @rx.var
    def db_label(self) -> str:
        if SINGLE_DB_NAME is not None:
            return "TEST" if SINGLE_DB_NAME == TEST_DB_NAME else "PRODUCTION"
        return "TEST" if self.use_test_db else "PRODUCTION"
```
Locally verify both directions before this ships: `LUCIDPM_SINGLE_DB` unset → local dev unaffected
(byte-identical, `is_single_db` stays `False`, this branch never runs); `LUCIDPM_SINGLE_DB=TenantCRM`
→ still shows "PRODUCTION" (the case this code originally assumed); `LUCIDPM_SINGLE_DB=TenantCRM_Test`
→ now correctly shows "TEST" (this cycle's actual case). Commit this ahead of Step 2 — it needs to be
in the image that gets built and pushed, not patched in afterward.

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

### Step 3 — Create the Container App with ingress restrictions already in place **[Claude via `az`, on request]**

The original two-step design (create fully open, restrict afterward) left a real window where the
app was externally reachable with no restriction and no Entra. Fixed: create it via `--yaml`, with
`ipSecurityRestrictions` part of the initial deployment — atomic, no window. `az containerapp create`
accepts `--environment` as a normal flag alongside `--yaml` for everything else
(`az containerapp create --help`'s own example does this), so the environment link doesn't need to be
embedded in the file.

**Before running this:** confirm the exact `ipSecurityRestrictions` field name/shape against a live
resource — I could not do this myself this session (`az containerapp show` hit a transient CLI
network error repeatedly; unrelated to this design). Run `az containerapp show -g Lucido-Apps-RG -n
portfolio-manager -o yaml` (or against any other live Container App) and check the
`properties.configuration.ingress` block before trusting the shape below verbatim — it's the standard,
documented ARM property (`Microsoft.App/containerApps`), but "standard" isn't the same as "verified
against this CLI version."

`lucidpm-containerapp.yaml` (new file, not committed — holds secrets):
```yaml
properties:
  configuration:
    ingress:
      external: true
      targetPort: 8080
      ipSecurityRestrictions:
        - name: Mark-Home
          ipAddressRange: <Mark's home IP>/32     # verify current — IPs drift, see Update-AzureSqlFirewall.ps1
          action: Allow
        - name: Mark-Office
          ipAddressRange: <Mark's office IP>/32
          action: Allow
    registries:
      - server: ghcr.io
        username: mslucido-lab
        passwordSecretRef: ghcrio-mslucido-lab
    secrets:
      - name: ghcrio-mslucido-lab
        value: <the READ-ONLY pull PAT from Step 1>
      - name: sql-password
        value: <lucidpm_app password>
      - name: fernet-key
        value: <the current LUCIDPM_FERNET_KEY>
  template:
    containers:
      - name: lucidpm
        image: ghcr.io/mslucido-lab/lucidpm:0.1.0
        env:
          - name: LUCIDPM_SQL_SERVER
            value: lucidpm-sql-24899.database.windows.net
          - name: LUCIDPM_SQL_AUTH
            value: sql
          - name: LUCIDPM_SQL_USER
            value: lucidpm_app
          - name: LUCIDPM_SQL_PASSWORD
            secretRef: sql-password
          - name: LUCIDPM_SQL_TRUST_CERT
            value: "no"
          - name: LUCIDPM_TEST_DB
            value: TenantCRM_Test
          - name: LUCIDPM_SINGLE_DB
            value: TenantCRM_Test
          - name: LUCIDPM_FERNET_KEY
            secretRef: fernet-key
          - name: LUCIDPM_ENV
            value: cloud
    scale:
      minReplicas: 1
      maxReplicas: 1
```

```bash
az containerapp create --name lucidpm --resource-group Lucido-Apps-RG \
  --environment lucido-apps-env --yaml lucidpm-containerapp.yaml
```

Notes:
- `minReplicas: 1` **initially** — not for a schema-bootstrap step (LucidPM has none; unlike PM's
  Flask `bootstrap` command, `TenantCRM_Test`'s schema+data is already fully loaded from Cycle 2.1) —
  purely so there's a live replica to check against before deliberately testing scale-to-zero in
  Step 6.
- `LUCIDPM_SINGLE_DB=TenantCRM_Test` **hides the Test/Prod toggle entirely** for this deployment —
  the app can't reach `TenantCRM` (Prod) at all from here, by design (see Scope constraint above).
- No `LUCIDPM_SQL_CONNECT_RETRIES`/`_RETRY_BACKOFF` override — the committed defaults (`8`/`4`, tuned
  in Cycle 2.2 from real measurements) apply here unchanged.
- `targetPort: 8080` matches Caddy's port from Cycle 3.1, not Reflex's internal `8000` — Container
  Apps ingress talks to Caddy, exactly like `docker run -p 8080:8080` did locally.
- Immediately after creation, confirm the restriction actually took:
  `az containerapp ingress access-restriction list --name lucidpm --resource-group Lucido-Apps-RG`
  should show both rules. Allow-list semantics apply once any rule exists — there's no separate
  "enable restriction mode" toggle to double check.
- Delete `lucidpm-containerapp.yaml` (or move it beside `.env.docker` as a gitignored local file) once
  the app is created — it holds the same class of secrets `.env.docker` does.

### Step 4 — First sanity check **[Mark verifies]**

Open `https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io/` in a browser (from an allowed
IP). Confirm:
- Valid HTTPS cert (Container Apps provisions this automatically for the `*.azurecontainerapps.io`
  domain — no action needed, just confirm it's not showing a warning).
- The real compiled app loads.
- **The core Gate 3 risk:** click something that requires the websocket event channel (the DB banner —
  which should now read **"TEST"**, confirming Step 0's fix; or a page navigation). This is the first
  time it's been proven through a **real** ingress/load-balancer hop — Cycle 3.1 only proved it
  through a direct local `docker run -p`, which is not the same code path as traffic actually routed
  through Azure's front door.
- **The Rent Roll PDF downloads** (`/api/rent-roll-pdf`) — the required Gate 3 PDF check. Not "any
  PDF": lease-package PDFs hit the known stale `StoredFilePath` issue
  (`C:\Dell Inspirion\...`, standing TOP-PRIORITY item) and would fail for a reason that has nothing
  to do with this cycle. Rent Roll is generated fresh from live `Leases`/`PropertySuites` data with no
  stored-file dependency, so it isolates exactly what this step needs to prove: `/api/*` routing
  through the real ingress.

### Step 5 — Scale-to-zero + cold-start measurement **[Claude via `az`, then Mark verifies]**

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

### Step 6 — Record the result

New `docs/cycle-3.2-validation.md`, mirroring `docs/cycle-2.2-validation.md`'s format — the Validation
Checklist below maps directly onto it.

---

## Do Not Touch

- **No Entra, no custom domain, no production cutover** — Stages 5.3/5.4/5, not this cycle.
- **No Prod DB access from this deployment.** `LUCIDPM_SINGLE_DB=TenantCRM_Test` is load-bearing here,
  not a suggestion — don't loosen it to restore the toggle "for convenience."
- **`lucidadmin`.** Stays unused for anything but the Cycle-2.2-era local smoke test. This deployment
  uses `lucidpm_app`, same as Cycle 3.1's local validation.
- **Don't create the app without `ipSecurityRestrictions` already in the YAML.** Step 3 folds
  creation and restriction into one atomic call specifically to remove the exposure window a
  create-then-restrict sequence would leave — don't split it back into two steps "to keep it simple."
- **Don't ship without Step 0.** The `db_label` fix needs to be in the image `docker build` produces
  in Step 2 — it can't be patched into a running container afterward.
- **Don't reuse the write:packages PAT as the Container App's registry credential** — Step 1's whole
  point is keeping those separate.
- **Don't create a second Container Apps environment.** Reuse `lucido-apps-env`.
- **The Dockerfile/Caddyfile/entrypoint.sh from Cycle 3.1** — unchanged by this cycle. If something
  that worked locally breaks here, look at the *deployment* config (env vars, ingress, registry) before
  suspecting the image itself.

---

## Validation Checklist — Gate 3 GO/NO-GO

- [ ] `db_label` fix (Step 0) verified locally in all three DB modes before Step 2's build.
- [ ] Image pulls successfully; Container App revision reaches `Healthy`/`Running`.
- [ ] `ipSecurityRestrictions` were part of the initial `create` call (Step 3), not added afterward —
      confirm no window existed where the app was reachable without them.
- [ ] `az containerapp ingress access-restriction list` shows the expected `Allow` rules and nothing
      else reachable — confirmed from a non-listed network (e.g. cellular, not the office/home wifi)
      that the app is **not** reachable.
- [ ] `https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io/` loads over HTTPS with a valid
      cert, from an allowed IP. DB banner reads **"TEST"**, not "PRODUCTION".
- [ ] **Websocket event channel confirmed working through real Container Apps ingress** — this is the
      one thing Cycle 3.1 could not prove and this cycle exists to answer.
- [ ] **Rent Roll PDF** downloads (`/api/rent-roll-pdf`) — the named, required PDF check. Not a
      lease-package PDF, which would fail on the unrelated stale-`StoredFilePath` issue.
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
  LucidPM\state.py                    ← Step 0, db_label fix (~3 lines)
  lucidpm-containerapp.yaml            ← new, gitignored, NOT committed (Step 3 — holds secrets,
                                          same class as .env.docker; delete or gitignore after use)
  docs\cycle-3.2-validation.md         ← new, Step 6, mirrors docs\cycle-2.2-validation.md
```

One small app-code change this cycle (Step 0); everything else is deployment config, not a diff.
Reference material already in the repo:
```
Completed Handoffs\LucidoPM_ChatGPT_Handoff_64_ContainerizeReflexODBC.md   ← the image this cycle deploys
Undelivered Handoffs\lucidpm-cloud-migration-knowledge-share.md            ← PM's proven deployment sequence,
                                                                               GHCR/token/Entra/scale-to-zero patterns
docs\cycle-2.2-validation.md                                                ← cold-resume timing this cycle's
                                                                               measurement builds on
db\azure_app_user.sql                                                       ← lucidpm_app, reused unchanged
```
