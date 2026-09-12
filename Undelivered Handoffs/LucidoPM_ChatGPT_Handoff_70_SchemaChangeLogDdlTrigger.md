# LucidoPM — ChatGPT Handoff 70
*Auto-populate `dbo.SchemaChangeLog` via a DDL trigger, so future schema changes can't go unlogged the
way 24 of them already have*
*Prepared: 2026-09-12*
*Standing backlog item, no Azure dependency. LOW risk to the app (touches no application code, no
table the app reads/writes), MEDIUM risk to get exactly right on the first try (a badly-written DDL
trigger can block every future schema change if it isn't defensive about its own failure modes — see
The Fix).*

---

## What This Is

`dbo.SchemaChangeLog` (`ScriptName`, `AppliedOn`, `AppliedBy`, `Notes`) already exists in both
databases and turned out to be the real authoritative schema history — more reliable than the
`db/history/` `.sql` files themselves, per `db/history/CHANGELOG.md`'s own accounting: **36 real
changes logged in `TenantCRM_Test`, but only 11 still have a surviving, runnable script file.** The
other 24-25 got logged because someone remembered to write the `INSERT INTO SchemaChangeLog` line (or
an equivalent one-off insert) at the time, but the actual script that made the change was never saved.
The log is exactly as complete as human discipline made it, no more.

**The fix:** a database-level DDL trigger that fires automatically on schema-changing statements and
writes its own row via `EVENTDATA()` — the SQL Server function that returns the actual executed
command text as XML. This flips the guarantee from "logged if someone remembered" to "logged because
the database itself can't make the change without it," and captures the literal T-SQL that ran (up to
`Notes`' existing 1000-character limit — truncated with a visible marker beyond that, see The Fix), not
a human's after-the-fact description — so even a change made ad hoc in SSMS with nothing saved to disk
still leaves a record.

**This is not a data-loss recovery for the 24-25 already-missing scripts** — those are gone, this
doesn't reconstruct them (`db/history/CHANGELOG.md` already documents what's known about each). It
only prevents the gap from growing further.

---

## Current State

**Exact schema, confirmed from `db/baseline_schema.sql`:**
```sql
CREATE TABLE dbo.[SchemaChangeLog] (
    [SchemaChangeLogID] INT IDENTITY(1,1) NOT NULL,
    [ScriptName] NVARCHAR(255) NOT NULL,
    [AppliedOn] DATETIME2(0) NOT NULL DEFAULT (sysdatetime()),
    [AppliedBy] NVARCHAR(128) NOT NULL DEFAULT (suser_sname()),
    [Notes] NVARCHAR(1000) NULL,
    CONSTRAINT [PK_SchemaChangeLog] PRIMARY KEY CLUSTERED ([SchemaChangeLogID])
);
```
**`ScriptName` carries a `UNIQUE` index** (`db/baseline_schema.sql` actually shows two duplicate ones,
`UQ_SchemaChangeLog_ScriptName` and `UX_SchemaChangeLog_ScriptName` — a pre-existing oddity, not this
handoff's job to clean up). This matters a great deal for the trigger's design (see below) — it's the
reason a naive "just INSERT on every DDL event" trigger is a real risk, not a nitpick.

**Today's manual pattern**, confirmed directly in `db/history/001_...sql:150-159` and repeated across
every script in `db/history/`:
```sql
IF NOT EXISTS (SELECT 1 FROM dbo.SchemaChangeLog WHERE ScriptName = @ScriptName)
BEGIN
    INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
    VALUES (@ScriptName, SYSDATETIME(), @AppliedBy, @Notes);
END;
```
`@ScriptName` is the script's own filename, `@Notes` a short human-written description — clean,
readable, and exactly what `CHANGELOG.md`'s table links against. **This pattern is not being removed
retroactively** — only the guidance for *future* scripts changes (see The Fix, Step 3).

**Two real design risks a naive implementation would hit — both must be handled, not left open:**
1. **`ScriptName`'s `UNIQUE` constraint can fail the trigger's own `INSERT`.** A DDL trigger runs
   inside the same transaction as the triggering statement; if the trigger's `INSERT` throws an
   unhandled error, SQL Server rolls back the *triggering DDL statement itself* — meaning a broken
   trigger could silently block every future `CREATE`/`ALTER`/`DROP` in the database. The trigger must
   (a) construct a `ScriptName` value that's unique-by-construction for auto-logged rows (never
   collides with a manual entry's real filename, and doesn't collide with itself on rapid repeated
   DDL), and (b) wrap its own `INSERT` in `TRY/CATCH` so a logging failure can **never** block the
   actual schema change — logging is a nice-to-have, not allowed to become a blocker.
