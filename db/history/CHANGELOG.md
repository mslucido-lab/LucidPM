# Schema Change History

This is the authoritative timeline, pulled directly from `dbo.SchemaChangeLog` (queried live on 2026-08-17). It is **not** derived from the files in this folder — it's the other way around: the files that survive are cross-referenced against this log, not the reverse.

**Counts:** `TenantCRM_Test` has 37 logged changes. `TenantCRM` (production) has 36 — missing only `20260426_Task1_Add_TenantID_To_LeaseGeneratedDocuments` (see note below; this is a logging gap, not a real schema difference).

**Of these 36 real changes, only 11 have a surviving, runnable SQL file** (`db/history/00N_*.sql`). One more (`task3_lease_template_sections_isactive.sql`) was applied but never logged — its file survives in `db/history/untracked/`. One logged entry (`lease_section_schema_cleanup_v2_8_6`) is a changelog-only marker with no real DDL in its file — also in `db/history/untracked/`. **The other 24 changes have no recoverable SQL at all** — the script that made them was never saved to this repo. All that survives for those is what's in this table: the date, who ran it, and the Notes text they wrote at the time.

Don't try to rebuild a database by replaying this list — most of it can't be replayed (the SQL is gone), and even the parts that can are secondary to the truth. **Use `db/baseline_schema.sql` for that** — it's a live, complete, regeneratable snapshot of the current schema, not a history replay. This file exists to answer "when and why did X change," not "how do I build this from scratch."

---

| # | Date (Test) | Script | Applied By | File |
|---|---|---|---|---|
| 1 | 2026-04-02 15:22 | `workitems_v1_16_dashboard_and_script_tracking.sql` | msluc | *(missing — creates `SchemaChangeLog` itself; no WorkItems schema change)* |
| 2 | 2026-04-04 11:46 | `workitems_v1_17_1_bids.sql` | msluc | *(missing — adds `WorkItemBids`)* |
| 3 | 2026-04-05 15:34 | `workitems_v1_17_4_bid_action_link.sql` | msluc | *(missing — adds `WorkItemActions.WorkItemBidID`)* |
| 4 | 2026-04-05 15:48 | `workitems_v1_17_5_action_vendor_assignment.sql` | msluc | *(missing — adds `WorkItemActions.VendorID`)* |
| 5 | 2026-04-10 21:19 | `2026-04-10_v1.17.6.0_property_suites.sql` | msluc | *(missing — adds `PropertySuites`, `Tenants`/`Leases.SuiteID`)* |
| 6 | 2026-04-10 21:28 | `2026-04-10_v1.17.6.1_property_suites_catchup.sql` | msluc | *(missing, no Notes recorded)* |
| 7 | 2026-04-10 21:59 | `2026-04-10_v1.17.6.4_properties_rent_roll_metadata.sql` | msluc | *(missing, no Notes recorded)* |
| 8 | 2026-04-11 08:41 | `2026-04-11_v1.17.7.0_property_financials.sql` | msluc | *(missing — adds `PropertyFinancials`)* |
| 9 | 2026-04-21 18:56 | `terminology_migration_prospect_to_applicant` | msluc | *(missing — renamed "Prospect" status to "Applicant")* |
| 10 | 2026-04-22 18:19 | `schema_cleanup_001` | Mark | *(missing — dropped `TenantSensitiveInfo`, duplicate of `ContactSensitiveInfo`)* |
| 11 | 2026-04-22 18:19 | `schema_cleanup_002` | Mark | *(missing — removed duplicate FKs on `WorkItems.StatusID`/`CategoryID`)* |
| 12 | 2026-04-22 18:19 | `schema_cleanup_003` | Mark | *(missing — renamed `Actions` to `Actions_legacy`)* |
| 13 | 2026-04-22 18:19 | `schema_cleanup_004` | Mark | *(missing — dropped `Communications_old`)* |
| 14 | 2026-04-22 18:19 | `schema_cleanup_005` | Mark | *(missing — added PKs to `TenantStatuses`/`TenantTypes`)* |
| 15 | 2026-04-22 18:19 | `schema_cleanup_006` | Mark | *(missing — reviewed `PropertySuites` square-footage columns)* |
| 16 | 2026-04-24 15:39 | `20260424_lease_documents_mvp_schema.sql` | msluc | [`001_...`](001_2026-04-24_1539_lease_documents_mvp_schema.sql) |
| 17 | 2026-04-24 23:16 | `lease_templates_admin_v3_settings_schema_with_changelog.sql` | msluc | [`002_...`](002_2026-04-24_2316_lease_templates_admin_v3_settings_schema.sql) |
| 18 | 2026-04-25 08:45 | `lease_package_builder_v1_schema_with_changelog.sql` | msluc | [`003_...`](003_2026-04-25_0845_lease_package_builder_v1_schema.sql) |
| 19 | 2026-04-25 12:36 | `lease_generated_documents.sql` | msluc | [`004_...`](004_2026-04-25_1236_lease_generated_documents.sql) |
| 20 | 2026-04-25 13:19 | `lease_document_content_migration_v2_6_2.sql` | msluc | [`005_...`](005_2026-04-25_1319_lease_document_content_migration_v2_6_2.sql) *(saved on disk as `lease_document_pieces_tokenization.sql` — renamed here to match what it actually logged itself as)* |
| 21 | 2026-04-25 13:23 | `lease_document_schema_v2_6_3_fixed.sql` | msluc | [`006_...`](006_2026-04-25_1323_lease_document_schema_v2_6_3_fixed.sql) |
| 22 | 2026-04-26 09:48 | `20260426_Task1_Add_TenantID_To_LeaseGeneratedDocuments` | msluc | [`007_...`](007_2026-04-26_0948_task1_add_tenantid_to_leasegenerateddocuments.sql) — **Test only, missing from Prod's log** (column confirmed present in both DBs regardless — see note below) |
| 23 | 2026-04-26 10:24 | `20260426_Task2_Lease_Template_Section_Tables` | msluc | [`008_...`](008_2026-04-26_1024_task2_lease_template_section_tables.sql) |
| — | *(2026-04-26, ~12:35, not logged)* | *(untracked)* | msluc | [`untracked/task3_lease_template_sections_isactive.sql`](untracked/task3_lease_template_sections_isactive.sql) — applied (confirmed live: `LeaseTemplateSections.IsActive` exists), never wrote a log entry |
| 24 | 2026-04-27 19:11 | `schema_lease_sections_rename.sql` | msluc | [`009_...`](009_2026-04-27_1911_schema_lease_sections_rename.sql) — the real `Piece → Section` table/column rename |
| 25 | 2026-04-27 19:40 | `lease_section_schema_cleanup_v2_8_6` | msluc | [`untracked/lease_section_schema_cleanup_v2_8_6.sql`](untracked/lease_section_schema_cleanup_v2_8_6.sql) — **log-only marker, contains no DDL**; the rename it describes was already done by #24 above |
| 26 | 2026-04-30 12:53 | `phase5_clause_library_columns.sql` | msluc | [`010_...`](010_2026-04-30_1253_phase5_clause_library_columns.sql) |
| 27 | 2026-05-01 09:18 | `phase5_sprint2_nullable_source_document.sql` | msluc | [`011_...`](011_2026-05-01_0918_phase5_sprint2_nullable_source_document.sql) |
| 28 | 2026-05-07 18:48 | `screening_phase1_create_tenantscreenings.sql` | msluc | *(missing — creates `TenantScreenings`)* |
| 29 | 2026-05-07 18:48 | `screening_phase1_5_alter_and_factors.sql` | msluc | *(missing — adds scoring columns + `TenantScreeningFactors`)* |
| 30 | 2026-05-09 14:44 | `tenant_references_create.sql` | msluc | *(missing — creates `TenantReferences`)* |
| 31 | 2026-05-09 14:44 | `contacts_emergency_contact_flag.sql` | msluc | *(missing — adds `Contacts.IsEmergencyContact`)* |
| 32 | 2026-05-17 10:11 | `email_ai_config_schema.sql` | msluc | *(missing — creates `EmailConfig`, `AIConfig`)* |
| 33 | 2026-05-20 11:24 | `add_lease_status.sql` | msluc | *(missing — adds `Leases.LeaseStatus`)* |
| 34 | 2026-05-20 12:17 | `add_lease_termination_date.sql` | msluc | *(missing — adds `Leases.LeaseTerminationDate`)* |
| 35 | 2026-05-30 18:54 | `DataCleanse_AddressLabels_01.sql` | msluc | *(missing — one-time data cleanse, not pure schema)* |
| 36 | 2026-06-04 00:55 | `lease_amendment_schema.sql` | msluc | *(missing — adds `Leases.ParentLeaseID`, `Leases.ExecutionDate`)* |
| 37 | 2026-08-25 23:26 | `add_tenant_isdba_flag.sql` | msluc | [`012_...`](012_2026-08-25_2326_add_tenant_isdba_flag.sql) — adds `Tenants.IsDBA` for DBA-aware lease merge tokens |

