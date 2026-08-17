/*
Lease Package Builder v1 schema update
Purpose:
  - Validate/create required lease document tables for tenant-level lease package generation
  - Store generated tenant lease package metadata linked to LeaseID
  - Log this change in dbo.SchemaChangeLog

Run against TenantCRM_Test first, then TenantCRM after validation.
*/

SET NOCOUNT ON;

DECLARE @ScriptName NVARCHAR(255) = N'lease_package_builder_v1_schema_with_changelog.sql';
DECLARE @Notes NVARCHAR(MAX) = N'Adds/validates tenant-level Lease Package Builder tables used to merge selected reusable Admin Lease Template pieces into generated lease package PDFs linked to LeaseID.';

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID('dbo.LeaseSourceDocuments', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseSourceDocuments (
            LeaseSourceDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            LeaseID INT NULL,
            PropertyID INT NULL,
            TemplateName NVARCHAR(255) NULL,
            DocumentScope NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentScope_LPB DEFAULT ('AdminTemplate'),
            DocumentCategory NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentCategory_LPB DEFAULT ('Base Lease'),
            TemplateVersion NVARCHAR(50) NULL,
            StorageRoot NVARCHAR(1000) NULL,
            RelativePath NVARCHAR(1000) NULL,
            SourceFileType NVARCHAR(20) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_SourceFileType_LPB DEFAULT ('PDF'),
            IsTemplate BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsTemplate_LPB DEFAULT (1),
            IsActive BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsActive_LPB DEFAULT (1),
            OriginalFileName NVARCHAR(255) NOT NULL,
            StoredFilePath NVARCHAR(1000) NOT NULL,
            PageCount INT NULL,
            DocumentStatus NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_Status_LPB DEFAULT ('Uploaded'),
            UploadedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseSourceDocuments_UploadedOn_LPB DEFAULT (SYSDATETIME()),
            Notes NVARCHAR(MAX) NULL
        );
    END;

    IF OBJECT_ID('dbo.LeaseDocumentPieces', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseDocumentPieces (
            LeaseDocumentPieceID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            LeaseSourceDocumentID INT NOT NULL,
            LeaseID INT NULL,
            PieceType NVARCHAR(50) NOT NULL,
            PieceName NVARCHAR(255) NOT NULL,
            ExhibitCode NVARCHAR(50) NULL,
            StartPage INT NOT NULL,
            EndPage INT NOT NULL,
            StoredFilePath NVARCHAR(1000) NOT NULL,
            StorageRoot NVARCHAR(1000) NULL,
            RelativePath NVARCHAR(1000) NULL,
            SortOrder INT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_SortOrder_LPB DEFAULT (0),
            IsReusable BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsReusable_LPB DEFAULT (1),
            IsActive BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsActive_LPB DEFAULT (1),
            CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseDocumentPieces_CreatedOn_LPB DEFAULT (SYSDATETIME()),
            Notes NVARCHAR(MAX) NULL
        );
    END;

    IF OBJECT_ID('dbo.LeaseGeneratedDocuments', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseGeneratedDocuments (
            LeaseGeneratedDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            LeaseID INT NULL,
            GeneratedFileName NVARCHAR(255) NOT NULL,
            StoredFilePath NVARCHAR(1000) NOT NULL,
            GeneratedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseGeneratedDocuments_GeneratedOn_LPB DEFAULT (SYSDATETIME()),
            PackageNotes NVARCHAR(MAX) NULL
        );
    END;

    IF OBJECT_ID('dbo.LeaseGeneratedDocumentPieces', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseGeneratedDocumentPieces (
            LeaseGeneratedDocumentPieceID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            LeaseGeneratedDocumentID INT NOT NULL,
            LeaseDocumentPieceID INT NOT NULL,
            SortOrder INT NOT NULL
        );
    END;

    IF COL_LENGTH('dbo.LeaseGeneratedDocuments', 'LeaseID') IS NULL
        ALTER TABLE dbo.LeaseGeneratedDocuments ADD LeaseID INT NULL;

    IF COL_LENGTH('dbo.LeaseGeneratedDocuments', 'PackageNotes') IS NULL
        ALTER TABLE dbo.LeaseGeneratedDocuments ADD PackageNotes NVARCHAR(MAX) NULL;

    IF COL_LENGTH('dbo.LeaseDocumentPieces', 'IsReusable') IS NULL
        ALTER TABLE dbo.LeaseDocumentPieces ADD IsReusable BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsReusable_LPB2 DEFAULT (1);

    IF COL_LENGTH('dbo.LeaseDocumentPieces', 'IsActive') IS NULL
        ALTER TABLE dbo.LeaseDocumentPieces ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsActive_LPB2 DEFAULT (1);

    IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM dbo.SchemaChangeLog WHERE ScriptName = @ScriptName)
        BEGIN
            INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
            VALUES (@ScriptName, SYSDATETIME(), SUSER_SNAME(), @Notes);
        END;
    END;

    COMMIT TRANSACTION;
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
    THROW;
END CATCH;
