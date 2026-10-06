# LucidoPM — ChatGPT Handoff 72
*Stage 5.3 — Microsoft Entra ID authentication for the deployed `lucidpm` Container App*
*Prepared: 2026-09-13*
*Azure Migration — Stage 5.3. Medium risk: the Entra + Container Apps mechanics are proven (Portfolio
Manager runs this exact pattern live); what's untested is whether Reflex's persistent WebSocket
state-sync channel survives EasyAuth sitting in front of ingress. Phase 3 additionally exposes
Production through the container for the first time — sequenced last, only after Phases 1-2 are
proven safe.*

---

## Implementation Status — 2026-09-13 — DONE

**All 3 phases implemented and verified.**

- Created a separate single-tenant `lucidpm` Entra app registration (app ID
  `36b23acd-ea5a-41f4-be58-fbd120e483ec`) and service principal (object ID
  `21a8155e-9e73-4794-b714-90310c18051a`). Its redirect URI is the live Container App FQDN's
  `/.auth/login/aad/callback` route and ID-token issuance is enabled.
- Configured Container Apps EasyAuth with Entra, `platform.enabled: true`, `requireHttps: true`,
  `RedirectToLoginPage`, and `AzureActiveDirectory` as redirect provider. The active client secret
  expires **2028-09-13 07:08 UTC**. A tenant-wide consent grant contains only the basic OIDC
  identity scopes `openid profile email`; there are no Microsoft Graph/data permissions.
- Set `appRoleAssignmentRequired: true`. Mark and Gary were assigned before activation. Paula was
  intentionally denied while unassigned (and retained Portfolio Manager access), then assigned and
  successfully signed in. This proved the LucidPM assignment boundary is independent of PM.
- Mark completed the Phase 1 live Test-data save/update after sign-in, proving Reflex's state/event
  channel works through EasyAuth. No LucidPM application code changed.
- Removed the `Mark-Office` and `Mark-Home` ingress access-restriction rules. Mark successfully
  reached the app from cellular data, confirming the IP perimeter was removed; Entra remains the
  sign-in gate.
- Removed `LUCIDPM_SINGLE_DB` through the Azure Portal as a new revision (`lucidpm--0000008`,
  healthy). The Test/Prod toggle is visible again. **Mark confirmed 2026-09-13: the toggle loads,
  and switching back and forth loads the correct data each way** — Production and Test both verified
  live through the deployed, Entra-gated app.
- Independently re-verified via `az` after the fact (not just trusting the narrative above):
  `containerapp auth show` matches the target shape with the new `lucidpm` app's `clientId`; ingress
  `ipSecurityRestrictions` is `[]`; the container's env vars have no `LUCIDPM_SINGLE_DB` entry; the
  active revision (`lucidpm--0000008`) is `Healthy`; the service principal has
  `appRoleAssignmentRequired: true`; and all three of Mark, Gary, and Paula have live
  `appRoleAssignedTo` entries on the `lucidpm` service principal (Mark/Gary from 06:25 UTC, Paula
  from 07:18 UTC, consistent with the assign-after-initial-denial sequence described above).

---

## What This Is

Enable Container Apps' built-in Entra ID authentication on `lucidpm`, following the Portfolio
Manager pattern this same subscription already runs in production — but pulled from PM's **live,
actual configuration** (queried directly via `az`), not just the prose knowledge-share doc, since the
doc turned out to describe one recommended step PM itself never actually applied (see Current State).

**LucidPM has zero existing application-level authentication** — no login screen, no user/session
concept. `grep`ing the codebase confirms `LUCIDPM_ENV` (`state.py:67`) is a reserved-but-unused
marker; nothing reads `X-MS-CLIENT-PRINCIPAL-NAME` or any Entra header today. This makes LucidPM's
case **simpler than PM's**: PM needed a workaround (trust the identity header only when
Container-Apps-only, to avoid its own Flask login screen firing a second time) because it already had
its own auth. LucidPM has nothing to conflict with — Entra becomes the *only* gate, and the roadmap's
own bar for this cycle ("Done when: the app requires login and no application auth code was added")
should hold literally, with zero lines of `pages/*.py` or `state.py` touched.

**The one real unknown:** whether the Reflex WebSocket event channel (every page navigation and state
update flows over one persistent `_event` connection, not discrete request/response like PM's Flask
app) survives Container Apps' EasyAuth layer in front of ingress. This needs an explicit test, not an
inference from PM's success — Phase 1 is structured so that test happens before anything else changes.

