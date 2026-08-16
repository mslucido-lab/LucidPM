/*
Lease Templates Admin Library schema update
Purpose:
  - Move lease document management above tenant level
  - Support admin-level base lease templates, exhibits, addendums, and reusable PDF pieces
  - Store files on disk, not as SQL blobs
  - Log this change in dbo.SchemaChangeLog

Run against TenantCRM_Test first, then TenantCRM after validation.
*/

SET NOCOUNT ON;

DECLARE @ScriptName NVARCHAR(255) = N'lease_templates_admin_v3_settings_schema_with_changelog.sql';
DECLARE @Notes NVARCHAR(MAX) = N'Adds admin-level lease template metadata, editable storage path fields, reusable PDF pieces, tenant-neutral source documents, and global AppSettings for developer tool visibility for Lease Templates module.';

BEGIN TRY
    BEGIN TRANSACTION;

    IF OBJECT_ID('dbo.LeaseSourceDocuments', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.LeaseSourceDocuments (
            LeaseSourceDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
            LeaseID INT NULL,
            PropertyID INT NULL,
            TemplateName NVARCHAR(255) NULL,
            DocumentScope NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentScope DEFAULT ('AdminTemplate'),
            DocumentCategory NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentCategory DEFAULT ('Base Lease'),
            TemplateVersion NVARCHAR(50) NULL,
            StorageRoot NVARCHAR(1000) NULL,
            RelativePath NVARCHAR(1000) NULL,
            SourceFileType NVARCHAR(20) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_SourceFileType DEFAULT ('PDF'),
            IsTemplate BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsTemplate DEFAULT (1),
            IsActive BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsActive DEFAULT (1),
            OriginalFileName NVARCHAR(255) NOT NULL,
            StoredFilePath NVARCHAR(1000) NOT NULL,
            PageCount INT NULL,
            DocumentStatus NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_Status DEFAULT ('Uploaded'),
            UploadedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseSourceDocuments_UploadedOn DEFAULT (SYSDATETIME()),
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
            SortOrder INT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_SortOrder DEFAULT (0),
            IsReusable BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsReusable DEFAULT (1),
            IsActive BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsActive DEFAULT (1),
            CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseDocumentPieces_CreatedOn DEFAULT (SYSDATETIME()),
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
            GeneratedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseGeneratedDocuments_GeneratedOn DEFAULT (SYSDATETIME()),
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

    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'PropertyID') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD PropertyID INT NULL;
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'TemplateName') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD TemplateName NVARCHAR(255) NULL;
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'DocumentScope') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD DocumentScope NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentScope2 DEFAULT ('AdminTemplate');
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'DocumentCategory') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD DocumentCategory NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_DocumentCategory2 DEFAULT ('Base Lease');
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'TemplateVersion') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD TemplateVersion NVARCHAR(50) NULL;
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'StorageRoot') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD StorageRoot NVARCHAR(1000) NULL;
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'RelativePath') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD RelativePath NVARCHAR(1000) NULL;
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'SourceFileType') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD SourceFileType NVARCHAR(20) NOT NULL CONSTRAINT DF_LeaseSourceDocuments_SourceFileType2 DEFAULT ('PDF');
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'IsTemplate') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD IsTemplate BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsTemplate2 DEFAULT (1);
    IF COL_LENGTH('dbo.LeaseSourceDocuments', 'IsActive') IS NULL ALTER TABLE dbo.LeaseSourceDocuments ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseSourceDocuments_IsActive2 DEFAULT (1);

    IF COL_LENGTH('dbo.LeaseDocumentPieces', 'StorageRoot') IS NULL ALTER TABLE dbo.LeaseDocumentPieces ADD StorageRoot NVARCHAR(1000) NULL;
    IF COL_LENGTH('dbo.LeaseDocumentPieces', 'RelativePath') IS NULL ALTER TABLE dbo.LeaseDocumentPieces ADD RelativePath NVARCHAR(1000) NULL;
    IF COL_LENGTH('dbo.LeaseDocumentPieces', 'IsActive') IS NULL ALTER TABLE dbo.LeaseDocumentPieces ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseDocumentPieces_IsActive2 DEFAULT (1);

    -- Support admin-level templates before a tenant lease package exists.
    BEGIN TRY
        ALTER TABLE dbo.LeaseSourceDocuments ALTER COLUMN LeaseID INT NULL;
    END TRY
    BEGIN CATCH
    END CATCH;

    BEGIN TRY
        ALTER TABLE dbo.LeaseDocumentPieces ALTER COLUMN LeaseID INT NULL;
    END TRY
    BEGIN CATCH
    END CATCH;

    IF OBJECT_ID('dbo.AppSettings', 'U') IS NULL
    BEGIN
        CREATE TABLE dbo.AppSettings (
            SettingKey NVARCHAR(100) NOT NULL PRIMARY KEY,
            SettingValue NVARCHAR(1000) NULL,
            UpdatedOn DATETIME2 NOT NULL CONSTRAINT DF_AppSettings_UpdatedOn DEFAULT (SYSDATETIME())
        );
    END;

    IF NOT EXISTS (SELECT 1 FROM dbo.AppSettings WHERE SettingKey = 'EnableDeveloperTools')
    BEGIN
        INSERT INTO dbo.AppSettings (SettingKey, SettingValue, UpdatedOn)
        VALUES ('EnableDeveloperTools', '0', SYSDATETIME());
    END;

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