2. **Scope.** `FOR DDL_DATABASE_LEVEL_EVENTS` is SQL Server's broadest database-scoped event group —
   dozens of event types including `GRANT_DATABASE`/`DENY`/`REVOKE`, `CREATE_USER`, `CREATE_STATISTICS`,
   and other noise that isn't a "schema change" in the sense this table is meant to track. Firing on
   literally everything would flood the log. The Fix below scopes it to a specific, curated event list.

**Not yet verified against a live server this session** — the trigger design below is grounded in
`EVENTDATA()`'s documented XML shape, but the exact node paths and Azure SQL Database's support for
database-scoped DDL triggers (as opposed to server-scoped ones, which Azure SQL does *not* support)
should be confirmed with a real `CREATE TRIGGER` + a real `ALTER TABLE` against `TenantCRM_Test`
before treating this as final — see Step 0.

---

## The Fix

### Step 0 — verify against `TenantCRM_Test` first (local SQL Server Express)

Create the trigger (Step 1) against Test only, run one harmless `ALTER TABLE ... ADD` /
`... DROP COLUMN` round-trip on a scratch column, and confirm:
- Exactly one row lands in `SchemaChangeLog`, with the expected `ScriptName`/`Notes` shape.
- The `Notes` column actually contains the executed `ALTER TABLE` text, not `NULL` (confirms the
  `TSQLCommand/CommandText` XPath is correct for this SQL Server version).
- Running the same statement twice produces two distinct rows (no `ScriptName` collision) — including
  when run twice in immediate succession (the `NEWID()` suffix, not the timestamp, is what's actually
  being proven here).
- Deliberately breaking the trigger body (e.g., temporarily commenting out the `TRY/CATCH`) and
  forcing a `ScriptName` collision does **not** roll back the `ALTER TABLE` once the `TRY/CATCH` is
  back in place — i.e., prove the defensiveness actually works, don't just trust the code.
- Run one deliberately long `ALTER TABLE` (padding it with comments or a long column list past 1000
  characters) and confirm the resulting `Notes` value is truncated to `...[TRUNCATED]` rather than
  either erroring or silently ending mid-statement with no indication.

Only after this passes, repeat for local `TenantCRM`, then (separately, since Azure SQL Database does
not support every DDL-trigger feature server-scoped SQL Server does) verify once against Azure
`TenantCRM_Test` before rolling out to Azure `TenantCRM`.

### Step 1 — the trigger

```sql
CREATE TRIGGER trg_LogSchemaChanges
ON DATABASE
FOR
    CREATE_TABLE,     ALTER_TABLE,     DROP_TABLE,
    CREATE_INDEX,     ALTER_INDEX,     DROP_INDEX,
    CREATE_VIEW,      ALTER_VIEW,      DROP_VIEW,
    CREATE_PROCEDURE, ALTER_PROCEDURE, DROP_PROCEDURE,
    CREATE_FUNCTION,  ALTER_FUNCTION,  DROP_FUNCTION,
    CREATE_TRIGGER,   ALTER_TRIGGER,   DROP_TRIGGER
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        DECLARE @data XML = EVENTDATA();
        DECLARE @eventType   NVARCHAR(100) = @data.value('(/EVENT_INSTANCE/EventType)[1]', 'nvarchar(100)');
        DECLARE @schemaName  NVARCHAR(128) = @data.value('(/EVENT_INSTANCE/SchemaName)[1]', 'nvarchar(128)');
        DECLARE @objectName  NVARCHAR(128) = @data.value('(/EVENT_INSTANCE/ObjectName)[1]', 'nvarchar(128)');
        DECLARE @loginName   NVARCHAR(128) = @data.value('(/EVENT_INSTANCE/LoginName)[1]', 'nvarchar(128)');
        DECLARE @rawCommand  NVARCHAR(MAX) = @data.value('(/EVENT_INSTANCE/TSQLCommand/CommandText)[1]', 'nvarchar(max)');

        -- Notes is NVARCHAR(1000) (see Current State) — truncate explicitly, with a visible marker,
        -- rather than let an implicit cast silently cut a long command off mid-statement.
        DECLARE @suffix NVARCHAR(20) = N' ...[TRUNCATED]';
        DECLARE @commandText NVARCHAR(1000) =
            CASE WHEN @rawCommand IS NULL THEN NULL
                 WHEN LEN(@rawCommand) > 1000 THEN LEFT(@rawCommand, 1000 - LEN(@suffix)) + @suffix
                 ELSE @rawCommand END;

        -- ScriptName has a UNIQUE index (see Current State) — a timestamp alone isn't a guaranteed-unique
        -- defense (clock resolution isn't guaranteed to match the datatype's stated precision on every
        -- host), so append a NEWID() fragment. This is the actual collision guarantee; the timestamp is
        -- for human readability only.
        DECLARE @scriptName NVARCHAR(255) =
            '[AUTO] ' + ISNULL(@eventType, 'DDL')
            + CASE WHEN @objectName IS NOT NULL
                   THEN ' on ' + ISNULL(@schemaName + '.', '') + @objectName ELSE '' END
            + ' @ ' + CONVERT(NVARCHAR(30), SYSDATETIME(), 121)
            + ' #' + LEFT(CONVERT(NVARCHAR(36), NEWID()), 8);
        IF LEN(@scriptName) > 255 SET @scriptName = LEFT(@scriptName, 255);

        INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
        VALUES (@scriptName, SYSDATETIME(), ISNULL(@loginName, SUSER_SNAME()), @commandText);
    END TRY
    BEGIN CATCH
        -- Logging must never block the actual schema change (e.g. a same-instant
        -- ScriptName collision against the UNIQUE index). Swallow and move on.
    END CATCH
END;
```
Design notes, matching the two risks in Current State plus two review corrections:
- `ScriptName`'s actual collision defense is the appended `NEWID()` fragment, not the timestamp.
  Tested empirically against this local instance: `CONVERT(NVARCHAR, SYSDATETIME(), 121)` on a
  `datetime2` source actually returned full 100ns precision here (`2026-09-12 16:30:44.8840759`), not
  the millisecond precision style 121 is sometimes described as giving for legacy `datetime` — but
  that's a property of one instance's version/behavior, not something to rely on across local SQL
  Express, Azure SQL, and whatever's next. System clock resolution can also be coarser than the
  datatype's stated precision on some hosts regardless. The timestamp stays for human readability when
  scanning `SchemaChangeLog`; the `NEWID()` suffix is what actually guarantees no collision against the
  `UNIQUE` index, independent of clock behavior on any given host.