**Also decided this session, bundled in:**
- **Gary Lucido and Paula Sawyer get access alongside Mark.** Entra access is controlled per
  *application* — each app registration is its own independent "Enterprise Application" with its own
  assignment list — so assigning them to `lucidpm` has zero effect on their Portfolio Manager access,
  and vice versa. A new, LucidPM-specific app registration handles this cleanly; PM's is read-only
  reference, never touched.
- **The Test/Prod toggle is restored** (the `LUCIDPM_SINGLE_DB=TenantCRM_Test` lock removed) once
  Entra is proven — this is the first time Production becomes reachable through the deployed
  container at all. Sequenced as the final, highest-stakes phase.

---

## Current State

- Deployed Container App: `lucidpm` in `Lucido-Apps-RG`, FQDN
  `lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io`, revision `lucidpm--0000007` (image
  `0.4.2`, per H71). `az containerapp auth show -n lucidpm -g Lucido-Apps-RG` returns `{}` — no auth
  configured today.
- Ingress is IP-restricted to two `Allow` rules: `Mark-Office` (72.183.200.115/32) and `Mark-Home`
  (47.184.19.248/32). **Neither Gary's nor Paula's networks are on this list — removing/replacing
  this restriction is a required step for this handoff's actual goal, not optional cleanup.**
  Container Apps evaluates IP restrictions before EasyAuth even runs; an unlisted IP never reaches
  the login page at all, regardless of Entra assignment.
- Current env vars on the container (confirmed live via `az containerapp show`):
  `LUCIDPM_SINGLE_DB=TenantCRM_Test` (Production not reachable through the container at all today —
  a deliberate lock from Cycle 3.2/H65; `components/sidebar.py:320` hides the Switch button via
  `rx.cond(~AppState.is_single_db, ...)`), `LUCIDPM_STORAGE_BACKEND=azure_blob`,
  `LUCIDPM_SQL_SERVER=lucidpm-sql-24899.database.windows.net`, `LUCIDPM_SQL_AUTH=sql`.
- **`LUCIDPM_SINGLE_DB` is safe to restore with zero code changes** — verified this isn't the same
  class of bug H71 just hit. `SINGLE_DB_NAME = os.getenv("LUCIDPM_SINGLE_DB") or None` (`state.py:59`)
  and `AppState.is_single_db` (`state.py:590-591`, a real `@rx.var`) are both evaluated by the
  **backend** process at container-runtime startup — not baked in during the separate `reflex export`
  frontend-build step the way H71's module-level UI branch was. Removing the env var and letting the
  Container App roll a new revision is sufficient.
- The Entra tenant (`mslucidogmail.onmicrosoft.com`, tenant ID
  `447ced56-639b-481c-8a82-1e75b21cc495`) has exactly 3 guest accounts (confirmed via
  `az ad user list`): Mark Lucido, Gary Lucido, Paula Sawyer. A single-tenant app registration alone
  would let all three sign in to *anything* in the tenant — per-app access needs
  `appRoleAssignmentRequired=true` plus an explicit assignment list on that specific app.
- **PM's live, working config, pulled directly as the template** (not assumed from the prose doc):
  - App registration (`portfolio-manager`, appId `ad9ed97a-31e3-4e1c-abbd-d3e6cf9802e5`):
    `signInAudience: AzureADMyOrg` (single-tenant); `web.redirectUris:
    ["https://portfolio-manager.icyocean-a1d9520f.westus3.azurecontainerapps.io/.auth/login/aad/callback"]`;
    `web.implicitGrantSettings.enableIdTokenIssuance: true` / `enableAccessTokenIssuance: false`; one
    client secret (2-year expiry).
  - Container App auth (`az containerapp auth show -n portfolio-manager -g Lucido-Apps-RG`):
    `platform.enabled: true`; `globalValidation.redirectToProvider: AzureActiveDirectory`;
    `globalValidation.unauthenticatedClientAction: RedirectToLoginPage`; `httpSettings.requireHttps:
    true`; `identityProviders.azureActiveDirectory.registration.clientSecretSettingName:
    microsoft-provider-authentication-secret`.
  - **Correction to the knowledge-share doc's own recipe:** PM's live service principal has
    `appRoleAssignmentRequired: false` (confirmed via `az ad sp show`) — the "set the enterprise
    application to require assignment" step the doc describes was never actually applied to PM
    itself. Not a defect to fix here (PM is a separate, out-of-scope app), but this handoff can't
    just mirror "whatever PM currently has" for that one setting — it has to actually do the step
    PM's own doc recommended but skipped.

---

## The Fix

### Phase 1 — Entra registration + Container Apps auth, still IP-restricted, still Test-only

