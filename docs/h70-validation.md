# H70 validation ? automatic schema-change logging

Validated 2026-09-12.

`db/history/013_2026-09-12_ddl_schema_change_log_trigger.sql` creates the database-level `trg_LogSchemaChanges` trigger. It records supported schema-object `CREATE`, `ALTER`, and `DROP` commands in `dbo.SchemaChangeLog` using `EVENTDATA()`.

## Deployment

The same versioned script was run successfully against all four targets:

- local `TenantCRM_Test`
- local `TenantCRM`
- Azure SQL `TenantCRM_Test`
- Azure SQL `TenantCRM`

Each target has `trg_LogSchemaChanges` with `parent_class_desc = DATABASE` and one manual history row for `013_2026-09-12_ddl_schema_change_log_trigger.sql`.

## Azure verification

On Azure `TenantCRM_Test`, a scratch `CREATE TABLE dbo.H70AzureScratch` followed by `ALTER TABLE ... ADD VerifiedAt DATETIME2 NULL` created two `[AUTO]` rows. The rows contained the executed command text, used `lucidadmin` as `AppliedBy`, and retained full GUID suffixes in unique `ScriptName` values.

The Azure Test and Azure Prod trigger definitions produced the same SHA-256 hash:

```text
3A1245FC463B943A8128A4BC1223C489BEE1538E1AE6F65FAD67DF4F7F2C4897
```

## Operating guidance

New schema scripts do not add manual `INSERT INTO dbo.SchemaChangeLog` statements. The trigger writes the automatic `[AUTO]` row. Existing history scripts remain unchanged, including their historical manual entries.

`db/generate_baseline_schema.py` does not currently export database-scoped DDL triggers. Therefore `db/baseline_schema.sql` deliberately does not include `trg_LogSchemaChanges`; generator support is separate follow-up work.
