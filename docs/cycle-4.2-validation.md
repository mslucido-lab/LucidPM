# Cycle 4.2 / Gate 4 — Blob storage restart-survival proof

**Result: PASSED. POC COMPLETE (Stages 0-4).**

Goal: prove a generated lease package PDF survives the `lucidpm` Container App scaling to zero and
back — something local-disk storage inside an ephemeral replica cannot do. See
`Undelivered Handoffs/LucidoPM_ChatGPT_Handoff_67_BlobStorageDeploy.md` for the deployment steps this
validates.

---

## A. Deployment

- [x] New image `ghcr.io/mslucido-lab/lucidpm:0.2.0` built from a checkout at/after `cbf2038`, pushed
      to GHCR.
- [x] Scoped Blob credential (container SAS, not the account key) set as a new Container Apps secret;
      existing SQL/Fernet secrets and env vars untouched.
- [x] `lucidpm` updated to the new image; new revision (`lucidpm--0000003`) reached `Healthy`.
- [x] Both ingress restrictions (`Mark-Office`, `Mark-Home`) confirmed present after the update.

## B. Generate + confirm Blob storage

- [x] Text-only lease package generated through the live app (revision `0000003`, `minReplicas: 1`).
      Downloaded correctly.
- [x] Blob object confirmed present in `lucidpm-documents`
      (`Generated/<lease-id>/<timestamp>_<uuid>_<filename>.pdf` key shape, per Handoff 66's design).

## C. Scale to zero

- [x] `az containerapp update -n lucidpm -g Lucido-Apps-RG --min-replicas 0`.
- [x] **First attempt did not scale down within the 5-minute cooldown** — traced to two browser tabs
      still open, each holding a live Reflex WebSocket connection. Confirmed via Azure Monitor: the
      `Requests` metric read `0` for 17+ minutes while the replica stayed up — a WebSocket connection
      sitting idle generates no new HTTP request-count entries but is still counted as an active
      connection by Container Apps' concurrency-based scaler. **Lesson:** "no console activity" and
      "no open connections" are not the same signal for a WebSocket app — check for open browser
      tabs/sessions specifically, not just request logs, before concluding scale-to-zero is stuck.
- [x] Once the tabs were genuinely closed, the app scaled to zero within the configured 5-minute
      cooldown, as expected. `replica list` confirmed empty.

## D. Retrieve after restart — the Gate 4 proof

- [x] Reopened the app (cold start, fresh replica `lucidpm--0000003-79488d89bf-pg4qp` — new pod
      suffix, confirming zero continuity with the replica that generated the package).
- [x] **First WebSocket connection attempt failed** with a Caddy 502 (`dial tcp 127.0.0.1:8000:
      connect: connection refused`). Confirmed directly in the container's own console logs: Caddy
      started accepting connections and printed "server running" before the Reflex backend's ASGI
      server was actually ready to accept TCP connections — the backend printed its own "Backend
      running at: http://0.0.0.0:8000" banner ~2s after Caddy, but was still loading page/state
      modules (`property_financials_analytics.py` deprecation warnings still appearing) for a couple
      more seconds after that banner. The first WebSocket upgrade request landed in that gap.
  - **Root cause:** `entrypoint.sh` (Handoff 64) starts Caddy and the Reflex backend concurrently
    with no "wait for backend ready" handshake between them. Not a regression from this cycle — a
    pre-existing gap in H64's design that only manifests on a genuine cold start (a warm/already-
    running app never hits this window).
  - **Not a Gate 4 blocker** — a retry recovers cleanly once the backend catches up.
  - **Follow-up, not urgent:** harden `entrypoint.sh` to have Caddy wait for a successful local health
    check against the backend before accepting external traffic (or have the reverse_proxy retry
    instead of failing immediately during that window). Tracked as a standing item, not a new handoff
    on its own.
- [x] Observed timeline from the user's first request to a working page (container had been idle long
      enough that `TenantCRM_Test` had likely also auto-paused, stacking two cold-start costs):
  - ~55s: first WebSocket attempt — 502 (Caddy/backend race, see above)
  - ~75s (+20s): second attempt — still failed. Longer than plain module-loading alone would explain;
    most likely the concurrent Azure SQL serverless resume (Cycle 2.2 measured 20-80s for this on its
    own) was also still in progress.
  - ~85s (+10s): succeeded — app usable.
- [x] **Navigated to the same package generated in Step B and downloaded it again — it downloaded
      correctly.** This is the core Gate 4 proof: a fresh container with zero local-disk continuity to
      the one that generated the file successfully retrieved it via Blob storage.

---

## Gate 4 — Result: **GO**

No pyodbc/Blob incompatibility, no data loss across the restart. The two things found during this
cycle (open-tab-blocks-scale-to-zero, Caddy/backend cold-start race) are real operational
characteristics worth carrying forward — neither is a defect in the Blob storage design itself, and
neither blocked the actual proof once understood.

**This closes Stages 0-4 — the LucidPM POC is complete.** Everything past this point (Stage 5:
production data migration, Entra auth, custom domain, cutover) touches production data and is a
larger commitment; Mark decides when to start it.

**Carried forward, not blockers:**
- Handoff 68 (source-PDF/split-section Blob migration) — found via this same testing session,
  tracked separately, not a Gate 4 regression.
- `entrypoint.sh` Caddy/backend startup race — worth a small hardening fix, not urgent.
- Auto-pause / cold-start UX for a single-user tool sitting idle — already an accepted tradeoff from
  Cycle 2.2, reconfirmed here at the container level too.

Result: **PASSED**  Date: 2026-09-11