Keep both existing safety nets (IP allowlist + `LUCIDPM_SINGLE_DB`) in place through this entire
phase. The goal is proving Entra sign-in *and* the Reflex websocket work at all, against the
lowest-stakes data, before removing anything.

1. **[Claude via az]** Create a new, LucidPM-specific app registration — never reuse PM's:
   ```
   az ad app create --display-name "lucidpm" --sign-in-audience AzureADMyOrg \
     --web-redirect-uris "https://lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io/.auth/login/aad/callback"
   az ad app update --id <new-app-id> --set web.implicitGrantSettings.enableIdTokenIssuance=true
   az ad sp create --id <new-app-id>
   ```
2. **[Claude via az]** Create a client secret and wire up Container Apps auth (this also creates the
   `microsoft-provider-authentication-secret` Container Apps secret):
   ```
   az containerapp auth microsoft update -n lucidpm -g Lucido-Apps-RG \
     --client-id <new-app-id> --client-secret <generated-secret> \
     --tenant-id 447ced56-639b-481c-8a82-1e75b21cc495
   az containerapp auth update -n lucidpm -g Lucido-Apps-RG \
     --enabled true --require-https true \
     --unauthenticated-client-action RedirectToLoginPage --redirect-provider AzureActiveDirectory
   ```
   Exact flag names to confirm against the installed az CLI's `--help` at execution time — PM's live
   config (above) is the target state to match, not any specific remembered command syntax. Setting
   `--enabled true` explicitly ensures the authentication platform itself is active; configuring a
   provider and anonymous-client action alone must not be relied on to enable it implicitly. This
   subscription's `az` has already hit at least one CLI/API quirk before (the
   `az containerapp create --yaml` Boolean-conversion 400, worked around via `az rest`) — if
   `containerapp auth` commands misbehave similarly, fall back to `az rest` against the Container
   Apps ARM API the same way.
3. **[Claude via az]** Turn on `appRoleAssignmentRequired` — the step PM's own doc recommended but
   never actually applied:
   ```
   az ad sp update --id <new-sp-object-id> --set appRoleAssignmentRequired=true
   ```
4. **[Mark, in the Entra portal]** Assign all three accounts: Entra ID → Enterprise Applications →
   `lucidpm` → Users and groups → Add user/group → select Mark, Gary Lucido, Paula Sawyer. Do this
   *before* relying on step 3's lockdown for anything — assign-before-enable, matching the
   knowledge-share doc's own stated safety rule (assign the administrator first, to avoid locking out
   the person making the change).
5. **[Mark verifies, from an allowed IP]** Visit the app URL, confirm redirect to Microsoft sign-in
   with the screen identifying itself as "lucidpm" (not "portfolio-manager"), sign in, land back in
   the app.
6. **[Mark verifies — the actual point of this phase]** Confirm the app isn't just a static shell
   post-login: navigate between at least two pages/tabs, open a tenant or lease record, confirm live
   data loads and updates. This only works if Reflex's WebSocket survived EasyAuth. If pages hang on
   a loading state or data never populates past the initial paint, the websocket is failing through
   EasyAuth and this phase is **not** done — stop here, don't proceed to Phase 2.
7. Record the client secret's expiry date somewhere durable (this handoff's eventual Status section,
   or `Action Items - Mark.md`) — PM's is 2 years out; match that unless there's a reason to shorten
   it.

### Phase 2 — open the perimeter to Entra alone

Only after Phase 1 step 6 passes.

1. **[Claude via az]** Remove the IP allowlist — Entra is now the perimeter:
   ```
   az containerapp ingress access-restriction remove -n lucidpm -g Lucido-Apps-RG --rule-name Mark-Office
   az containerapp ingress access-restriction remove -n lucidpm -g Lucido-Apps-RG --rule-name Mark-Home
   ```
2. **[Mark verifies]** From a network *not* on the old allowlist (cellular data, or have Gary/Paula
   try from their own location), confirm two things: (a) the app is reachable at all now, and (b)
   sign-in is still required — an unauthenticated request must still redirect to Entra, not serve the
   app directly. (b) is the actual security proof for this phase, not just "Gary can get in."
3. **[Gary / Paula]** Each attempts sign-in once, confirms landing in the app (still Test-only at
   this point).

### Phase 3 — restore the Test/Prod toggle

Only after Phase 2 is fully verified. **Highest-stakes step in this handoff** — real tenant/lease/
financial data becomes reachable over the public internet (behind Entra) for the first time.

1. **[Claude via az]**
   ```
   az containerapp update -n lucidpm -g Lucido-Apps-RG --remove-env-vars LUCIDPM_SINGLE_DB
   ```
