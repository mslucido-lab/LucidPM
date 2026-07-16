/*
Lucid Property Manager
Lease document token schema migration
Version: 2.6.2
Run against TEST first.

Adds the fields needed for lease merge tokens such as:
{{LandlordEntity}}, {{County}}, {{State}}, {{SuiteFullAddress}},
{{UseType}}, {{LeaseTermDescription}}, {{TotalRent}}, {{PaymentScheduleBlock}}
*/

SET NOCOUNT ON;

/* LeaseDocumentPieces text content for tokenized merge pieces */
IF COL_LENGTH('dbo.LeaseDocumentPieces', 'Content') IS NULL
BEGIN
    ALTER TABLE dbo.LeaseDocumentPieces ADD Content NVARCHAR(MAX) NULL;
END;

/* Property-level lease document defaults */
IF COL_LENGTH('dbo.Properties', 'LandlordEntityName') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD LandlordEntityName NVARCHAR(255) NULL;
END;

IF COL_LENGTH('dbo.Properties', 'PropertyCounty') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD PropertyCounty NVARCHAR(100) NULL;
END;

IF COL_LENGTH('dbo.Properties', 'PropertyLegalDescription') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD PropertyLegalDescription NVARCHAR(MAX) NULL;
END;

IF COL_LENGTH('dbo.Properties', 'PropertyUseDefault') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD PropertyUseDefault NVARCHAR(255) NULL;
END;

IF COL_LENGTH('dbo.Properties', 'LeaseNoticeAddress1') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD LeaseNoticeAddress1 NVARCHAR(255) NULL;
END;

IF COL_LENGTH('dbo.Properties', 'LeaseNoticeAddress2') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD LeaseNoticeAddress2 NVARCHAR(255) NULL;
END;

IF COL_LENGTH('dbo.Properties', 'LeaseNoticeCity') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD LeaseNoticeCity NVARCHAR(100) NULL;
END;

IF COL_LENGTH('dbo.Properties', 'LeaseNoticeState') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD LeaseNoticeState NVARCHAR(50) NULL;
END;

IF COL_LENGTH('dbo.Properties', 'LeaseNoticeZip') IS NULL
BEGIN
    ALTER TABLE dbo.Properties ADD LeaseNoticeZip NVARCHAR(20) NULL;
END;

/* Suite-level lease document overrides */
IF COL_LENGTH('dbo.PropertySuites', 'SuitePremisesDescription') IS NULL
BEGIN
    ALTER TABLE dbo.PropertySuites ADD SuitePremisesDescription NVARCHAR(500) NULL;
END;

IF COL_LENGTH('dbo.PropertySuites', 'SuiteLegalDescription') IS NULL
BEGIN
    ALTER TABLE dbo.PropertySuites ADD SuiteLegalDescription NVARCHAR(MAX) NULL;
END;

IF COL_LENGTH('dbo.PropertySuites', 'SuiteAddressOverride') IS NULL
BEGIN
    ALTER TABLE dbo.PropertySuites ADD SuiteAddressOverride NVARCHAR(500) NULL;
END;

/* Seed landlord entity names from current hardcoded report logic */
UPDATE dbo.Properties
SET LandlordEntityName = CASE
    WHEN LOWER(LTRIM(RTRIM(PropertyName))) = 'broadway' THEN 'Dor-Sal Capital Partners, LLC'
    WHEN LOWER(LTRIM(RTRIM(PropertyName))) = 'walnut' THEN 'Lucido Properties SP, LLC'
    WHEN LOWER(LTRIM(RTRIM(PropertyName))) = 'euless' THEN 'Lucido Properties 508, LLC'
    ELSE LandlordEntityName
END
WHERE ISNULL(LandlordEntityName, '') = '';

/* Seed common defaults without overwriting existing values */
UPDATE dbo.Properties
SET PropertyCounty = 'Dallas'
WHERE ISNULL(PropertyCounty, '') = ''
  AND LOWER(LTRIM(RTRIM(PropertyName))) IN ('broadway', 'walnut');

UPDATE dbo.Properties
SET PropertyCounty = 'Tarrant'
WHERE ISNULL(PropertyCounty, '') = ''
  AND LOWER(LTRIM(RTRIM(PropertyName))) = 'euless';

UPDATE dbo.Properties
SET PropertyUseDefault = 'Office/Warehouse/Showroom'
WHERE ISNULL(PropertyUseDefault, '') = ''
  AND LOWER(LTRIM(RTRIM(PropertyName))) IN ('broadway', 'walnut');

UPDATE dbo.Properties
SET PropertyUseDefault = 'Commercial'
WHERE ISNULL(PropertyUseDefault, '') = ''
  AND LOWER(LTRIM(RTRIM(PropertyName))) = 'euless';

/* Mirror property address into notice address defaults when blank */
UPDATE dbo.Properties
SET LeaseNoticeAddress1 = PropertyAddress1,
    LeaseNoticeAddress2 = PropertyAddress2,
    LeaseNoticeCity = PropertyCity,
    LeaseNoticeState = PropertyState,
    LeaseNoticeZip = PropertyZip
WHERE ISNULL(LeaseNoticeAddress1, '') = '';

/* Log migration when SchemaChangeLog exists */
IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
BEGIN
    IF NOT EXISTS (SELECT 1 FROM dbo.SchemaChangeLog WHERE ScriptName = 'lease_document_schema_v2_6_2.sql')
    BEGIN
        INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
        VALUES (
            'lease_document_schema_v2_6_2.sql',
            GETDATE(),
            SUSER_SNAME(),
            'Added lease document token fields to Properties, PropertySuites, and LeaseDocumentPieces.'
        );
    END;
END;
