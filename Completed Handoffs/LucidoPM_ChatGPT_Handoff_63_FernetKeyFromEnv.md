# LucidoPM — ChatGPT Handoff 63
*Fernet config-encryption key: out of the database, into the environment — with a key rotation*
*Prepared: 2026-09-08 · revised 2026-09-08 (pre-impl review r1: `docs/Database.md` §Secrets added to scope; `_fernet()` rejects an all-whitespace/separator key list with the same `ConfigError` as unset, not `IndexError`; migration is a **key rotation**, not a straight move. r2: the three gitignored `db/TenantCRM*.sql` exports **do** carry the `LocalEncryptionKey` row + SMTP/API ciphertext (UTF-16 — byte-`grep` missed them; `rg` finds them) → runbook step 8 deletes them alongside the `.bacpac`/backups, and step 9 recommends rotating the underlying SMTP/Anthropic credentials. Scope wording: no bulk re-encryption in code; Mark re-saves the four secrets via Admin Settings. **Git history is still clean — those exports were never `git add`ed — so no `filter-repo`.**)*
*Azure Migration — Stage 0, Cycle 0.4 (the last Stage 0 item). No Azure resource required.*

---

## Status — CODE DONE (`cc9af6b`) · ROTATION DONE 2026-09-09

- **Code:** `state.get_fernet` → env-driven `LUCIDPM_FERNET_KEY` (comma-separated → `MultiFernet`), fail-fast
  `ConfigError`, lazy. Committed `cc9af6b`. Docs updated (`.env.example`, DeveloperSetup §5, Deployment,
  Database §Secrets).
- **Rotation (Mark, 2026-09-09):** new key generated, secrets re-saved under it, app verified running on the
  **new key alone**, and the `LocalEncryptionKey` rows **deleted from both `TenantCRM` and `TenantCRM_Test`**.
  New key lives only in `.env` (gitignored, `.gitignore:18`).