2. **[Mark verifies]** The Switch (Test/Prod) button reappears in the sidebar (confirms
   `AppState.is_single_db` now reads `false`). Toggle to Production, confirm real data loads, toggle
   back to Test.
3. **[Mark's call, not this handoff's to decide]** Whether Gary and Paula should be told Production
   is now reachable, or whether their access should stay "Test only" by agreement even though
   technically one click away. This handoff makes Production *reachable to signed-in, assigned
   users* — it does not add any in-app role/permission system to restrict what an assigned user does
   once inside. If narrower access is wanted, that's a real product feature, well beyond this
   handoff's scope.

---

## Do Not Touch

- **Portfolio Manager's app registration, service principal, or Container App auth config.**
  Read-only reference for this handoff's design — never modified. A separate, LucidPM-only app
  registration is created instead.
- **`document_storage.py`, `state.py`'s DB-routing logic, any application code.** This handoff should
  ship with **zero application code changes**, matching the roadmap's own stated bar for Stage 5.3.
  If implementing this ever seems to require an app-code change, that's a sign of a wrong turn —
  stop and reconsider before writing it.
- **The Azure SQL firewall, the `lucidpm_app` contained SQL user, Blob storage config.** Unrelated to
  this handoff, already correct, not touched.
- **Custom domain / TLS certificate (Cycle 5.4).** Separately tracked; not needed for Entra to work —
  EasyAuth functions fine against the temporary `*.azurecontainerapps.io` hostname.
- **Any in-app role/permission system.** Explicitly out of scope (see Phase 3, step 3) — this handoff
  is authentication (who can get in), not authorization (what they can do once inside).

---

## Validation Checklist

**Phase 1**
- [x] New `lucidpm` app registration exists: single-tenant, ID-token issuance on, redirect URI
      matches the live FQDN exactly.
- [x] `az containerapp auth show -n lucidpm -g Lucido-Apps-RG` matches PM's shape (`platform.enabled`,
      `RedirectToLoginPage`, `requireHttps: true`) — re-confirmed independently via `az`.
- [x] `appRoleAssignmentRequired: true` on the new service principal — confirmed via `az ad sp show`,
      not assumed.
- [x] All three accounts (Mark, Gary, Paula) assigned in the Entra portal before relying on the
      lockdown — confirmed live via Graph `appRoleAssignedTo`, not just the implementation narrative.
- [x] Sign-in redirects to a login screen correctly identified as "lucidpm."
- [x] **Live data loads and updates after sign-in** — the actual websocket-survives-EasyAuth proof,
      not just that the login page renders. Mark completed a live Test-data save/update post-login.
- [x] Client secret expiry recorded — 2028-09-13 07:08 UTC (see Implementation Status above).

**Phase 2**
- [x] Both IP allowlist rules removed — confirmed via `az`, `ipSecurityRestrictions` returns `[]`.
- [x] Unauthenticated request from a non-allowlisted network still redirects to Entra — does not
      serve the app directly. Mark verified reachability from cellular data with Entra still gating.
- [x] Gary and Paula each successfully sign in at least once — Paula's initial denial-while-unassigned
      was deliberately tested first, then both assigned and confirmed signed in.

**Phase 3**
- [x] `LUCIDPM_SINGLE_DB` removed from the Container App's env vars — confirmed via `az`, no such
      entry remains; active revision `lucidpm--0000008` is `Healthy`.
- [x] Switch (Test/Prod) button visible again in the deployed app.
- [x] Production data loads correctly through the toggle; toggling back to Test still works too —
      confirmed by Mark 2026-09-13.

**Done when:** Mark, Gary, and Paula can each sign in from anywhere; no one else can; the app works
fully after sign-in (live data, not a static shell); and the Test/Prod toggle is restored — all
without a single line of application code changing.

---

## File Locations

This handoff is almost entirely Azure resource configuration, not application code:
```
(no application files change)

Action Items - Mark.md, or this handoff's own eventual Status section  ← record the client secret's
                                                                            expiry date
```

Reference material (read, don't modify):
```
Undelivered Handoffs\lucidpm-cloud-migration-knowledge-share.md   ← PM's proven recipe (prose)
Portfolio Manager's live Entra app registration + Container App
  auth config (queried via az, not a file) — the actual template
  this handoff's target state was pulled from
Undelivered Handoffs\Azure Migration Roadmap.md — Stage 5.3 section
components\sidebar.py:320                                          ← the existing, untouched
                                                                       Switch-button guard Phase 3
                                                                       relies on
```