- **`Notes`' 1000-character limit is real and explicit, not glossed over.** A DDL statement longer than
  1000 characters gets truncated with a visible `...[TRUNCATED]` marker rather than silently cut off —
  so "captures the executed T-SQL" is accurate for anything under the limit and honestly marked when
  it isn't, instead of overclaiming exact fidelity for every possible statement length. The schema
  itself isn't changed (see Do Not Touch) — this handoff works within `NVARCHAR(1000)`, it doesn't
  widen it.
- The whole body is wrapped in `TRY/CATCH` with an intentionally empty `CATCH` — a logging failure is
  swallowed, never propagated back to fail the triggering `CREATE`/`ALTER`/`DROP`.
- Event list is curated to schema objects (`TABLE`, `INDEX`, `VIEW`, `PROCEDURE`, `FUNCTION`,
  `TRIGGER`) — deliberately excludes `DDL_DATABASE_LEVEL_EVENTS`' broader set (permissions, users,
  roles, statistics, etc.), which isn't what `SchemaChangeLog` has ever meant.
- `AppliedBy` uses `EVENTDATA()`'s own `LoginName` (falling back to `SUSER_SNAME()`) rather than the
  column's own `DEFAULT` — this is the login that actually issued the DDL, which is what the column is
  for, and stays correct even under impersonation.

### Step 2 — roll out to all 4 database targets

Both local databases first (where schema changes actually happen today), then both Azure copies —
same "verify one at a time" sequencing as Step 0, not a single script fired at all four blind:
1. Local `TenantCRM_Test` (already done in Step 0's verification).
2. Local `TenantCRM`.
3. Azure `TenantCRM_Test`.
4. Azure `TenantCRM`.

If Azure SQL Database rejects any part of this syntax (unexpected, but Step 0 flagged it as unverified)
— stop and report back rather than adapting it ad hoc; the trigger needs to be identical across all
four targets, not a variant per environment.

### Step 3 — decide, and document, what happens to the manual `INSERT INTO SchemaChangeLog` lines

Recommendation (this is the "decision" CLAUDE.md's backlog note flagged, given a concrete default
rather than left open):
- **Stop adding the manual `INSERT INTO SchemaChangeLog` block to new `db/history/` scripts** — the
  trigger now logs the same `CREATE`/`ALTER`/`DROP` automatically and more reliably than a
  human-remembered follow-up statement, which is exactly the gap this handoff exists to close.
- **Do not touch existing `db/history/*.sql` files** — their manual inserts are historical fact, not
  boilerplate to clean up (see Do Not Touch).
- **Accept the trade-off explicitly, don't let it surprise anyone later:** the trigger's `Notes` will
  be raw executed T-SQL, not a human-written one-line description like `db/history/`'s convention has
  used until now. Less immediately readable per row, but complete by construction — nothing can be
  forgotten. If a future script wants a *readable* description in `Notes` in addition to the raw
  command text the trigger captures, that's a second row for the same change (acceptable — the two
  serve different purposes) rather than something to try to unify into one.
- Update `docs/Database.md`'s line *"any future schema-changing script should keep writing to it"* to
  reflect this — future scripts don't need their own insert, the trigger is now what "keeps writing to
  it."

