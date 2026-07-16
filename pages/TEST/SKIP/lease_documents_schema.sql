/*
Lease Documents MVP schema
Stores PDF files on disk and document metadata in SQL Server.
No blobs.
*/

IF OBJECT_ID('dbo.LeaseSourceDocuments', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LeaseSourceDocuments (
        LeaseSourceDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        LeaseID INT NOT NULL,
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
        Notes NVARCHAR(MAX) NULL
    );
END;

IF OBJECT_ID('dbo.LeaseGeneratedDocuments', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LeaseGeneratedDocuments (
        LeaseGeneratedDocumentID INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        LeaseID INT NOT NULL,
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
