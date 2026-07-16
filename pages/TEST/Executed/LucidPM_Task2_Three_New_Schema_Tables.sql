/*
Lucido Property Manager - Task 2 SQL
Three New Schema Tables Required
Date: 2026-04-26

Purpose:
Adds the lease template architecture tables documented in the Project Context:
1. LeaseTemplates
2. LeaseTemplateSections
3. LeasePackageSections

Safe to run more than once.
Run against TenantCRM_Test first.
*/

/* Layer 2: Reusable template definition */
IF OBJECT_ID('dbo.LeaseTemplates', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LeaseTemplates (
        LeaseTemplateID  INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        TemplateName     NVARCHAR(255) NOT NULL,
        PropertyID       INT NULL,           -- NULL = all properties
        Description      NVARCHAR(MAX) NULL,
        IsActive         BIT NOT NULL CONSTRAINT DF_LeaseTemplates_IsActive DEFAULT (1),
        CreatedOn        DATETIME2 NOT NULL CONSTRAINT DF_LeaseTemplates_CreatedOn DEFAULT (SYSDATETIME()),
        UpdatedOn        DATETIME2 NULL
    );
END;

/* Layer 2: Ordered section slots within a template, roughly 25-30 per lease */
IF OBJECT_ID('dbo.LeaseTemplateSections', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LeaseTemplateSections (
        LeaseTemplateSectionID  INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        LeaseTemplateID         INT NOT NULL,   -- FK to LeaseTemplates
        SortOrder               INT NOT NULL CONSTRAINT DF_LeaseTemplateSections_SortOrder DEFAULT (0),
        SectionLabel            NVARCHAR(255) NOT NULL,  -- e.g. Section 7 - HVAC
        DefaultPieceID          INT NULL,       -- FK to LeaseDocumentPieces, standard clause
        IsOptional              BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsOptional DEFAULT (0),
        IsRequired              BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsRequired DEFAULT (0),
        SectionType             NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseTemplateSections_SectionType DEFAULT ('dynamic')
        -- SectionType values: static / dynamic / generated / optional
    );
END;

/* Layer 3: Tenant-specific package sections, replaces flat piece selection */
IF OBJECT_ID('dbo.LeasePackageSections', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LeasePackageSections (
        LeasePackageSectionID    INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        LeaseGeneratedDocumentID INT NOT NULL,  -- FK to LeaseGeneratedDocuments
        LeaseTemplateSectionID   INT NOT NULL,  -- FK to LeaseTemplateSections
        SortOrder                INT NOT NULL CONSTRAINT DF_LeasePackageSections_SortOrder DEFAULT (0),
        IsIncluded               BIT NOT NULL CONSTRAINT DF_LeasePackageSections_IsIncluded DEFAULT (1),  -- toggle optional sections
        PieceID                  INT NULL,      -- FK to LeaseDocumentPieces, selected piece used
        Content                  NVARCHAR(MAX) NULL,  -- editable merged text
        IsDirty                  BIT NOT NULL CONSTRAINT DF_LeasePackageSections_IsDirty DEFAULT (0),  -- edited from default
        ContentSnapshot          NVARCHAR(MAX) NULL   -- frozen at generation, immutable legal record
    );
END;

/* Self-healing ALTERs for partially-created tables */
IF COL_LENGTH('dbo.LeaseTemplates', 'TemplateName') IS NULL ALTER TABLE dbo.LeaseTemplates ADD TemplateName NVARCHAR(255) NULL;
IF COL_LENGTH('dbo.LeaseTemplates', 'PropertyID') IS NULL ALTER TABLE dbo.LeaseTemplates ADD PropertyID INT NULL;
IF COL_LENGTH('dbo.LeaseTemplates', 'Description') IS NULL ALTER TABLE dbo.LeaseTemplates ADD Description NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.LeaseTemplates', 'IsActive') IS NULL ALTER TABLE dbo.LeaseTemplates ADD IsActive BIT NOT NULL CONSTRAINT DF_LeaseTemplates_IsActive2 DEFAULT (1);
IF COL_LENGTH('dbo.LeaseTemplates', 'CreatedOn') IS NULL ALTER TABLE dbo.LeaseTemplates ADD CreatedOn DATETIME2 NOT NULL CONSTRAINT DF_LeaseTemplates_CreatedOn2 DEFAULT (SYSDATETIME());
IF COL_LENGTH('dbo.LeaseTemplates', 'UpdatedOn') IS NULL ALTER TABLE dbo.LeaseTemplates ADD UpdatedOn DATETIME2 NULL;

IF COL_LENGTH('dbo.LeaseTemplateSections', 'LeaseTemplateID') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD LeaseTemplateID INT NULL;
IF COL_LENGTH('dbo.LeaseTemplateSections', 'SortOrder') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD SortOrder INT NOT NULL CONSTRAINT DF_LeaseTemplateSections_SortOrder2 DEFAULT (0);
IF COL_LENGTH('dbo.LeaseTemplateSections', 'SectionLabel') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD SectionLabel NVARCHAR(255) NULL;
IF COL_LENGTH('dbo.LeaseTemplateSections', 'DefaultPieceID') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD DefaultPieceID INT NULL;
IF COL_LENGTH('dbo.LeaseTemplateSections', 'IsOptional') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD IsOptional BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsOptional2 DEFAULT (0);
IF COL_LENGTH('dbo.LeaseTemplateSections', 'IsRequired') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD IsRequired BIT NOT NULL CONSTRAINT DF_LeaseTemplateSections_IsRequired2 DEFAULT (0);
IF COL_LENGTH('dbo.LeaseTemplateSections', 'SectionType') IS NULL ALTER TABLE dbo.LeaseTemplateSections ADD SectionType NVARCHAR(50) NOT NULL CONSTRAINT DF_LeaseTemplateSections_SectionType2 DEFAULT ('dynamic');

IF COL_LENGTH('dbo.LeasePackageSections', 'LeaseGeneratedDocumentID') IS NULL ALTER TABLE dbo.LeasePackageSections ADD LeaseGeneratedDocumentID INT NULL;
IF COL_LENGTH('dbo.LeasePackageSections', 'LeaseTemplateSectionID') IS NULL ALTER TABLE dbo.LeasePackageSections ADD LeaseTemplateSectionID INT NULL;
IF COL_LENGTH('dbo.LeasePackageSections', 'SortOrder') IS NULL ALTER TABLE dbo.LeasePackageSections ADD SortOrder INT NOT NULL CONSTRAINT DF_LeasePackageSections_SortOrder2 DEFAULT (0);
IF COL_LENGTH('dbo.LeasePackageSections', 'IsIncluded') IS NULL ALTER TABLE dbo.LeasePackageSections ADD IsIncluded BIT NOT NULL CONSTRAINT DF_LeasePackageSections_IsIncluded2 DEFAULT (1);
IF COL_LENGTH('dbo.LeasePackageSections', 'PieceID') IS NULL ALTER TABLE dbo.LeasePackageSections ADD PieceID INT NULL;
IF COL_LENGTH('dbo.LeasePackageSections', 'Content') IS NULL ALTER TABLE dbo.LeasePackageSections ADD Content NVARCHAR(MAX) NULL;
IF COL_LENGTH('dbo.LeasePackageSections', 'IsDirty') IS NULL ALTER TABLE dbo.LeasePackageSections ADD IsDirty BIT NOT NULL CONSTRAINT DF_LeasePackageSections_IsDirty2 DEFAULT (0);
IF COL_LENGTH('dbo.LeasePackageSections', 'ContentSnapshot') IS NULL ALTER TABLE dbo.LeasePackageSections ADD ContentSnapshot NVARCHAR(MAX) NULL;

/* Helpful indexes */
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LeaseTemplates_PropertyID_IsActive' AND object_id = OBJECT_ID('dbo.LeaseTemplates'))
BEGIN
    CREATE INDEX IX_LeaseTemplates_PropertyID_IsActive ON dbo.LeaseTemplates(PropertyID, IsActive, TemplateName);
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LeaseTemplateSections_Template_Sort' AND object_id = OBJECT_ID('dbo.LeaseTemplateSections'))
BEGIN
    CREATE INDEX IX_LeaseTemplateSections_Template_Sort ON dbo.LeaseTemplateSections(LeaseTemplateID, SortOrder, LeaseTemplateSectionID);
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LeasePackageSections_Generated_Sort' AND object_id = OBJECT_ID('dbo.LeasePackageSections'))
BEGIN
    CREATE INDEX IX_LeasePackageSections_Generated_Sort ON dbo.LeasePackageSections(LeaseGeneratedDocumentID, SortOrder, LeasePackageSectionID);
END;

/* Optional SchemaChangeLog entry */
IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM dbo.SchemaChangeLog
        WHERE ScriptName = '20260426_Task2_Lease_Template_Section_Tables'
    )
    BEGIN
        INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
        VALUES (
            '20260426_Task2_Lease_Template_Section_Tables',
            SYSDATETIME(),
            SYSTEM_USER,
            'Added LeaseTemplates, LeaseTemplateSections, and LeasePackageSections for template-driven lease assembly.'
        );
    END;
END;