---

## Do Not Touch

- **Existing `db/history/*.sql` scripts and their manual `INSERT INTO SchemaChangeLog` blocks.**
  Historical record, not boilerplate — don't remove or "clean up" retroactively.
- **The 24-25 already-unrecoverable log entries and their missing scripts.** Nothing to fix; this
  handoff prevents the gap from growing, it doesn't fill it in.
- **The duplicate `UQ_SchemaChangeLog_ScriptName` / `UX_SchemaChangeLog_ScriptName` indexes.** A
  pre-existing oddity, separately trackable if it ever matters, not this handoff's job.
- **`db/generate_baseline_schema.py`.** Confirmed by reading it directly: it only queries
  `sys.tables`, `sys.foreign_keys`, and `sys.indexes` — no `sys.triggers` query exists at all, and its
  own docstring scopes it to "a deterministic, from-scratch CREATE TABLE..." generator. **Regenerating
  `db/baseline_schema.sql` will NOT include `trg_LogSchemaChanges`** — an earlier draft of this handoff
  claimed it would, which was wrong (see Validation Checklist and File Locations for the corrected
  claim). Extending the generator to also emit database-scoped DDL triggers is real, separate work with
  its own testing burden — out of scope for this handoff, tracked as a follow-up, not a blocker to
  calling H70 done.
- **`db/baseline_schema.sql`** (the file itself). Don't hand-edit it to add the trigger by hand either —
  if the generator doesn't cover it, the honest state is "the baseline doesn't reflect this trigger
  yet," not a hand-patched baseline that looks generator-produced but isn't.
- **Application code.** Nothing in `LucidPM/` reads or writes `SchemaChangeLog` today; this handoff
  doesn't change that.

---

## Validation Checklist

- [ ] Step 0's live verification passed against local `TenantCRM_Test` — single row per DDL statement,
      `Notes` contains real command text, repeated identical statements don't collide, and a
      deliberately-broken trigger body proved the `TRY/CATCH` actually protects the triggering
      statement (not just assumed from reading the code).
- [ ] Trigger created identically (verified via `sp_helptext` or an object-definition diff) on all 4
      targets: local `TenantCRM_Test`, local `TenantCRM`, Azure `TenantCRM_Test`, Azure `TenantCRM`.
- [ ] Azure SQL Database confirmed to accept database-scoped DDL triggers with this exact syntax — not
      assumed from general SQL Server documentation.
- [ ] A real `db/history/`-style schema change (e.g. the next legitimate `ALTER TABLE`) produces
      **two** rows where a manual insert is also present (one `[AUTO] ...`, one the script's own) —
      confirms this is understood as intentional overlap, not a bug, until Step 3's guidance is
      followed for new scripts.
- [ ] `docs/Database.md` updated per Step 3.
- [ ] Confirmed (not assumed) that `db/generate_baseline_schema.py` does not emit
      `trg_LogSchemaChanges` after regeneration — its current scope is tables/FKs/indexes only. Note
      this gap in `docs/Database.md` alongside Step 3's update rather than silently leaving the
      baseline out of sync with no explanation.

**Done when:** all 4 database targets auto-log schema-changing DDL without any script needing to
remember to do so, verified live (not just by code review), with `docs/Database.md` reflecting both
the new trigger and the known baseline-generator gap. Extending
`db/generate_baseline_schema.py` to cover triggers is a separate, optional follow-up — not required
for this handoff to be done.

---

## File Locations

```
c:\Inspirion\Dev\TenantCRM\LucidPM\
  db\history\<next-numbered>_ddl_schema_change_log_trigger.sql   ← new, Step 1's CREATE TRIGGER,
                                                                     run against all 4 targets per
                                                                     Step 2 (this script logs itself
                                                                     manually, per today's convention —
                                                                     it's the LAST script to use the
                                                                     old pattern, everything after it
                                                                     relies on the trigger instead)
  docs\Database.md                                                ← Step 3's guidance update, plus a
                                                                     note that db/generate_baseline_
                                                                     schema.py does not (yet) emit
                                                                     this trigger on regeneration
```
`db/baseline_schema.sql` is deliberately **not** listed as an output here — confirmed by reading
`db/generate_baseline_schema.py` that it has no `sys.triggers` query at all, so regenerating it will
not include `trg_LogSchemaChanges`. See Do Not Touch.

Reference material already in the repo:
```
db\history\CHANGELOG.md                    ← the 24-25 already-missing scripts this trigger prevents
                                               growing further; the "authoritative timeline" this
                                               handoff makes more complete going forward
db\history\001_...lease_documents_mvp...sql:150-159   ← today's manual INSERT pattern, byte-verified
db\baseline_schema.sql:383-390                          ← SchemaChangeLog's exact current schema
docs\Database.md                            ← the line this handoff's Step 3 updates
```
