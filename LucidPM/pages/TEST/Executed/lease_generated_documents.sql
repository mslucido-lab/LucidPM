/*
Lucid Property Manager - Generated Lease Documents audit table
v0.1.0

Purpose:
Stores the exact merge context and rendered output created from a lease package.
Run against TEST first.
*/

IF OBJECT_ID('dbo.GeneratedLeaseDocuments', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.GeneratedLeaseDocuments
    (
        GeneratedLeaseDocumentID INT IDENTITY(1,1) NOT NULL
            CONSTRAINT PK_GeneratedLeaseDocuments PRIMARY KEY,
        TenantID INT NOT NULL,
        LeaseID INT NOT NULL,
        LeaseDocumentPackageID INT NULL,
        GeneratedOn DATETIME2(0) NOT NULL
            CONSTRAINT DF_GeneratedLeaseDocuments_GeneratedOn DEFAULT SYSUTCDATETIME(),
        OutputPath NVARCHAR(1000) NULL,
        MergeContextJson NVARCHAR(MAX) NULL,
        RenderedText NVARCHAR(MAX) NULL,
        CreatedBy NVARCHAR(100) NULL
    );
END;

IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
BEGIN
    INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
    VALUES
    (
        'lease_generated_documents.sql',
        GETDATE(),
        SUSER_SNAME(),
        'Created GeneratedLeaseDocuments audit table for lease package merge/render snapshots.'
    );
END;
