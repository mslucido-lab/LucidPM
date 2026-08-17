-- Generated baseline schema snapshot.
-- Source database: TenantCRM_Test
-- Generated: 2026-08-16T23:44:59
-- Regenerate with: python db/generate_baseline_schema.py
-- This is a snapshot of the live schema at generation time, NOT a replay
-- of history -- see db/history/CHANGELOG.md for that.

-- ============================================================
-- Tables
-- ============================================================

CREATE TABLE dbo.[Actions_legacy] (
    [ActionID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NULL,
    [PropertyID] INT NULL,
    [LeaseID] INT NULL,
    [Title] NVARCHAR(200) NOT NULL,
    [Description] NVARCHAR(MAX) NULL,
    [Status] NVARCHAR(50) NOT NULL DEFAULT ('Open'),
    [Priority] NVARCHAR(20) NULL,
    [DueDate] DATE NULL,
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    [CompletedDate] DATETIME NULL,
    [AssignedTo] NVARCHAR(100) NULL,
    [SourceCommunicationID] INT NULL,
    CONSTRAINT [PK_Actions_legacy] PRIMARY KEY CLUSTERED ([ActionID])
);

CREATE TABLE dbo.[AIConfig] (
    [AIConfigID] INT IDENTITY(1,1) NOT NULL,
    [APIKeyEncrypted] NVARCHAR(500) NULL,
    [ModelName] NVARCHAR(100) NOT NULL DEFAULT ('claude-sonnet-4-20250514'),
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    [CreatedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    [UpdatedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    CONSTRAINT [PK_AIConfig] PRIMARY KEY CLUSTERED ([AIConfigID])
);

CREATE TABLE dbo.[AppSettings] (
    [SettingKey] NVARCHAR(100) NOT NULL,
    [SettingValue] NVARCHAR(1000) NULL,
    [UpdatedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    CONSTRAINT [PK_AppSettings] PRIMARY KEY CLUSTERED ([SettingKey])
);

CREATE TABLE dbo.[Communications] (
    [CommunicationID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NOT NULL,
    [ContactID] INT NULL,
    [PropertyID] INT NULL,
    [CommDate] DATETIME NOT NULL,
    [Method] NVARCHAR(100) NULL,
    [Subject] NVARCHAR(255) NULL,
    [TemplateName] NVARCHAR(100) NULL,
    [Outcome] NVARCHAR(100) NULL,
    [NextActionDate] DATETIME NULL,
    [Notes] NVARCHAR(MAX) NULL,
    CONSTRAINT [PK_Communications] PRIMARY KEY CLUSTERED ([CommunicationID])
);

CREATE TABLE dbo.[Contacts] (
    [ContactID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NOT NULL,
    [Title] NVARCHAR(50) NULL,
    [FirstName] NVARCHAR(100) NULL,
    [LastName] NVARCHAR(100) NULL,
    [WorkPhone] NVARCHAR(50) NULL,
    [HomePhone] NVARCHAR(50) NULL,
    [Email1] NVARCHAR(255) NULL,
    [Email2] NVARCHAR(255) NULL,
    [ContactRole] NVARCHAR(30) NULL,
    [IsPrimary] BIT NOT NULL,
    [Salutation] NVARCHAR(50) NULL,
    [IsEmergencyContact] BIT NOT NULL DEFAULT ((0)),
    CONSTRAINT [PK_Contacts] PRIMARY KEY CLUSTERED ([ContactID])
);

CREATE TABLE dbo.[ContactSensitiveInfo] (
    [ContactSensitiveInfoID] INT IDENTITY(1,1) NOT NULL,
    [ContactID] INT NOT NULL,
    [SSN_Encrypted] NVARCHAR(MAX) NULL,
    [DL_Encrypted] NVARCHAR(MAX) NULL,
    [DOB] DATE NULL,
    [Last4SSN] NVARCHAR(4) NULL,
    [DL_Last4] NVARCHAR(4) NULL,
    [CreatedOn] DATETIME NOT NULL DEFAULT (getdate()),
    [UpdatedOn] DATETIME NULL,
    CONSTRAINT [PK_ContactSensitiveInfo] PRIMARY KEY CLUSTERED ([ContactSensitiveInfoID])
);

CREATE TABLE dbo.[DocumentTypes] (
    [DocumentTypeID] INT NOT NULL,
    [DocumentTypeName] NVARCHAR(50) NOT NULL,
    [HasExpiration] BIT NOT NULL,
    [DefaultRenewalMonths] INT NULL,
    [IsRequired] BIT NOT NULL,
    CONSTRAINT [PK_DocumentTypes] PRIMARY KEY CLUSTERED ([DocumentTypeID])
);

CREATE TABLE dbo.[EmailConfig] (
    [EmailConfigID] INT IDENTITY(1,1) NOT NULL,
    [DisplayName] NVARCHAR(100) NULL,
    [EmailAddress] NVARCHAR(200) NULL,
    [IMAPServer] NVARCHAR(200) NULL,
    [IMAPPort] INT NOT NULL DEFAULT ((993)),
    [SMTPServer] NVARCHAR(200) NULL,
    [SMTPPort] INT NOT NULL DEFAULT ((587)),
    [Username] NVARCHAR(200) NULL,
    [PasswordEncrypted] NVARCHAR(500) NULL,
    [PollIntervalMin] INT NOT NULL DEFAULT ((10)),
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    [CreatedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    [UpdatedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    CONSTRAINT [PK_EmailConfig] PRIMARY KEY CLUSTERED ([EmailConfigID])
);

CREATE TABLE dbo.[GeneratedLeaseDocuments] (
    [GeneratedLeaseDocumentID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NOT NULL,
    [LeaseID] INT NOT NULL,
    [LeaseDocumentPackageID] INT NULL,
    [GeneratedOn] DATETIME2(0) NOT NULL DEFAULT (sysutcdatetime()),
    [OutputPath] NVARCHAR(1000) NULL,
    [MergeContextJson] NVARCHAR(MAX) NULL,
    [RenderedText] NVARCHAR(MAX) NULL,
    [CreatedBy] NVARCHAR(100) NULL,
    CONSTRAINT [PK_GeneratedLeaseDocuments] PRIMARY KEY CLUSTERED ([GeneratedLeaseDocumentID])
);

CREATE TABLE dbo.[LeaseDocumentSections] (
    [LeaseDocumentSectionID] INT IDENTITY(1,1) NOT NULL,
    [LeaseSourceDocumentID] INT NULL,
    [LeaseID] INT NULL,
    [SectionType] NVARCHAR(50) NOT NULL,
    [SectionName] NVARCHAR(255) NOT NULL,
    [ExhibitCode] NVARCHAR(50) NULL,
    [StartPage] INT NULL,
    [EndPage] INT NULL,
    [StoredFilePath] NVARCHAR(1000) NULL,
    [SortOrder] INT NOT NULL DEFAULT ((0)),
    [IsReusable] BIT NOT NULL DEFAULT ((0)),
    [CreatedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    [Notes] NVARCHAR(MAX) NULL,
    [StorageRoot] NVARCHAR(1000) NULL,
    [RelativePath] NVARCHAR(1000) NULL,
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    [Content] NVARCHAR(MAX) NULL,
    [ClauseTag] NVARCHAR(100) NULL,
    [ArticleNumber] NVARCHAR(20) NULL,
    [DisplayLabel] NVARCHAR(255) NULL,
    [UpdatedOn] DATETIME2(7) NULL,
    CONSTRAINT [PK_LeaseDocumentSections] PRIMARY KEY CLUSTERED ([LeaseDocumentSectionID])
);

CREATE TABLE dbo.[LeaseGeneratedDocuments] (
    [LeaseGeneratedDocumentID] INT IDENTITY(1,1) NOT NULL,
    [LeaseID] INT NOT NULL,
    [GeneratedFileName] NVARCHAR(255) NOT NULL,
    [StoredFilePath] NVARCHAR(1000) NOT NULL,
    [GeneratedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    [PackageNotes] NVARCHAR(MAX) NULL,
    [TenantID] INT NULL,
    CONSTRAINT [PK_LeaseGeneratedDocuments] PRIMARY KEY CLUSTERED ([LeaseGeneratedDocumentID])
);

CREATE TABLE dbo.[LeaseGeneratedDocumentSections] (
    [LeaseGeneratedDocumentSectionID] INT IDENTITY(1,1) NOT NULL,
    [LeaseGeneratedDocumentID] INT NOT NULL,
    [LeaseDocumentPieceID] INT NOT NULL,
    [SortOrder] INT NOT NULL,
    CONSTRAINT [PK_LeaseGeneratedDocumentSections] PRIMARY KEY CLUSTERED ([LeaseGeneratedDocumentSectionID])
);

CREATE TABLE dbo.[LeasePackageSections] (
    [LeasePackageSectionID] INT IDENTITY(1,1) NOT NULL,
    [LeaseGeneratedDocumentID] INT NOT NULL,
    [LeaseTemplateSectionID] INT NOT NULL,
    [SortOrder] INT NOT NULL DEFAULT ((0)),
    [IsIncluded] BIT NOT NULL DEFAULT ((1)),
    [SectionID] INT NULL,
    [Content] NVARCHAR(MAX) NULL,
    [IsDirty] BIT NOT NULL DEFAULT ((0)),
    [ContentSnapshot] NVARCHAR(MAX) NULL,
    CONSTRAINT [PK_LeasePackageSections] PRIMARY KEY CLUSTERED ([LeasePackageSectionID])
);

CREATE TABLE dbo.[LeaseRentIncreaseTypes] (
    [IncreaseTypeID] INT IDENTITY(1,1) NOT NULL,
    [IncreaseTypeName] NVARCHAR(50) NOT NULL,
    [Description] NVARCHAR(500) NULL,
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    [DisplayOrder] INT NOT NULL DEFAULT ((0)),
    [LeaseRentIncreaseTypeID] INT NULL,
    [SortOrder] INT NOT NULL DEFAULT ((0)),
    CONSTRAINT [PK_LeaseRentIncreaseTypes] PRIMARY KEY CLUSTERED ([IncreaseTypeID])
);

CREATE TABLE dbo.[LeaseRentIncreaseTypes_Legacy_20260315_123957] (
    [LeaseRentIncreaseTypeID] INT IDENTITY(1,1) NOT NULL,
    [IncreaseTypeName] NVARCHAR(50) NOT NULL,
    [SortOrder] INT NOT NULL DEFAULT ((0)),
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_LeaseRentIncreaseTypes_Legacy_20260315_123957] PRIMARY KEY CLUSTERED ([LeaseRentIncreaseTypeID])
);

CREATE TABLE dbo.[LeaseRentSchedule] (
    [LeaseRentScheduleID] INT IDENTITY(1,1) NOT NULL,
    [LeaseID] INT NOT NULL,
    [EffectiveStartDate] DATETIME NOT NULL,
    [EffectiveEndDate] DATETIME NULL,
    [RentAmount] MONEY NOT NULL,
    [IncreaseType] NVARCHAR(50) NULL,
    [Notes] NVARCHAR(MAX) NULL,
    [IncreaseTypeID] INT NOT NULL,
    CONSTRAINT [PK_LeaseRentSchedule] PRIMARY KEY CLUSTERED ([LeaseRentScheduleID])
);

CREATE TABLE dbo.[Leases] (
    [LeaseID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NOT NULL,
    [PropertyID] INT NOT NULL,
    [LeaseType] NVARCHAR(50) NULL,
    [LeaseStart] DATETIME NULL,
    [LeaseEnd] DATETIME NULL,
    [RentAmount] MONEY NULL,
    [DepositAmount] MONEY NULL,
    [RentDueDay] INT NULL,
    [NextDueDate] DATETIME NULL,
    [LeaseTypeID] INT NULL,
    [LeaseTermTypeID] INT NULL,
    [ShowAnniversaries] BIT NOT NULL,
    [SuiteID] INT NULL,
    [LeaseStatus] NVARCHAR(50) NULL DEFAULT ('Active'),
    [LeaseTerminationDate] DATETIME NULL,
    [ParentLeaseID] INT NULL,
    [ExecutionDate] DATETIME NULL,
    CONSTRAINT [PK_Leases] PRIMARY KEY CLUSTERED ([LeaseID])
);

CREATE TABLE dbo.[LeaseSourceDocuments] (
    [LeaseSourceDocumentID] INT IDENTITY(1,1) NOT NULL,
    [LeaseID] INT NULL,
    [OriginalFileName] NVARCHAR(255) NOT NULL,
    [StoredFilePath] NVARCHAR(1000) NOT NULL,
    [PageCount] INT NULL,
    [DocumentStatus] NVARCHAR(50) NOT NULL DEFAULT (N'Uploaded'),
    [UploadedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    [Notes] NVARCHAR(MAX) NULL,
    [PropertyID] INT NULL,
    [TemplateName] NVARCHAR(255) NULL,
    [DocumentScope] NVARCHAR(50) NOT NULL DEFAULT ('AdminTemplate'),
    [DocumentCategory] NVARCHAR(50) NOT NULL DEFAULT ('Base Lease'),
    [TemplateVersion] NVARCHAR(50) NULL,
    [StorageRoot] NVARCHAR(1000) NULL,
    [RelativePath] NVARCHAR(1000) NULL,
    [SourceFileType] NVARCHAR(20) NOT NULL DEFAULT ('PDF'),
    [IsTemplate] BIT NOT NULL DEFAULT ((1)),
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_LeaseSourceDocuments] PRIMARY KEY CLUSTERED ([LeaseSourceDocumentID])
);

CREATE TABLE dbo.[LeaseTemplates] (
    [LeaseTemplateID] INT IDENTITY(1,1) NOT NULL,
    [TemplateName] NVARCHAR(255) NOT NULL,
    [PropertyID] INT NULL,
    [Description] NVARCHAR(MAX) NULL,
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    [CreatedOn] DATETIME2(7) NOT NULL DEFAULT (sysdatetime()),
    [UpdatedOn] DATETIME2(7) NULL,
    [TemplateVersion] INT NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_LeaseTemplates] PRIMARY KEY CLUSTERED ([LeaseTemplateID])
);

CREATE TABLE dbo.[LeaseTemplateSections] (
    [LeaseTemplateSectionID] INT IDENTITY(1,1) NOT NULL,
    [LeaseTemplateID] INT NOT NULL,
    [SortOrder] INT NOT NULL DEFAULT ((0)),
    [SectionLabel] NVARCHAR(255) NOT NULL,
    [DefaultSectionID] INT NULL,
    [IsOptional] BIT NOT NULL DEFAULT ((0)),
    [IsRequired] BIT NOT NULL DEFAULT ((0)),
    [SectionType] NVARCHAR(50) NOT NULL DEFAULT ('dynamic'),
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_LeaseTemplateSections] PRIMARY KEY CLUSTERED ([LeaseTemplateSectionID])
);

CREATE TABLE dbo.[LeaseTermTypes] (
    [LeaseTermTypeID] INT NOT NULL,
    [LeaseTermTypeName] NVARCHAR(50) NOT NULL,
    CONSTRAINT [PK_LeaseTermTypes] PRIMARY KEY CLUSTERED ([LeaseTermTypeID])
);

CREATE TABLE dbo.[LeaseTypes] (
    [LeaseTypeID] INT NOT NULL,
    [LeaseTypeName] NVARCHAR(50) NOT NULL,
    CONSTRAINT [PK_LeaseTypes] PRIMARY KEY CLUSTERED ([LeaseTypeID])
);

CREATE TABLE dbo.[MailMerge Query] (
    [Salutation] NVARCHAR(50) NULL,
    [FirstName] NVARCHAR(100) NULL,
    [LastName] NVARCHAR(100) NULL,
    [Company Name] NVARCHAR(255) NULL,
    [Address1] NVARCHAR(255) NULL,
    [Address2] NVARCHAR(255) NULL,
    [City] NVARCHAR(100) NULL,
    [state] NVARCHAR(50) NULL,
    [Zip] NVARCHAR(20) NULL
);

CREATE TABLE dbo.[Properties] (
    [PropertyID] INT IDENTITY(1,1) NOT NULL,
    [PropertyName] NVARCHAR(100) NOT NULL,
    [PropertyAddress1] NVARCHAR(200) NULL,
    [PropertyAddress2] NVARCHAR(200) NULL,
    [PropertyCity] NVARCHAR(100) NULL,
    [PropertyState] NVARCHAR(25) NULL,
    [PropertyZip] NVARCHAR(20) NULL,
    [TaxAccountNumber] NVARCHAR(100) NULL,
    [LandlordEntityName] NVARCHAR(255) NULL,
    [PropertyLegalDescription] NVARCHAR(MAX) NULL,
    [PropertyCounty] NVARCHAR(100) NULL,
    [PropertyUseDefault] NVARCHAR(255) NULL,
    [LeaseNoticeAddress1] NVARCHAR(255) NULL,
    [LeaseNoticeAddress2] NVARCHAR(255) NULL,
    [LeaseNoticeCity] NVARCHAR(100) NULL,
    [LeaseNoticeState] NVARCHAR(50) NULL,
    [LeaseNoticeZip] NVARCHAR(20) NULL,
    CONSTRAINT [PK_Properties] PRIMARY KEY CLUSTERED ([PropertyID])
);

CREATE TABLE dbo.[PropertyFinancials] (
    [PropertyFinancialID] INT IDENTITY(1,1) NOT NULL,
    [PropertyID] INT NOT NULL,
    [FiscalYear] INT NOT NULL,
    [TotalRevenue] DECIMAL(18,2) NOT NULL DEFAULT ((0)),
    [TotalOperatingExpenses] DECIMAL(18,2) NOT NULL DEFAULT ((0)),
    [Notes] NVARCHAR(MAX) NULL,
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    [UpdatedDate] DATETIME NULL,
    CONSTRAINT [PK_PropertyFinancials] PRIMARY KEY CLUSTERED ([PropertyFinancialID])
);

CREATE TABLE dbo.[PropertySuites] (
    [SuiteID] INT IDENTITY(1,1) NOT NULL,
    [PropertyID] INT NOT NULL,
    [SuiteLabel] NVARCHAR(100) NOT NULL,
    [SuiteSquareFeet] DECIMAL(18,2) NULL,
    [SortOrder] INT NOT NULL DEFAULT ((0)),
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    [Notes] NVARCHAR(MAX) NULL,
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    [UpdatedDate] DATETIME NULL,
    [SquareFeet] DECIMAL(18,2) NULL,
    [SuiteUseType] NVARCHAR(50) NOT NULL DEFAULT ('Standard'),
    [UnderwritingRent] DECIMAL(18,2) NULL,
    [SuiteLegalDescription] NVARCHAR(MAX) NULL,
    [SuitePremisesDescription] NVARCHAR(MAX) NULL,
    [SuiteAddressOverride] NVARCHAR(500) NULL,
    CONSTRAINT [PK_PropertySuites] PRIMARY KEY CLUSTERED ([SuiteID])
);

CREATE TABLE dbo.[Prospects] (
    [ProspectID] INT IDENTITY(1,1) NOT NULL,
    [ProspectName] NVARCHAR(200) NOT NULL,
    [PropertyID] INT NULL,
    [Phone] NVARCHAR(50) NULL,
    [Email] NVARCHAR(255) NULL,
    [DesiredUnitType] NVARCHAR(100) NULL,
    [DesiredSize] NVARCHAR(100) NULL,
    [DesiredMoveInDate] DATE NULL,
    [BudgetRange] NVARCHAR(100) NULL,
    [Source] NVARCHAR(50) NULL,
    [ProspectStatus] NVARCHAR(50) NOT NULL DEFAULT ('Waiting'),
    [LastContactDate] DATE NULL,
    [Notes] NVARCHAR(MAX) NULL,
    [DateCreated] DATETIME NOT NULL DEFAULT (getdate()),
    [DateModified] DATETIME NULL,
    [ConvertedTenantID] INT NULL,
    CONSTRAINT [PK_Prospects] PRIMARY KEY CLUSTERED ([ProspectID])
);

CREATE TABLE dbo.[SchemaChangeLog] (
    [SchemaChangeLogID] INT IDENTITY(1,1) NOT NULL,
    [ScriptName] NVARCHAR(255) NOT NULL,
    [AppliedOn] DATETIME2(0) NOT NULL DEFAULT (sysdatetime()),
    [AppliedBy] NVARCHAR(128) NOT NULL DEFAULT (suser_sname()),
    [Notes] NVARCHAR(1000) NULL,
    CONSTRAINT [PK_SchemaChangeLog] PRIMARY KEY CLUSTERED ([SchemaChangeLogID])
);

CREATE TABLE dbo.[sysdiagrams] (
    [name] NVARCHAR(128) NOT NULL,
    [principal_id] INT NOT NULL,
    [diagram_id] INT IDENTITY(1,1) NOT NULL,
    [version] INT NULL,
    [definition] VARBINARY(MAX) NULL,
    CONSTRAINT [PK_sysdiagrams] PRIMARY KEY CLUSTERED ([diagram_id])
);

CREATE TABLE dbo.[TenantAddresses] (
    [TenantAddressID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NOT NULL,
    [AddressLabel] NVARCHAR(50) NULL,
    [AddressLine1] NVARCHAR(255) NULL,
    [AddressLine2] NVARCHAR(255) NULL,
    [City] NVARCHAR(100) NULL,
    [State] NVARCHAR(50) NULL,
    [ZipCode] NVARCHAR(20) NULL,
    [CountryOrRegion] NVARCHAR(100) NULL,
    [IsPrimary] BIT NOT NULL,
    [Notes] NVARCHAR(MAX) NULL,
    CONSTRAINT [PK_TenantAddresses] PRIMARY KEY CLUSTERED ([TenantAddressID])
);

CREATE TABLE dbo.[TenantDocuments] (
    [TenantDocumentID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NOT NULL,
    [PropertyID] INT NULL,
    [DocumentTypeID] INT NULL,
    [DocumentName] NVARCHAR(255) NULL,
    [FilePath] NVARCHAR(500) NULL,
    [IssueDate] DATETIME NULL,
    [ExpirationDate] DATETIME NULL,
    [Notes] NVARCHAR(MAX) NULL,
    CONSTRAINT [PK_TenantDocuments] PRIMARY KEY CLUSTERED ([TenantDocumentID])
);

CREATE TABLE dbo.[TenantReferences] (
    [ReferenceID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NOT NULL,
    [ReferenceName] NVARCHAR(255) NULL,
    [ReferencePhone] NVARCHAR(50) NULL,
    [ReferenceEmail] NVARCHAR(255) NULL,
    [ReferenceAddress] NVARCHAR(500) NULL,
    [RelationshipYears] NVARCHAR(50) NULL,
    [Relationship] NVARCHAR(255) NULL,
    [Notes] NVARCHAR(MAX) NULL,
    [DateContacted] DATE NULL,
    [Outcome] NVARCHAR(50) NULL,
    [ImportedFromTally] BIT NOT NULL DEFAULT ((0)),
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    CONSTRAINT [PK_TenantReferences] PRIMARY KEY CLUSTERED ([ReferenceID])
);

CREATE TABLE dbo.[Tenants] (
    [TenantID] INT IDENTITY(1,1) NOT NULL,
    [TenantName] NVARCHAR(255) NOT NULL,
    [Notes] NVARCHAR(MAX) NULL,
    [TenantTypeID] INT NULL,
    [TenantStatusID] INT NULL,
    [PropertyID] INT NOT NULL,
    [Suite] NVARCHAR(50) NULL,
    [ProspectID] INT NULL,
    [SuiteID] INT NULL,
    CONSTRAINT [PK_Tenants] PRIMARY KEY CLUSTERED ([TenantID])
);

CREATE TABLE dbo.[TenantScreeningFactors] (
    [FactorID] INT IDENTITY(1,1) NOT NULL,
    [ScreeningID] INT NOT NULL,
    [FactorCode] NVARCHAR(50) NOT NULL,
    [PointsEarned] INT NOT NULL,
    [PointsMax] INT NOT NULL,
    [HardFlag] BIT NOT NULL DEFAULT ((0)),
    [Notes] NVARCHAR(500) NULL,
    CONSTRAINT [PK_TenantScreeningFactors] PRIMARY KEY CLUSTERED ([FactorID])
);

CREATE TABLE dbo.[TenantScreenings] (
    [TenantScreeningID] INT IDENTITY(1,1) NOT NULL,
    [TenantID] INT NOT NULL,
    [OrderedDate] DATE NOT NULL,
    [CompletedDate] DATE NULL,
    [ReportFileNumber] NVARCHAR(50) NULL,
    [OverallResult] NVARCHAR(20) NULL,
    [CreditScore] INT NULL,
    [Evictions] INT NULL,
    [Bankruptcies] INT NULL,
    [Collections] INT NULL,
    [ChargeOffs] INT NULL,
    [DelinquentAccounts] INT NULL,
    [IncomeToRent] DECIMAL(5,2) NULL,
    [IncomeToDebt] DECIMAL(5,2) NULL,
    [IncomeToDebtInclRent] DECIMAL(5,2) NULL,
    [CriminalResult] NVARCHAR(50) NULL,
    [EvictionResult] NVARCHAR(50) NULL,
    [CreditSourceType] NVARCHAR(50) NULL,
    [CreditSourceNotes] NVARCHAR(500) NULL,
    [RiskTier] NVARCHAR(20) NULL,
    [DepositRecommended] MONEY NULL,
    [Notes] NVARCHAR(MAX) NULL,
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    [CalculatedScore] INT NULL,
    [SuggestedTier] NVARCHAR(20) NULL,
    [SuggestedDecision] NVARCHAR(50) NULL,
    [SuggestedDepositPremium] MONEY NULL,
    CONSTRAINT [PK_TenantScreenings] PRIMARY KEY CLUSTERED ([TenantScreeningID])
);

CREATE TABLE dbo.[TenantStatuses] (
    [TenantStatusID] INT NOT NULL,
    [TenantStatusName] NVARCHAR(50) NOT NULL,
    CONSTRAINT [PK_TenantStatuses] PRIMARY KEY CLUSTERED ([TenantStatusID])
);

CREATE TABLE dbo.[TenantTypes] (
    [TenantTypeID] INT NOT NULL,
    [TenantTypeName] NVARCHAR(50) NOT NULL,
    CONSTRAINT [PK_TenantTypes] PRIMARY KEY CLUSTERED ([TenantTypeID])
);

CREATE TABLE dbo.[Vendors] (
    [VendorID] INT IDENTITY(1,1) NOT NULL,
    [VendorName] NVARCHAR(200) NOT NULL,
    [VendorCategoryID] INT NULL,
    [Phone] NVARCHAR(50) NULL,
    [Email] NVARCHAR(255) NULL,
    [Notes] NVARCHAR(MAX) NULL,
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    [UpdatedDate] DATETIME NULL,
    CONSTRAINT [PK_Vendors] PRIMARY KEY CLUSTERED ([VendorID])
);

CREATE TABLE dbo.[WorkItemActions] (
    [WorkItemActionID] INT IDENTITY(1,1) NOT NULL,
    [WorkItemID] INT NOT NULL,
    [ActionTitle] NVARCHAR(200) NOT NULL,
    [ActionStatus] NVARCHAR(50) NOT NULL DEFAULT ('Open'),
    [DueDate] DATE NULL,
    [CompletedDate] DATETIME NULL,
    [AssignedTo] NVARCHAR(100) NULL,
    [Notes] NVARCHAR(MAX) NULL,
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    [UpdatedDate] DATETIME NULL,
    [WorkItemBidID] INT NULL,
    [VendorID] INT NULL,
    CONSTRAINT [PK_WorkItemActions] PRIMARY KEY CLUSTERED ([WorkItemActionID])
);

CREATE TABLE dbo.[WorkItemBids] (
    [WorkItemBidID] INT IDENTITY(1,1) NOT NULL,
    [WorkItemID] INT NOT NULL,
    [VendorID] INT NOT NULL,
    [BidDate] DATE NULL,
    [BidAmount] DECIMAL(18,2) NULL,
    [BidStatus] NVARCHAR(50) NOT NULL DEFAULT ('Requested'),
    [ScopeSummary] NVARCHAR(MAX) NULL,
    [Notes] NVARCHAR(MAX) NULL,
    [IsSelected] BIT NOT NULL DEFAULT ((0)),
    [SelectedDate] DATETIME NULL,
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    [UpdatedDate] DATETIME NULL,
    CONSTRAINT [PK_WorkItemBids] PRIMARY KEY CLUSTERED ([WorkItemBidID])
);

CREATE TABLE dbo.[WorkItemCategories] (
    [WorkItemCategoryID] INT IDENTITY(1,1) NOT NULL,
    [CategoryName] NVARCHAR(100) NOT NULL,
    [SortOrder] INT NOT NULL DEFAULT ((0)),
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_WorkItemCategories] PRIMARY KEY CLUSTERED ([WorkItemCategoryID])
);

CREATE TABLE dbo.[WorkItems] (
    [WorkItemID] INT IDENTITY(1,1) NOT NULL,
    [WorkType] NVARCHAR(50) NOT NULL DEFAULT ('Maintenance Request'),
    [PropertyID] INT NULL,
    [TenantID] INT NULL,
    [LeaseID] INT NULL,
    [Suite] NVARCHAR(50) NULL,
    [Category] NVARCHAR(100) NULL,
    [Title] NVARCHAR(200) NOT NULL,
    [Description] NVARCHAR(MAX) NULL,
    [Status] NVARCHAR(50) NOT NULL DEFAULT ('New'),
    [Priority] NVARCHAR(20) NOT NULL DEFAULT ('Normal'),
    [Source] NVARCHAR(100) NULL,
    [SourceCommunicationID] INT NULL,
    [DateReported] DATE NULL,
    [TargetDate] DATE NULL,
    [ScheduledDate] DATE NULL,
    [CompletedDate] DATETIME NULL,
    [AssignedTo] NVARCHAR(100) NULL,
    [VendorName] NVARCHAR(200) NULL,
    [EstimatedCost] DECIMAL(18,2) NULL,
    [ActualCost] DECIMAL(18,2) NULL,
    [IsCapitalProject] BIT NOT NULL DEFAULT ((0)),
    [IsBillableToTenant] BIT NOT NULL DEFAULT ((0)),
    [Notes] NVARCHAR(MAX) NULL,
    [ResolutionSummary] NVARCHAR(MAX) NULL,
    [CreatedDate] DATETIME NOT NULL DEFAULT (getdate()),
    [UpdatedDate] DATETIME NULL,
    [CategoryID] INT NULL,
    [StatusID] INT NULL,
    [VendorID] INT NULL,
    CONSTRAINT [PK_WorkItems] PRIMARY KEY CLUSTERED ([WorkItemID])
);

CREATE TABLE dbo.[WorkItemStatuses] (
    [WorkItemStatusID] INT IDENTITY(1,1) NOT NULL,
    [StatusName] NVARCHAR(100) NOT NULL,
    [SortOrder] INT NOT NULL DEFAULT ((0)),
    [IsActive] BIT NOT NULL DEFAULT ((1)),
    CONSTRAINT [PK_WorkItemStatuses] PRIMARY KEY CLUSTERED ([WorkItemStatusID])
);

-- ============================================================
-- Foreign keys
-- ============================================================

ALTER TABLE dbo.[Actions_legacy] ADD CONSTRAINT [FK_Actions_Communications] FOREIGN KEY ([SourceCommunicationID]) REFERENCES dbo.[Communications] ([CommunicationID]);
ALTER TABLE dbo.[Actions_legacy] ADD CONSTRAINT [FK_Actions_Leases] FOREIGN KEY ([LeaseID]) REFERENCES dbo.[Leases] ([LeaseID]);
ALTER TABLE dbo.[Actions_legacy] ADD CONSTRAINT [FK_Actions_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[Actions_legacy] ADD CONSTRAINT [FK_Actions_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[Communications] ADD CONSTRAINT [FK_Communications_Contacts] FOREIGN KEY ([ContactID]) REFERENCES dbo.[Contacts] ([ContactID]);
ALTER TABLE dbo.[Communications] ADD CONSTRAINT [FK_Communications_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[Communications] ADD CONSTRAINT [FK_Communications_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[Contacts] ADD CONSTRAINT [FK_Contacts_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[ContactSensitiveInfo] ADD CONSTRAINT [FK_ContactSensitiveInfo_Contacts] FOREIGN KEY ([ContactID]) REFERENCES dbo.[Contacts] ([ContactID]);
ALTER TABLE dbo.[LeaseDocumentSections] ADD CONSTRAINT [FK_LeaseDocumentPieces_Leases] FOREIGN KEY ([LeaseID]) REFERENCES dbo.[Leases] ([LeaseID]);
ALTER TABLE dbo.[LeaseDocumentSections] ADD CONSTRAINT [FK_LeaseDocumentPieces_SourceDocuments] FOREIGN KEY ([LeaseSourceDocumentID]) REFERENCES dbo.[LeaseSourceDocuments] ([LeaseSourceDocumentID]);
ALTER TABLE dbo.[LeaseGeneratedDocuments] ADD CONSTRAINT [FK_LeaseGeneratedDocuments_Leases] FOREIGN KEY ([LeaseID]) REFERENCES dbo.[Leases] ([LeaseID]);
ALTER TABLE dbo.[LeaseGeneratedDocumentSections] ADD CONSTRAINT [FK_LeaseGeneratedDocumentPieces_DocumentPieces] FOREIGN KEY ([LeaseDocumentPieceID]) REFERENCES dbo.[LeaseDocumentSections] ([LeaseDocumentSectionID]);
ALTER TABLE dbo.[LeaseGeneratedDocumentSections] ADD CONSTRAINT [FK_LeaseGeneratedDocumentPieces_GeneratedDocuments] FOREIGN KEY ([LeaseGeneratedDocumentID]) REFERENCES dbo.[LeaseGeneratedDocuments] ([LeaseGeneratedDocumentID]);
ALTER TABLE dbo.[LeaseRentSchedule] ADD CONSTRAINT [FK_LeaseRentSchedule_LeaseRentIncreaseTypes] FOREIGN KEY ([IncreaseTypeID]) REFERENCES dbo.[LeaseRentIncreaseTypes] ([IncreaseTypeID]);
ALTER TABLE dbo.[LeaseRentSchedule] ADD CONSTRAINT [FK_LeaseRentSchedule_Leases] FOREIGN KEY ([LeaseID]) REFERENCES dbo.[Leases] ([LeaseID]);
ALTER TABLE dbo.[Leases] ADD CONSTRAINT [FK_Leases_LeaseTermTypes] FOREIGN KEY ([LeaseTermTypeID]) REFERENCES dbo.[LeaseTermTypes] ([LeaseTermTypeID]);
ALTER TABLE dbo.[Leases] ADD CONSTRAINT [FK_Leases_LeaseTypes] FOREIGN KEY ([LeaseTypeID]) REFERENCES dbo.[LeaseTypes] ([LeaseTypeID]);
ALTER TABLE dbo.[Leases] ADD CONSTRAINT [FK_Leases_ParentLeaseID] FOREIGN KEY ([ParentLeaseID]) REFERENCES dbo.[Leases] ([LeaseID]);
ALTER TABLE dbo.[Leases] ADD CONSTRAINT [FK_Leases_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[Leases] ADD CONSTRAINT [FK_Leases_PropertySuites] FOREIGN KEY ([SuiteID]) REFERENCES dbo.[PropertySuites] ([SuiteID]);
ALTER TABLE dbo.[Leases] ADD CONSTRAINT [FK_Leases_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[LeaseSourceDocuments] ADD CONSTRAINT [FK_LeaseSourceDocuments_Leases] FOREIGN KEY ([LeaseID]) REFERENCES dbo.[Leases] ([LeaseID]);
ALTER TABLE dbo.[PropertyFinancials] ADD CONSTRAINT [FK_PropertyFinancials_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[PropertySuites] ADD CONSTRAINT [FK_PropertySuites_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[Prospects] ADD CONSTRAINT [FK_Prospects_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[Prospects] ADD CONSTRAINT [FK_Prospects_Tenants_ConvertedTenantID] FOREIGN KEY ([ConvertedTenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[TenantAddresses] ADD CONSTRAINT [FK_TenantAddresses_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[TenantDocuments] ADD CONSTRAINT [FK_TenantDocuments_DocumentTypes] FOREIGN KEY ([DocumentTypeID]) REFERENCES dbo.[DocumentTypes] ([DocumentTypeID]);
ALTER TABLE dbo.[TenantDocuments] ADD CONSTRAINT [FK_TenantDocuments_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[TenantDocuments] ADD CONSTRAINT [FK_TenantDocuments_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[TenantReferences] ADD CONSTRAINT [FK_TenantReferences_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[Tenants] ADD CONSTRAINT [FK_Tenants_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[Tenants] ADD CONSTRAINT [FK_Tenants_PropertySuites] FOREIGN KEY ([SuiteID]) REFERENCES dbo.[PropertySuites] ([SuiteID]);
ALTER TABLE dbo.[Tenants] ADD CONSTRAINT [FK_Tenants_Prospects] FOREIGN KEY ([ProspectID]) REFERENCES dbo.[Prospects] ([ProspectID]);
ALTER TABLE dbo.[Tenants] ADD CONSTRAINT [FK_Tenants_Prospects_ProspectID] FOREIGN KEY ([ProspectID]) REFERENCES dbo.[Prospects] ([ProspectID]);
ALTER TABLE dbo.[TenantScreeningFactors] ADD CONSTRAINT [FK_TenantScreeningFactors_Screening] FOREIGN KEY ([ScreeningID]) REFERENCES dbo.[TenantScreenings] ([TenantScreeningID]);
ALTER TABLE dbo.[TenantScreenings] ADD CONSTRAINT [FK_TenantScreenings_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[Vendors] ADD CONSTRAINT [FK_Vendors_WorkItemCategories] FOREIGN KEY ([VendorCategoryID]) REFERENCES dbo.[WorkItemCategories] ([WorkItemCategoryID]);
ALTER TABLE dbo.[WorkItemActions] ADD CONSTRAINT [FK_WorkItemActions_Vendors] FOREIGN KEY ([VendorID]) REFERENCES dbo.[Vendors] ([VendorID]);
ALTER TABLE dbo.[WorkItemActions] ADD CONSTRAINT [FK_WorkItemActions_WorkItemBids] FOREIGN KEY ([WorkItemBidID]) REFERENCES dbo.[WorkItemBids] ([WorkItemBidID]);
ALTER TABLE dbo.[WorkItemActions] ADD CONSTRAINT [FK_WorkItemActions_WorkItems] FOREIGN KEY ([WorkItemID]) REFERENCES dbo.[WorkItems] ([WorkItemID]);
ALTER TABLE dbo.[WorkItemBids] ADD CONSTRAINT [FK_WorkItemBids_Vendors] FOREIGN KEY ([VendorID]) REFERENCES dbo.[Vendors] ([VendorID]);
ALTER TABLE dbo.[WorkItemBids] ADD CONSTRAINT [FK_WorkItemBids_WorkItems] FOREIGN KEY ([WorkItemID]) REFERENCES dbo.[WorkItems] ([WorkItemID]);
ALTER TABLE dbo.[WorkItems] ADD CONSTRAINT [FK_WorkItems_Communications] FOREIGN KEY ([SourceCommunicationID]) REFERENCES dbo.[Communications] ([CommunicationID]);
ALTER TABLE dbo.[WorkItems] ADD CONSTRAINT [FK_WorkItems_Leases] FOREIGN KEY ([LeaseID]) REFERENCES dbo.[Leases] ([LeaseID]);
ALTER TABLE dbo.[WorkItems] ADD CONSTRAINT [FK_WorkItems_Properties] FOREIGN KEY ([PropertyID]) REFERENCES dbo.[Properties] ([PropertyID]);
ALTER TABLE dbo.[WorkItems] ADD CONSTRAINT [FK_WorkItems_Tenants] FOREIGN KEY ([TenantID]) REFERENCES dbo.[Tenants] ([TenantID]);
ALTER TABLE dbo.[WorkItems] ADD CONSTRAINT [FK_WorkItems_Vendors] FOREIGN KEY ([VendorID]) REFERENCES dbo.[Vendors] ([VendorID]);
ALTER TABLE dbo.[WorkItems] ADD CONSTRAINT [FK_WorkItems_WorkItemCategories] FOREIGN KEY ([CategoryID]) REFERENCES dbo.[WorkItemCategories] ([WorkItemCategoryID]);
ALTER TABLE dbo.[WorkItems] ADD CONSTRAINT [FK_WorkItems_WorkItemStatuses] FOREIGN KEY ([StatusID]) REFERENCES dbo.[WorkItemStatuses] ([WorkItemStatusID]);

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX [IX_Actions_PropertyID] ON dbo.[Actions_legacy] ([PropertyID]);
CREATE INDEX [IX_Actions_SourceCommunicationID] ON dbo.[Actions_legacy] ([SourceCommunicationID]);
CREATE INDEX [IX_Actions_Status_DueDate] ON dbo.[Actions_legacy] ([Status], [DueDate]);
CREATE INDEX [IX_Actions_TenantID] ON dbo.[Actions_legacy] ([TenantID]);
CREATE INDEX [IX_Communications_NextActionDate_CommDate] ON dbo.[Communications] ([NextActionDate], [CommDate]);
CREATE INDEX [IX_Communications_TenantID_CommDate] ON dbo.[Communications] ([TenantID], [CommDate]);
CREATE INDEX [IX_Contacts_TenantID_IsPrimary_Last_First] ON dbo.[Contacts] ([TenantID], [IsPrimary], [LastName], [FirstName]);
CREATE UNIQUE INDEX [UX_Contacts_OnePrimaryPerTenant] ON dbo.[Contacts] ([TenantID]);
CREATE UNIQUE INDEX [UQ_ContactSensitiveInfo_ContactID] ON dbo.[ContactSensitiveInfo] ([ContactID]);
CREATE INDEX [IX_LeaseDocumentPieces_LeaseID] ON dbo.[LeaseDocumentSections] ([LeaseID], [SortOrder]);
CREATE INDEX [IX_LeaseDocumentPieces_SourceDocumentID] ON dbo.[LeaseDocumentSections] ([LeaseSourceDocumentID], [SortOrder]);
CREATE INDEX [IX_LeaseGeneratedDocuments_LeaseID] ON dbo.[LeaseGeneratedDocuments] ([LeaseID], [GeneratedOn]);
CREATE INDEX [IX_LeaseGeneratedDocumentPieces_GeneratedDocumentID] ON dbo.[LeaseGeneratedDocumentSections] ([LeaseGeneratedDocumentID], [SortOrder]);
CREATE INDEX [IX_LeasePackageSections_Generated_Sort] ON dbo.[LeasePackageSections] ([LeaseGeneratedDocumentID], [SortOrder], [LeasePackageSectionID]);
CREATE UNIQUE INDEX [UQ_LeaseRentIncreaseTypes_IncreaseTypeName] ON dbo.[LeaseRentIncreaseTypes] ([IncreaseTypeName]);
CREATE UNIQUE INDEX [UX_LeaseRentIncreaseTypes_IncreaseTypeID] ON dbo.[LeaseRentIncreaseTypes] ([IncreaseTypeID]);
CREATE UNIQUE INDEX [UQ_LeaseRentIncreaseTypes_IncreaseTypeName] ON dbo.[LeaseRentIncreaseTypes_Legacy_20260315_123957] ([IncreaseTypeName]);
CREATE INDEX [IX_LeaseRentSchedule_IncreaseTypeID] ON dbo.[LeaseRentSchedule] ([IncreaseTypeID]);
CREATE INDEX [IX_LeaseRentSchedule_LeaseID_EffectiveStartDate] ON dbo.[LeaseRentSchedule] ([LeaseID], [EffectiveStartDate]);
CREATE INDEX [IX_Leases_LeaseEnd] ON dbo.[Leases] ([TenantID], [PropertyID], [LeaseTypeID], [RentAmount], [LeaseEnd]);
CREATE INDEX [IX_Leases_SuiteID] ON dbo.[Leases] ([SuiteID]);
CREATE INDEX [IX_Leases_TenantID_LeaseEnd_LeaseStart] ON dbo.[Leases] ([TenantID], [LeaseEnd], [LeaseStart]);
CREATE INDEX [IX_LeaseSourceDocuments_LeaseID] ON dbo.[LeaseSourceDocuments] ([LeaseID]);
CREATE INDEX [IX_LeaseTemplates_PropertyID_IsActive] ON dbo.[LeaseTemplates] ([PropertyID], [IsActive], [TemplateName]);
CREATE INDEX [IX_LeaseTemplateSections_Template_Sort] ON dbo.[LeaseTemplateSections] ([LeaseTemplateID], [SortOrder], [LeaseTemplateSectionID]);
CREATE INDEX [IX_PropertyFinancials_PropertyID_FiscalYear] ON dbo.[PropertyFinancials] ([PropertyID], [FiscalYear]);
CREATE UNIQUE INDEX [UQ_PropertyFinancials_PropertyID_FiscalYear] ON dbo.[PropertyFinancials] ([PropertyID], [FiscalYear]);
CREATE INDEX [IX_PropertySuites_PropertyID_IsActive_SortOrder] ON dbo.[PropertySuites] ([PropertyID], [IsActive], [SortOrder], [SuiteLabel]);
CREATE UNIQUE INDEX [UQ_PropertySuites_PropertyID_SuiteLabel] ON dbo.[PropertySuites] ([PropertyID], [SuiteLabel]);
CREATE UNIQUE INDEX [UX_PropertySuites_PropertyID_SuiteLabel] ON dbo.[PropertySuites] ([PropertyID], [SuiteLabel]);
CREATE INDEX [IX_Prospects_Email] ON dbo.[Prospects] ([Email]);
CREATE INDEX [IX_Prospects_Phone] ON dbo.[Prospects] ([Phone]);
CREATE INDEX [IX_Prospects_Status_Property] ON dbo.[Prospects] ([ProspectStatus], [PropertyID], [DateCreated]);
CREATE UNIQUE INDEX [UQ_SchemaChangeLog_ScriptName] ON dbo.[SchemaChangeLog] ([ScriptName]);
CREATE UNIQUE INDEX [UX_SchemaChangeLog_ScriptName] ON dbo.[SchemaChangeLog] ([ScriptName]);
CREATE INDEX [IX_TenantAddresses_TenantID_IsPrimary] ON dbo.[TenantAddresses] ([TenantID], [IsPrimary]);
CREATE UNIQUE INDEX [UX_TenantAddresses_OnePrimaryPerTenant] ON dbo.[TenantAddresses] ([TenantID]);
CREATE INDEX [IX_TenantDocuments_ExpirationDate] ON dbo.[TenantDocuments] ([TenantID], [PropertyID], [DocumentTypeID], [ExpirationDate]);
CREATE INDEX [IX_TenantDocuments_TenantID_ExpirationDate] ON dbo.[TenantDocuments] ([TenantID], [ExpirationDate]);
CREATE INDEX [IX_Tenants_ProspectID] ON dbo.[Tenants] ([ProspectID]);
CREATE INDEX [IX_Tenants_SuiteID] ON dbo.[Tenants] ([SuiteID]);
CREATE INDEX [IX_Tenants_TenantStatusID] ON dbo.[Tenants] ([TenantID], [PropertyID], [TenantName], [TenantStatusID]);
CREATE INDEX [IX_Vendors_IsActive_VendorName] ON dbo.[Vendors] ([IsActive], [VendorName]);
CREATE UNIQUE INDEX [UQ_Vendors_VendorName] ON dbo.[Vendors] ([VendorName]);
CREATE INDEX [IX_WorkItemActions_VendorID] ON dbo.[WorkItemActions] ([VendorID]);
CREATE INDEX [IX_WorkItemActions_WorkItemBidID] ON dbo.[WorkItemActions] ([WorkItemBidID]);
CREATE INDEX [IX_WorkItemActions_WorkItemID_Status_DueDate] ON dbo.[WorkItemActions] ([WorkItemID], [ActionStatus], [DueDate]);
CREATE INDEX [IX_WorkItemBids_VendorID] ON dbo.[WorkItemBids] ([VendorID]);
CREATE INDEX [IX_WorkItemBids_WorkItemID] ON dbo.[WorkItemBids] ([WorkItemID], [BidStatus], [BidDate]);
CREATE UNIQUE INDEX [UQ_WorkItemCategories_CategoryName] ON dbo.[WorkItemCategories] ([CategoryName]);
CREATE INDEX [IX_WorkItems_CategoryID] ON dbo.[WorkItems] ([CategoryID]);
CREATE INDEX [IX_WorkItems_SourceCommunicationID] ON dbo.[WorkItems] ([SourceCommunicationID]);
CREATE INDEX [IX_WorkItems_Status_TargetDate] ON dbo.[WorkItems] ([Status], [TargetDate], [PropertyID], [TenantID]);
CREATE INDEX [IX_WorkItems_StatusID] ON dbo.[WorkItems] ([StatusID]);
CREATE INDEX [IX_WorkItems_StatusID_TargetDate] ON dbo.[WorkItems] ([StatusID], [TargetDate], [PropertyID], [TenantID]);
CREATE INDEX [IX_WorkItems_TenantID] ON dbo.[WorkItems] ([TenantID], [Status], [TargetDate]);
CREATE INDEX [IX_WorkItems_TenantID_StatusID] ON dbo.[WorkItems] ([TenantID], [StatusID], [TargetDate]);
CREATE INDEX [IX_WorkItems_Type_Status] ON dbo.[WorkItems] ([WorkType], [Status], [PropertyID]);
CREATE INDEX [IX_WorkItems_Type_StatusID] ON dbo.[WorkItems] ([WorkType], [StatusID], [PropertyID]);
CREATE INDEX [IX_WorkItems_VendorID] ON dbo.[WorkItems] ([VendorID]);
CREATE UNIQUE INDEX [UQ_WorkItemStatuses_StatusName] ON dbo.[WorkItemStatuses] ([StatusName]);
