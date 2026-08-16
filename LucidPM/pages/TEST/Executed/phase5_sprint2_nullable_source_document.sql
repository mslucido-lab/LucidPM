-- Phase 5 Sprint 2: Make source document reference optional on LeaseDocumentSections.
-- Run against TenantCRM_Test first. Verify in SSMS. Then run against TenantCRM.

IF COL_LENGTH('dbo.LeaseDocumentSections', 'LeaseSourceDocumentID') IS NOT NULL
    AND COLUMNPROPERTY(OBJECT_ID('dbo.LeaseDocumentSections'), 'LeaseSourceDocumentID', 'AllowsNull') = 0
BEGIN
    ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN LeaseSourceDocumentID INT NULL;
END;

IF COL_LENGTH('dbo.LeaseDocumentSections', 'StartPage') IS NOT NULL
    AND COLUMNPROPERTY(OBJECT_ID('dbo.LeaseDocumentSections'), 'StartPage', 'AllowsNull') = 0
BEGIN
    ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN StartPage INT NULL;
END;

IF COL_LENGTH('dbo.LeaseDocumentSections', 'EndPage') IS NOT NULL
    AND COLUMNPROPERTY(OBJECT_ID('dbo.LeaseDocumentSections'), 'EndPage', 'AllowsNull') = 0
BEGIN
    ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN EndPage INT NULL;
END;

IF COL_LENGTH('dbo.LeaseDocumentSections', 'StoredFilePath') IS NOT NULL
    AND COLUMNPROPERTY(OBJECT_ID('dbo.LeaseDocumentSections'), 'StoredFilePath', 'AllowsNull') = 0
BEGIN
    ALTER TABLE dbo.LeaseDocumentSections ALTER COLUMN StoredFilePath NVARCHAR(1000) NULL;
END;

IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM dbo.SchemaChangeLog
        WHERE ScriptName = 'phase5_sprint2_nullable_source_document.sql'
    )
BEGIN
    INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
    VALUES (
        'phase5_sprint2_nullable_source_document.sql',
        GETDATE(),
        SUSER_SNAME(),
        'Made LeaseSourceDocumentID, StartPage, EndPage, StoredFilePath nullable on LeaseDocumentSections to support standalone clauses not derived from a source PDF.'
    );
END;
