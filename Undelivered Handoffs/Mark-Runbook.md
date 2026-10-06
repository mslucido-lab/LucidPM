# Mark Runbook — Custom domain for LucidPM (Cycle 5.4)

**STATUS: DONE, 2026-09-13.** `https://lucidpm.lucidoproperties.net` is live with a valid,
Azure-managed TLS certificate (`bindingType: SniEnabled`), and Entra auth is enforcing on it exactly
like the old address. Nothing further needed from you unless you want the app fully "moved in"
(rebuilding the image so its API calls target the new domain instead of the old Azure one — optional,
the app works fine as-is either way). Steps below are kept for reference.

Companion to Stage 5.4 in `Undelivered Handoffs/Azure Migration Roadmap.md`. Goal: make LucidPM
reachable at `lucidpm.lucidoproperties.net` instead of the temporary Azure hostname, with a free
Azure-managed TLS certificate.

**Your domain's DNS is hosted through Spectrum Business's SiteProtect panel** (confirmed via
`nslookup -type=NS lucidoproperties.net` → `adns.cs.siteprotect.com` / `bdns.cs.siteprotect.com` —
the same infrastructure behind your `mlucido@lucidoproperties.net` mail, which routes through
`mx1`/`mx2.biz.rr.com`). That's where the two records below get added.

**This only adds a new subdomain label (`lucidpm`) — it does not touch your existing apex domain
record or your email.** Your current website (`lucidoproperties.net` → `66.113.136.229`) and mail
(`mx1`/`mx2.biz.rr.com`) are untouched by anything here.

---

## Step 1 — Log into the Spectrum/SiteProtect DNS panel

Wherever you manage `lucidoproperties.net`'s DNS records today (the same place you'd have gone to set
up the `mlucido@lucidoproperties.net` mailbox). Find the DNS management / zone editor for the domain.

---

## Step 2 — Add these two records

| Type | Host / Name | Value | Notes |
|---|---|---|---|
| TXT | `asuid.lucidpm` | `F7AD1EF41652235A18FAE21F0C6A0C98510F31CD6F65C4DC2DB677E10D2DE306` | Proves you control the domain. If the panel insists on a full name instead of a relative one, use `asuid.lucidpm.lucidoproperties.net`. |
| CNAME | `lucidpm` | `lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io` | Points the subdomain at the actual app. Some panels require a trailing dot on the target (`...azurecontainerapps.io.`) — add one if the panel rejects it without. |

Leave TTL at whatever the panel defaults to (usually fine at 1 hour or less).

---

## Step 3 — Wait for DNS to propagate, then self-check (optional but recommended)

Usually a few minutes since you control the authoritative panel directly, but can take longer. From
a command prompt or PowerShell, you can check yourself before telling me it's done:

```powershell
nslookup -type=TXT asuid.lucidpm.lucidoproperties.net
nslookup lucidpm.lucidoproperties.net
```

The first should show the long `F7AD1...` value; the second should eventually resolve through to
Azure (it'll show the CNAME chain). If either comes back empty, double-check the Host/Name field —
DNS panels vary on whether they want the full name or just the part before your domain.

---

## Step 4 — Tell me it's done

Once both records are in and (ideally) confirmed via Step 3, let me know. From there:
- I bind the hostname to the Container App and request Azure's free managed certificate
  (`az containerapp hostname bind`), which validates the two records above are actually in place.
- I add `https://lucidpm.lucidoproperties.net/.auth/login/aad/callback` to the `lucidpm` Entra app
  registration's redirect URIs — without this, signing in via the new domain will fail even after
  DNS and the certificate are working, since Entra only allows sign-in redirects to URLs it already
  knows about.
- I'll flag whether a rebuild (to bake the new domain into the frontend's API URL) is worth doing
  right away or can wait — the app keeps working at the old `*.azurecontainerapps.io` address
  regardless, so this part isn't urgent.

---

## Why these specific values

- The TXT value (`F7AD1EF4...`) is this Container App's own fixed verification ID
  (`az containerapp show -n lucidpm -g Lucido-Apps-RG --query properties.customDomainVerificationId`)
  — it doesn't change per-domain, so if we ever add a second custom domain to this same Container App
  later, it'd reuse the same TXT value under a different host label.
- The CNAME target (`lucidpm.icyocean-a1d9520f.westus3.azurecontainerapps.io`) is the Container App's
  real, permanent Azure-assigned hostname — this doesn't change even after the custom domain is live;
  the custom domain becomes an additional way to reach the same app, not a replacement.
