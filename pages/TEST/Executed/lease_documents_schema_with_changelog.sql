/*
Lease Documents MVP schema with SchemaChangeLog logging
Lucid Property Manager

Purpose:
- Adds disk-based lease document metadata tables.
- No PDF blobs are stored in SQL Server.
- Logs the schema change to dbo.SchemaChangeLog.

Run against TenantCRM_Test first, then TenantCRM after validation.
*/

SET NOCOUNT ON;
SET XACT_ABORT ON;

BEGIN TRY
    BEGIN TRANSACTION;

    DECLARE @ScriptName NVARCHAR(255) = N'20260424_lease_documents_mvp_schema.sql';
    DECLARE @AppliedBy NVARCHAR(255) = SUSER_SNAME();
    DECLARE @Notes NVARCHAR(MAX) = N'Added Lease Documents MVP tables: LeaseSourceDocuments, LeaseDocumentPieces, LeaseGeneratedDocuments, LeaseGeneratedDocumentPieces. Uses file paths, not blobs.';

    /* Safety check: SchemaChangeLog should already exist in your database. */
    IF OBJECT_ID(N'dbo.SchemaChangeLog', N'U') IS NULL
    BEGIN
        RAISERROR('dbo.SchemaChangeLog does not exist. Create it first or run the baseline schema setup before this script.', 16, 1);
    END;

    IF OBJECT_ID(N'dbo.LeaseSourceDocuments', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseSourceDocuments (
            LeaseSourceDocumentID INT IDENTITY(1,1) NOT NULL,
            LeaseID INT NOT NULL,
            OriginalFileName NVARCHAR(255) NOT NULL,
            StoredFilePath NVARCHAR(1000) NOT NULL,
            PageCount INT NULL,
            DocumentStatus NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_Status DEFAULT (N'Uploaded'),
            UploadedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseSourceDocuments_UploadedOn DEFAULT (SYSDATETIME()),
            Notes NVARCHAR(MAX) NULL,
            CONSTRAINT PK_LeaseSourceDocuments PRIMARY KEY CLUSTERED (LeaseSourceDocumentID)
        );
    END;

    IF OBJECT_ID(N'dbo.LeaseDocumentPieces', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseDocumentPieces (
            LeaseDocumentPieceID INT IDENTITY(1,1) NOT NULL,
            LeaseSourceDocumentID INT NOT NULL,
            LeaseID INT NOT NULL,
            PieceType NVARCHAR(50) NOT NULL,
            PieceName NVARCHAR(255) NOT NULL,
            ExhibitCode NVARCHAR(50) NULL,
            StartPage INT NOT NULL,
            EndPage INT NOT NULL,
            StoredFilePath NVARCHAR(1000) NOT NULL,
            SortOrder INT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_SortOrder DEFAULT (0),
            IsReusable BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsReusable DEFAULT (0),
            CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseDocumentPieces_CreatedOn DEFAULT (SYSDATETIME()),
            Notes NVARCHAR(MAX) NULL,
            CONSTRAINT PK_LeaseDocumentPieces PRIMARY KEY CLUSTERED (LeaseDocumentPieceID)
        );
    END;

    IF OBJECT_ID(N'dbo.LeaseGeneratedDocuments', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseGeneratedDocuments (
            LeaseGeneratedDocumentID INT IDENTITY(1,1) NOT NULL,
            LeaseID INT NOT NULL,
            GeneratedFileName NVARCHAR(255) NOT NULL,
            StoredFilePath NVARCHAR(1000) NOT NULL,
            GeneratedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseGeneratedDocuments_GeneratedOn DEFAULT (SYSDATETIME()),
            PackageNotes NVARCHAR(MAX) NULL,
            CONSTRAINT PK_LeaseGeneratedDocuments PRIMARY KEY CLUSTERED (LeaseGeneratedDocumentID)
        );
    END;

    IF OBJECT_ID(N'dbo.LeaseGeneratedDocumentPieces', N'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseGeneratedDocumentPieces (
            LeaseGeneratedDocumentPieceID INT IDENTITY(1,1) NOT NULL,
            LeaseGeneratedDocumentID INT NOT NULL,
            LeaseDocumentPieceID INT NOT NULL,
            SortOrder INT NOT NULL,
            CONSTRAINT PK_LeaseGeneratedDocumentPieces PRIMARY KEY CLUSTERED (LeaseGeneratedDocumentPieceID)
        );
    END;

    /* Helpful indexes. Safe to re-run. */
    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_LeaseSourceDocuments_LeaseID' AND object_id = OBJECT_ID(N'dbo.LeaseSourceDocuments'))
        CREATE INDEX IX_LeaseSourceDocuments_LeaseID ON dbo.LeaseSourceDocuments (LeaseID);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_LeaseDocumentPieces_LeaseID' AND object_id = OBJECT_ID(N'dbo.LeaseDocumentPieces'))
        CREATE INDEX IX_LeaseDocumentPieces_LeaseID ON dbo.LeaseDocumentPieces (LeaseID, SortOrder);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_LeaseDocumentPieces_SourceDocumentID' AND object_id = OBJECT_ID(N'dbo.LeaseDocumentPieces'))
        CREATE INDEX IX_LeaseDocumentPieces_SourceDocumentID ON dbo.LeaseDocumentPieces (LeaseSourceDocumentID, SortOrder);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_LeaseGeneratedDocuments_LeaseID' AND object_id = OBJECT_ID(N'dbo.LeaseGeneratedDocuments'))
        CREATE INDEX IX_LeaseGeneratedDocuments_LeaseID ON dbo.LeaseGeneratedDocuments (LeaseID, GeneratedOn DESC);

    IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = N'IX_LeaseGeneratedDocumentPieces_GeneratedDocumentID' AND object_id = OBJECT_ID(N'dbo.LeaseGeneratedDocumentPieces'))
        CREATE INDEX IX_LeaseGeneratedDocumentPieces_GeneratedDocumentID ON dbo.LeaseGeneratedDocumentPieces (LeaseGeneratedDocumentID, SortOrder);

    /* Optional foreign keys. Added only if referenced tables exist. */
    IF OBJECT_ID(N'dbo.Leases', N'U') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_LeaseSourceDocuments_Leases')
    BEGIN
        ALTER TABLE dbo.LeaseSourceDocuments
        ADD CONSTRAINT FK_LeaseSourceDocuments_Leases
        FOREIGN KEY (LeaseID) REFERENCES dbo.Leases(LeaseID);
    END;

    IF OBJECT_ID(N'dbo.Leases', N'U') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_LeaseDocumentPieces_Leases')
    BEGIN
        ALTER TABLE dbo.LeaseDocumentPieces
        ADD CONSTRAINT FK_LeaseDocumentPieces_Leases
        FOREIGN KEY (LeaseID) REFERENCES dbo.Leases(LeaseID);
    END;

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_LeaseDocumentPieces_SourceDocuments')
    BEGIN
        ALTER TABLE dbo.LeaseDocumentPieces
        ADD CONSTRAINT FK_LeaseDocumentPieces_SourceDocuments
        FOREIGN KEY (LeaseSourceDocumentID) REFERENCES dbo.LeaseSourceDocuments(LeaseSourceDocumentID);
    END;

    IF OBJECT_ID(N'dbo.Leases', N'U') IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_LeaseGeneratedDocuments_Leases')
    BEGIN
        ALTER TABLE dbo.LeaseGeneratedDocuments
        ADD CONSTRAINT FK_LeaseGeneratedDocuments_Leases
        FOREIGN KEY (LeaseID) REFERENCES dbo.Leases(LeaseID);
    END;

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_LeaseGeneratedDocumentPieces_GeneratedDocuments')
    BEGIN
        ALTER TABLE dbo.LeaseGeneratedDocumentPieces
        ADD CONSTRAINT FK_LeaseGeneratedDocumentPieces_GeneratedDocuments
        FOREIGN KEY (LeaseGeneratedDocumentID) REFERENCES dbo.LeaseGeneratedDocuments(LeaseGeneratedDocumentID);
    END;

    IF NOT EXISTS (SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_LeaseGeneratedDocumentPieces_DocumentPieces')
    BEGIN
        ALTER TABLE dbo.LeaseGeneratedDocumentPieces
        ADD CONSTRAINT FK_LeaseGeneratedDocumentPieces_DocumentPieces
        FOREIGN KEY (LeaseDocumentPieceID) REFERENCES dbo.LeaseDocumentPieces(LeaseDocumentPieceID);
    END;

    /* SchemaChangeLog entry. Idempotent by ScriptName. */
    IF NOT EXISTS (
        SELECT 1
        FROM dbo.SchemaChangeLog
        WHERE ScriptName = @ScriptName
    )
    BEGIN
        INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
        VALUES (@ScriptName, SYSDATETIME(), @AppliedBy, @Notes);
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    DECLARE @ErrorMessage NVARCHAR(4000) = ERROR_MESSAGE();
    DECLARE @ErrorSeverity INT = ERROR_SEVERITY();
    DECLARE @ErrorState INT = ERROR_STATE();

    RAISERROR(@ErrorMessage, @ErrorSeverity, @ErrorState);
END CATCH;
