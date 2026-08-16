/*
Lucido Property Manager - Task 1 Schema Patch
Adds TenantID to LeaseGeneratedDocuments.
Run against TenantCRM_Test first, then production after validation.
*/

IF COL_LENGTH('dbo.LeaseGeneratedDocuments', 'TenantID') IS NULL
BEGIN
    ALTER TABLE dbo.LeaseGeneratedDocuments
        ADD TenantID INT NULL;

    INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
    SELECT
        '20260426_Task1_Add_TenantID_To_LeaseGeneratedDocuments',
        SYSDATETIME(),
        SUSER_SNAME(),
        'Added TenantID INT NULL to LeaseGeneratedDocuments for direct tenant lookup in generated lease packages.'
    WHERE OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL;
END;
GO

/* Optional backfill for existing generated documents */
UPDATE gd
SET gd.TenantID = l.TenantID
FROM dbo.LeaseGeneratedDocuments gd
INNER JOIN dbo.Leases l ON gd.LeaseID = l.LeaseID
WHERE gd.TenantID IS NULL;
GO