---

## Confirmed never applied (kept for context, not history)

Two files in `db/history/skipped/` were checked against the log and against the live schema directly — neither's identity appears anywhere in `SchemaChangeLog`, and both were superseded by scripts that *did* run:

- `skipped/lease_document_schema_v2_6_2.sql` — superseded by #20 above (`lease_document_content_migration_v2_6_2.sql`, saved on disk as `lease_document_pieces_tokenization.sql`).
- `skipped/lease_documents_schema.sql` — an earlier draft with no `SchemaChangeLog` logging code at all, superseded by #16 above.

## Test vs. Prod

Functionally in sync as of 2026-08-17. Table lists are identical except `TenantCRM_Test` has one extra harmless leftover, `LeaseRentIncreaseTypes_Legacy_20260315_123957` (an old renamed-away table someone archived by suffixing rather than dropping — not in Prod). The one log-entry gap (#22, Task1) does **not** reflect an actual schema difference — `LeaseGeneratedDocuments.TenantID` was directly confirmed present in both databases; the column got added to Prod without its logging statement running (or without that logging succeeding).

## One naming oddity worth knowing about, not fixed here

Two separate, live tables currently coexist: **`LeaseGeneratedDocuments`** (created by #16, the actively-referenced one — FKs from `LeaseGeneratedDocumentSections` point at it) and **`GeneratedLeaseDocuments`** (created by #19, described as an "audit table" for merge/render snapshots). Turns out this is already known: `LucidPM/pages/lease_documents.py` has an existing "PHASE 1 - CLEANUP" TODO block (lines ~104-133) from a prior code review, and its Issue 3 says exactly this — `save_generated_lease_snapshot()` in `lease_merge.py` is dead code that "references wrong table (`GeneratedLeaseDocuments` vs `LeaseGeneratedDocuments`)" and should be deleted. So `GeneratedLeaseDocuments` is confirmed unused dead weight, not an active duplicate-data path — low urgency, already tracked in-code, not re-fixed here (out of scope for a schema-history reorganization).
