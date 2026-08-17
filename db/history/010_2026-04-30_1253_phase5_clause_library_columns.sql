/*
Lucid Property Manager
Phase 5 - T1-1 Clause Library Schema Additions

Purpose:
Add clause-level metadata fields to LeaseDocumentSections.

Run order:
1. Run against TenantCRM_Test first.
2. Verify columns exist in SSMS.
3. Run against TenantCRM production.

This script is additive and non-breaking.
*/

IF COL_LENGTH('dbo.LeaseDocumentSections', 'ClauseTag') IS NULL
BEGIN
    ALTER TABLE dbo.LeaseDocumentSections
    ADD ClauseTag NVARCHAR(100) NULL;
END;

IF COL_LENGTH('dbo.LeaseDocumentSections', 'ArticleNumber') IS NULL
BEGIN
    ALTER TABLE dbo.LeaseDocumentSections
    ADD ArticleNumber NVARCHAR(20) NULL;
END;

IF COL_LENGTH('dbo.LeaseDocumentSections', 'DisplayLabel') IS NULL
BEGIN
    ALTER TABLE dbo.LeaseDocumentSections
    ADD DisplayLabel NVARCHAR(255) NULL;
END;

IF NOT EXISTS (
    SELECT 1
    FROM dbo.SchemaChangeLog
    WHERE ScriptName = 'phase5_clause_library_columns.sql'
)
BEGIN
    INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
    VALUES (
        'phase5_clause_library_columns.sql',
        GETDATE(),
        SUSER_SNAME(),
        'Added ClauseTag, ArticleNumber, DisplayLabel to LeaseDocumentSections for Phase 5 clause-level library'
    );
END;

SELECT
    COLUMN_NAME,
    DATA_TYPE,
    CHARACTER_MAXIMUM_LENGTH,
    IS_NULLABLE
FROM INFORMATION_SCHEMA.COLUMNS
WHERE TABLE_SCHEMA = 'dbo'
  AND TABLE_NAME = 'LeaseDocumentSections'
  AND COLUMN_NAME IN ('ClauseTag', 'ArticleNumber', 'DisplayLabel')
ORDER BY COLUMN_NAME;