- **Conscious deviations from the runbook (Mark's call, recorded for accuracy — not open issues):**
  - **Old key kept**, as a commented line in `.env`, for recovery insurance ("posterity"). Step 8/9 of the
    runbook (purge the local `db/TenantCRM*.sql` / `.bacpac` / `*_Backup\` copies that carry old key +
    old ciphertext; rotate the underlying SMTP/Anthropic creds) was **not** done. Net effect: on a
    stolen-laptop basis the old SMTP password + old Anthropic key remain recoverable (old key in `.env` +
    old ciphertext in those local, gitignored exports). The intended gain that *was* realised: the key is
    no longer *in the database*, so a DB-only compromise (injection, cloud-SQL breach, leaked backup) no
    longer yields it — which is the point that matters as the DB moves to Azure.
- **Stage 0 (code prep) is complete.** Next: Cycle 2.2 / Gate 2.

---

## What This Is

Roadmap **Cycle 0.4** (`Undelivered Handoffs/Azure Migration Roadmap.md`,
lines 178–184): the Fernet key that encrypts the stored SMTP password and
Anthropic API key is itself **stored in the same database**, which defeats
encryption-at-rest — anyone who can read the DB gets both the ciphertext and its
key.

The live code (the roadmap's "`settings.py` ~lines 35–57" pointer is stale — it
moved):

`LucidPM/state.py`, `get_fernet(db)` (line 291):

```python
def get_fernet(db: str) -> "Fernet":
    """Load or generate the Fernet encryption key from AppSettings."""
    rows = run_query(
        "SELECT SettingValue FROM dbo.AppSettings WHERE SettingKey = 'LocalEncryptionKey'",
        db=db,
    )
    if rows and rows[0].get("SettingValue"):
        key = str(rows[0]["SettingValue"])
    else:
        key = Fernet.generate_key().decode("utf-8")
        run_exec(""" MERGE dbo.AppSettings … 'LocalEncryptionKey' … """, ("LocalEncryptionKey", key), db=db)
    return Fernet(key.encode("utf-8"))
```

`encrypt_value(value, db)` / `decrypt_value(value, db)` wrap it. Callers:

| Call site | Ciphertext it touches |
|---|---|
| `admin_settings.py:299` `encrypt_value` | `dbo.EmailConfig.PasswordEncrypted` |
| `admin_settings.py:319` `encrypt_value` | `dbo.AIConfig.APIKeyEncrypted` |
| `admin_settings.py:351`, `:431` `decrypt_value` | reads those back |
| `communications.py:314` `decrypt_value` | `AIConfig.APIKeyEncrypted` (`_get_ai_config`) |
| `communications.py:344` `decrypt_value` | `EmailConfig.PasswordEncrypted` (IMAP) |
| `state.py:375` `decrypt_value` (`send_email`) | `EmailConfig.PasswordEncrypted` (SMTP) |

The key lives in `dbo.AppSettings`, key `'LocalEncryptionKey'`, **per database**
(each DB auto-generates its own on first use). In the May-2026 export snapshots
under `db/` the `TenantCRM` and `TenantCRM_Test` values are **the same** — the
runbook still `SELECT`s from both live DBs to confirm, since they could have
diverged since.

**There is already a precedent in this repo.** `pages/tally_import.py`
`get_cipher()` reads a *different* Fernet key (`TENANTCRM_FERNET_KEY`, for tenant
SSN/DL) **from an environment variable** and hard-errors if it's missing. H63
does the same for the config key, under the `LUCIDPM_*` namespace this migration
has been using (`LUCIDPM_SQL_*`, `LUCIDPM_ENV`, …).

### The change

`get_fernet` reads `LUCIDPM_FERNET_KEY` from the environment — a **comma-separated
list**: the first key encrypts, every key can decrypt (`MultiFernet`). No DB
read, no auto-generate. Missing / malformed → fail fast with `ConfigError`
(the H58 pattern), caught by the same page-level `try/except` that handles a
bad key today.

Comma-separated covers rotation and the two-DB case with one mechanism:
- **Rotation (the migration path — see below):**
  `LUCIDPM_FERNET_KEY=<new>,<old-prod>[,<old-test>]` → re-save each secret in
  Admin Settings → they re-encrypt under `<new>` → drop the old keys.
- **Steady state:** one key, `LUCIDPM_FERNET_KEY=<key>`.

### Rotate, don't just relocate

The migration **generates a fresh key** rather than lifting the current one into
`.env` unchanged. The old key + both ciphertexts sit together, in plaintext, in
several **local, untracked** files:

- `db/TenantCRM_full.sql`, `db/TenantCRM_azure.sql`, `db/TenantCRM_Test_azure.sql`
  — each has the `INSERT … AppSettings … 'LocalEncryptionKey'` row *and* the
  `AIConfig.APIKeyEncrypted` / `EmailConfig.PasswordEncrypted` INSERTs (UTF-16,
  which is why a byte-`grep` missed them earlier — use `rg`).
- `C:\Inspirion\Dev\TenantCRM\Database\TenantCRM_Azure.bacpac`,
  `…\TenantCRM_Backup\`, `…\TenantCRM_Test_Backup\` — full DB copies.

Anyone with one of those files can already decrypt the SMTP password and
Anthropic API key. A straight key-move fixes nothing for them; a rotation does.
`MultiFernet` is already the mechanism — rotation is ~2 extra runbook steps.
(**Because those credentials are exposed at rest locally, consider rotating the
SMTP password and the Anthropic API key themselves too — Mark's call, noted in
the runbook.**)

**Git history is clean and needs no remediation** (verified 2026-09-08): the
`db/*.sql` dumps are `.gitignore`d (`/db/TenantCRM*.sql`) and were **never
`git add`ed** — `git log --all -- 'db/TenantCRM*.sql'` is empty; the only
`LocalEncryptionKey` string anywhere in history is the SQL query literal in the
code. So **no `git filter-repo` / BFG**. The at-risk files above are all in the
working tree / outside the repo — deletable, not history-rewrite territory.

**Files that change:** `LucidPM/state.py` (`get_fernet` body + one import),
`.env.example` (document the var), `docs/DeveloperSetup.md` (§5 Secrets),
`docs/Deployment.md` (known-blockers note), `docs/Database.md` (§ "Secrets and
encryption" — H63 makes lines 36–41 false). Plus a migration/rotation
**runbook** (run by Mark, per DB) and an optional `db/data_updates/` script for
the final row delete. No schema. No page code.

### Scope constraint

**Config-encryption key only.** This handoff does **not**:

- Touch `pages/tally_import.py` or `TENANTCRM_FERNET_KEY` (tenant SSN/DL — a
  separate key, separate data, *already* env-based). Unifying the two env-var
  names is a possible later cleanup, explicitly out of scope here; the two
  coexist after H63.
- Touch the dead `pages/settings.py` (superseded by `admin_settings.py`, not
  imported anywhere live; it carries its own unused copy of
  `_get_or_create_encryption_key` / `encrypt_value` / `decrypt_value`). Leave it.
- Change the signatures of `get_fernet` / `encrypt_value` / `decrypt_value` or
  any of their ~8 call sites — the `db` parameter simply stops being used for
  key selection (keep it in the signature).
- Add any automatic or bulk re-encryption code, or touch any ciphertext column
  or tenant SSN/DL data. (The rotation runbook re-encrypts the four config
  secrets by Mark **re-saving them through Admin Settings** — a normal user
  action, no migration code.)
- Add a `_validate_*` import-time check — `get_fernet` stays **lazy** (called
  only when a secret is encrypted/decrypted), so the app still boots with the
  var unset; only email/AI actions then fail, exactly as a bad key fails today.
- Add schema or a `db/history/` script (deleting a data row is a
  `db/data_updates/` concern, and mostly a manual runbook step).

---

## The Current State

### `LucidPM/state.py`

- Line 14: `from cryptography.fernet import Fernet`
- Line 76: `class ConfigError(RuntimeError)` (added by H58) — reuse it.
- Lines 287–329: the encryption block (`get_fernet`, `encrypt_value`,
  `decrypt_value`) shown above.
- `os` is already imported (line 6).

### `.env.example`

Documents `LUCIDPM_SQL_*`, `LUCIDPM_ENV`, `LUCIDPM_PROD_DB` / `_TEST_DB` /
`_SINGLE_DB`. **No secrets/encryption section yet.**

### `docs/DeveloperSetup.md` — "## 5. Secrets" (line 63)

> No environment variables are required to start the app (see `.env.example`).
> SMTP credentials and the Anthropic API key are configured from within the
> running app itself (Admin Settings) and stored encrypted in the database —
> there's no separate secrets step during setup.

The first sentence stays true (the app *boots* with nothing set); the rest needs
the key caveat.

### `docs/Deployment.md` — "Known blockers for cloud hosting"

Currently lists SQL Windows-auth and local storage paths (the file-picker bullet
was removed in H62). The Fernet-key-in-DB problem is **not** in this list even
though the architect gap analysis flagged it — add it as a bullet marked
resolved by H63, or add-and-strike, matching the H62 treatment.

### `docs/Database.md` — "Secrets and encryption" (lines 36–41)

> No environment variables are used. All secrets live encrypted in the database
> itself:
> - **Fernet encryption key**: `get_fernet()` in `state.py` reads
>   `AppSettings.LocalEncryptionKey`; if absent, it generates one and persists
>   it back … There's no external key to configure — the key lives entirely in
>   whichever database … is active …
> - **SMTP credentials, Anthropic API key**: stored encrypted (via that Fernet
>   key) in `EmailConfig` / `AppSettings` …
> One consequence … because the Fernet key is per-database and auto-generated,
> a value encrypted under `TenantCRM_Test`'s key cannot be decrypted using
> `TenantCRM`'s key …

**Every sentence of this becomes false** — it is the most wrong doc after the
change, so it must be in scope.

### Verified (2026-09-08)

- `get_fernet` / `encrypt_value` / `decrypt_value` are defined only in
  `state.py` (live) and dead `settings.py`. `MultiFernet` is not used anywhere.
- `'LocalEncryptionKey'` is read/written only by `state.get_fernet` (live) and
  dead `settings.py`.
- All live callers import `encrypt_value` / `decrypt_value` from `LucidPM.state`.
- **Git history carries no key material** — `git log --all -- 'db/TenantCRM*.sql'`
  is empty (never tracked); `git rev-list --all | xargs -I{} git grep -l
  "LocalEncryptionKey" {}` → only code (SQL query literals in
  `Archived Versions/state_*.py`, dead `settings.py`). No key value, no
  ciphertext, ever committed → **no `git filter-repo` / BFG step in H63.**
- **The at-risk files are all local / untracked, and DO carry key + ciphertext**
  (correcting an earlier note): `db/TenantCRM_full.sql`, `db/TenantCRM_azure.sql`,
  `db/TenantCRM_Test_azure.sql` (working tree, gitignored, UTF-16 — `rg` finds
  the `AppSettings` / `EmailConfig` / `AIConfig` INSERTs a byte-`grep` misses)
  and `C:\Inspirion\Dev\TenantCRM\Database\TenantCRM_Azure.bacpac` +
  `…\TenantCRM_Backup\` / `…\TenantCRM_Test_Backup\`. All deletable/re-generatable
  — runbook step 8.

---

## The Fix

### Step 1 — `state.py`: env-driven key

**1a.** Line 14 — add `MultiFernet`:

```python
from cryptography.fernet import Fernet, InvalidToken, MultiFernet
```

(`InvalidToken` is optional — only if you add the catch in 1c; otherwise just
`Fernet, MultiFernet`.)

**1b.** Replace `get_fernet` (lines 291–315) with:

```python
def _fernet():
    """Build the config-secret cipher from LUCIDPM_FERNET_KEY.

    The value is a comma-separated list of url-safe-base64 Fernet keys: the
    first encrypts, all of them can decrypt (MultiFernet). Two keys covers the
    TenantCRM / TenantCRM_Test pair (each historically had its own key) and
    key rotation (new,old -> re-save secrets -> drop old).
    """
    raw = os.getenv("LUCIDPM_FERNET_KEY", "")
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        # unset, empty, or only whitespace / separators ("", " , ")
        raise ConfigError(
            "LUCIDPM_FERNET_KEY is not set (or holds no key value) — it holds "
            "the Fernet key(s) that encrypt the saved SMTP password and "
            "Anthropic API key. See .env.example."
        )
    try:
        fernets = [Fernet(k.encode("utf-8")) for k in keys]
    except ValueError as exc:   # covers binascii.Error (a ValueError subclass)
        raise ConfigError(f"LUCIDPM_FERNET_KEY holds an invalid Fernet key: {exc}") from None
    return MultiFernet(fernets) if len(fernets) > 1 else fernets[0]


def get_fernet(db: str):
    """The config-secret cipher. `db` is unused now (the key is process-wide,
    from LUCIDPM_FERNET_KEY) — kept in the signature for call-site stability."""
    return _fernet()
```

**1c.** `encrypt_value` / `decrypt_value` (lines 318–329) are unchanged — they
already call `get_fernet(db)` and `.encrypt` / `.decrypt` work identically on a
`MultiFernet`. (Optional: in `decrypt_value`, catch `InvalidToken` and return
`""` so a wrong-key failure matches the empty-string path callers already handle
— but today's code doesn't catch it either, so leaving it raises is not a
regression. Recommend leaving it.)

### Step 2 — `.env.example`: document the var

Add, after the `LUCIDPM_ENV` block (or as its own `# --- Secrets ---` section):

```
# --- Secrets / config encryption -----------------------------------------
# Fernet key(s) for the stored SMTP password + Anthropic API key. Required
# before email or AI features work; the app still BOOTS without it.
# Comma-separated: the first key encrypts, all keys decrypt (MultiFernet).
#  - Fresh install: generate one —
#      python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
#  - Rotation / migration off the old DB key: LUCIDPM_FERNET_KEY=<new>,<old...>
#    then re-save each secret in Admin Settings on both DBs, then drop <old...>.
# In the cloud this is a Container Apps secret, never a committed value.
#LUCIDPM_FERNET_KEY=
```

### Step 3 — `docs/DeveloperSetup.md` §5 Secrets

Replace the paragraph with:

> The app **boots** with no environment variables. But saving or using the SMTP
> password / Anthropic API key needs **`LUCIDPM_FERNET_KEY`** — the Fernet key
> that encrypts them (ciphertext lives in `dbo.EmailConfig` / `dbo.AIConfig`;
> the key used to auto-generate into `dbo.AppSettings` and was moved to the
> environment in Cycle 0.4 / Handoff 63). Set it in `.env` (see `.env.example`)
> to a key you generate with
> `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
> The value is comma-separated: the first key encrypts, all keys decrypt — used
> for rotation (`new,old`) and, during the H63 migration, to decrypt data still
> encrypted under the old per-database keys.
>
> Tenant SSN/DL fields use a **separate** key, `TENANTCRM_FERNET_KEY`
> (`pages/tally_import.py`) — unrelated to the above, also env-only.

### Step 4 — `docs/Deployment.md`

Add to the known-blockers list (matching the H62 treatment):

> - ~~The Fernet key for config secrets was stored in `dbo.AppSettings`
>   alongside the ciphertext it protects~~ — moved to the `LUCIDPM_FERNET_KEY`
>   environment variable and rotated in Cycle 0.4 / Handoff 63.

### Step 4b — `docs/Database.md` (§ "Secrets and encryption", lines 36–41)

Rewrite the whole subsection:

> ### Secrets and encryption
>
> The SMTP password and Anthropic API key are stored encrypted (Fernet) in
> `dbo.EmailConfig.PasswordEncrypted` and `dbo.AIConfig.APIKeyEncrypted`. The
> key(s) come from the **`LUCIDPM_FERNET_KEY`** environment variable
> (comma-separated — the first encrypts, all decrypt), not from the database.
> The app boots without it; only email/AI actions need it. See `.env.example`
> and `docs/DeveloperSetup.md` §5.
>
> Because the key is now process-wide rather than per-database, a value written
> under one database decrypts fine against the other — the old
> `TenantCRM` vs `TenantCRM_Test` cross-key problem is gone. (Historically each
> DB auto-generated its own key into `AppSettings.LocalEncryptionKey`; Handoff
> 63 removed that row from both.)
>
> Tenant SSN / DL use a separate Fernet key, `TENANTCRM_FERNET_KEY`
> (`pages/tally_import.py`).

### Step 5 — migration = **key rotation** runbook  *(Mark runs this; not code)*

Once done, record it in the roadmap progress log. **Order: new key in with the
old → re-encrypt → verify under new alone → remove the old key, the DB rows, and
the local export/backup files.**

1. **Extract the old keys.** For each DB:
   `SELECT SettingValue FROM dbo.AppSettings WHERE SettingKey = 'LocalEncryptionKey';`
   Record both (call them `OLD_PROD`, `OLD_TEST` — may be equal).
2. **Generate a new key:**
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   → `NEW`.
3. **Set `.env`** at the repo root, new key first:
   `LUCIDPM_FERNET_KEY=<NEW>,<OLD_PROD>[,<OLD_TEST> if different]`
4. **Re-encrypt.** Restart. In Admin Settings, on **each** DB (toggle Prod/Test):
   re-enter and save the SMTP password; re-enter and save the Anthropic API key.
   Each save now writes ciphertext under `NEW`.
5. **Verify under NEW alone.** Set `.env` to `LUCIDPM_FERNET_KEY=<NEW>` only.
   Restart. On both DBs: Email + AI show *configured*; a test email sends; "Test
   AI connection" succeeds. (If anything fails, put the old keys back — you have
   not deleted anything yet.)
6. **Delete the DB rows.** Only when step 5 is fully green, on **both** DBs:
   `DELETE FROM dbo.AppSettings WHERE SettingKey = 'LocalEncryptionKey';`
   (optionally as `db/data_updates/2026-09-08_handoff_63_drop_local_encryption_key.py`,
   H52 pattern).
7. **Re-verify** — repeat step 5's checks. The env var is now the sole key and
   the old keys are retired.
8. **Purge the local artifacts that hold old key + ciphertext** (do this — the
   SMTP password and Anthropic key are recoverable from any of them):
   - Delete `db/TenantCRM_full.sql`, `db/TenantCRM_azure.sql`,
     `db/TenantCRM_Test_azure.sql` (all gitignored, regenerate from Azure later
     if needed — a fresh export post-rotation carries only `NEW`-key ciphertext).
   - Delete / move offline `C:\Inspirion\Dev\TenantCRM\Database\TenantCRM_Azure.bacpac`,
     `…\TenantCRM_Backup\`, `…\TenantCRM_Test_Backup\`.
   - No git action (history is clean — see Verified).
9. **Optional but recommended — rotate the underlying credentials too.** Those
   files exposed the *plaintext* SMTP password and Anthropic API key at rest.
   Issue a new SMTP app password and a new Anthropic key, save them in Admin
   Settings (both DBs). Independent of the Fernet rotation; do it whenever.

### Step 6 — roadmap

- `### Cycle 0.4 …` heading → `**complete <date> (Handoff 63)**` with a short
  note; progress-log entry; **Stage 0 is now complete** — update the "Next"
  line and the "Gate 0" note.

---

## Do Not Touch

| What | Why |
|---|---|
| `pages/tally_import.py`, `TENANTCRM_FERNET_KEY` | Separate key / data, already env-based; unification is a later cleanup |
| `pages/settings.py` (+ its `_vN`) | Dead module; not imported anywhere live |
| `encrypt_value` / `decrypt_value` bodies & signatures, all call sites | Only `get_fernet`'s internals change |
| `dbo.EmailConfig`, `dbo.AIConfig` schema / columns | Untouched. **No automatic or bulk re-encryption in code** — Mark re-saves the four secrets (SMTP password + Anthropic key, on each of Prod and Test) through Admin Settings during the rotation runbook |
| `_validate_sql_config` / import-time checks | `get_fernet` stays lazy — app still boots with the var unset |
| Tenant SSN/DL encryption | Different subsystem |
| `db/history/` | This is a data-row delete, not schema |

---

## Validation Checklist

### A — `_fernet()` behaviour, isolated subprocess (no DB)

- [ ] `LUCIDPM_FERNET_KEY` unset → `get_fernet("x")` raises `ConfigError` naming
      the var.
- [ ] `LUCIDPM_FERNET_KEY=" , "` (only whitespace / separators) → **same
      `ConfigError`**, not `IndexError`.
- [ ] one valid key → returns a `Fernet`; `encrypt_value` then `decrypt_value`
      round-trips a string.
- [ ] two valid keys (`k1,k2`) → returns a `MultiFernet`; a token made with
      `Fernet(k2)` still `decrypt_value`s; new `encrypt_value` output decrypts
      under `Fernet(k1)`.
- [ ] `LUCIDPM_FERNET_KEY=not-a-key` → `ConfigError` ("invalid Fernet key").
- [ ] trailing comma / surrounding spaces (`" k1 , "`) → treated as one key, no
      crash.

### B — real old-key ciphertext still decrypts (Codex, pre-commit)

- [ ] With `LUCIDPM_FERNET_KEY=<OLD_PROD>`, in a subprocess,
      `decrypt_value(<a real EmailConfig.PasswordEncrypted from TenantCRM>,
      "TenantCRM")` returns the known SMTP password. (Mark supplies the
      ciphertext + expected plaintext out-of-band; nothing secret in the commit.)
- [ ] With `LUCIDPM_FERNET_KEY=<NEW>,<OLD_PROD>,<OLD_TEST>` the same call still
      works and a fresh `encrypt_value` round-trips.

### C — rotation runbook, step 4 (new key alongside old) — Mark

- [ ] `reflex run` boots with the old `.env` unchanged.
- [ ] `LUCIDPM_FERNET_KEY=<NEW>,<OLD_PROD>[,<OLD_TEST>]` set: Admin Settings →
      Email + AI show *configured* on **both** Prod and Test; re-save the SMTP
      password and API key on each; a test email sends; "Test AI connection"
      succeeds.
- [ ] With `LUCIDPM_FERNET_KEY` unset entirely: those actions fail with a clear
      message (page `try/except` catches the `ConfigError`); the app still boots.

### D — after `LUCIDPM_FERNET_KEY=<NEW>` only + row deleted (both DBs) — Mark

- [ ] With just `<NEW>`: email + AI checks pass on both DBs (proves everything
      was re-encrypted under it).
- [ ] `SELECT … WHERE SettingKey = 'LocalEncryptionKey'` → **0 rows** in
      `TenantCRM` and `TenantCRM_Test`.
- [ ] Same checks pass again after the delete.

### E — regression

- [ ] `python -c "import LucidPM.LucidPM"` exits 0; `reflex run` compiles.
- [ ] `grep -n "Fernet.generate_key\|MERGE dbo.AppSettings" LucidPM/state.py`
      → no hits (the auto-generate path is gone).
- [ ] `grep -rn "LocalEncryptionKey" LucidPM/` → hits only in dead
      `settings.py` / `_vN` files; no live code reads or writes it.
- [ ] `grep -n "LUCIDPM_FERNET_KEY\|LocalEncryptionKey" docs/Database.md` →
      Database.md describes the env var, not the DB row.
- [ ] After runbook step 8: `rg -l "LocalEncryptionKey|PasswordEncrypted|APIKeyEncrypted" db/`
      → nothing (the three `TenantCRM*.sql` exports are gone).

---

## How to Deliver This

1. Codex: Steps 1–4, 4b, and Step 6's roadmap edits. Run checklist **A**, **E**,
   and **B** (Mark supplies one real ciphertext value + expected plaintext, kept
   out of the commit). Commit — e.g.
   `Fernet config key from LUCIDPM_FERNET_KEY, not the database (H63, Cycle 0.4)`.
2. Mark: run the Step 5 **rotation** runbook (checklist **C** then **D**).
   Optionally land the `db/data_updates/` delete script as its own commit.
3. Move this doc to `Completed Handoffs/`; roadmap progress log; **Stage 0
   complete**.

`state.py`'s `_vN` siblings were archived under H58 (`d18a256`) — none to clean.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  LucidPM\state.py            ← Step 1 (get_fernet -> _fernet, one import)
  .env.example                ← Step 2
  docs\DeveloperSetup.md      ← Step 3 (§5 Secrets)
  docs\Deployment.md          ← Step 4 (known-blockers)
  docs\Database.md            ← Step 4b (§ Secrets and encryption, lines 36–41)
  db\data_updates\2026-09-08_handoff_63_drop_local_encryption_key.py  ← Step 5.6 (optional)
  Undelivered Handoffs\Azure Migration Roadmap.md  ← Step 6

Rotation runbook (Mark, per DB): extract OLD keys -> generate NEW -> .env NEW,OLD... ->
  re-save secrets on both DBs -> verify under NEW alone -> DELETE the rows -> re-verify.
```

---

*`get_fernet` stops reading its own key out of the database it's meant to
protect. One env var, `LUCIDPM_FERNET_KEY`, comma-separated (`MultiFernet`) for
rotation and for the migration off the old per-DB keys; fail-fast when unset or
empty; lazy, so the app still boots. The migration generates a fresh key, not a
copy of the old one — and git history was checked clean, so there's no
filter-repo tail. After the rows are gone from both databases, Stage 0 of the
Azure migration is done.*
