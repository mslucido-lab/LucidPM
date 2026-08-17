/*
Lucid Property Manager
Lease document schema migration v2.6.3
Purpose:
  - Add lease document merge fields to Properties and PropertySuites
  - Add text Content support to LeaseDocumentPieces
  - Seed basic merge template only if safe
  - Log migration in SchemaChangeLog

Safe to run multiple times.
Run in TEST first, then PROD.
*/

DECLARE @ScriptName NVARCHAR(255) = 'lease_document_schema_v2_6_3_fixed.sql';

IF NOT EXISTS (
    SELECT 1
    FROM dbo.SchemaChangeLog
    WHERE ScriptName = @ScriptName
)
BEGIN
    BEGIN TRY
        BEGIN TRANSACTION;

        /* LeaseDocumentPieces.Content */
        IF COL_LENGTH('dbo.LeaseDocumentPieces', 'Content') IS NULL
        BEGIN
            ALTER TABLE dbo.LeaseDocumentPieces
            ADD Content NVARCHAR(MAX) NULL;
        END;

        /* Properties merge fields */
        IF COL_LENGTH('dbo.Properties', 'LandlordEntityName') IS NULL
        BEGIN
            ALTER TABLE dbo.Properties ADD LandlordEntityName NVARCHAR(255) NULL;
        END;

        IF COL_LENGTH('dbo.Properties', 'PropertyLegalDescription') IS NULL
        BEGIN
            ALTER TABLE dbo.Properties ADD PropertyLegalDescription NVARCHAR(MAX) NULL;
        END;

        IF COL_LENGTH('dbo.Properties', 'PropertyCounty') IS NULL
        BEGIN
            ALTER TABLE dbo.Properties ADD PropertyCounty NVARCHAR(100) NULL;
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

        /* PropertySuites merge fields */
        IF COL_LENGTH('dbo.PropertySuites', 'SuiteLegalDescription') IS NULL
        BEGIN
            ALTER TABLE dbo.PropertySuites ADD SuiteLegalDescription NVARCHAR(MAX) NULL;
        END;

        IF COL_LENGTH('dbo.PropertySuites', 'SuitePremisesDescription') IS NULL
        BEGIN
            ALTER TABLE dbo.PropertySuites ADD SuitePremisesDescription NVARCHAR(MAX) NULL;
        END;

        IF COL_LENGTH('dbo.PropertySuites', 'SuiteAddressOverride') IS NULL
        BEGIN
            ALTER TABLE dbo.PropertySuites ADD SuiteAddressOverride NVARCHAR(500) NULL;
        END;

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        DECLARE @Err1 NVARCHAR(MAX) = ERROR_MESSAGE();
        RAISERROR('Lease document schema column migration failed: %s', 16, 1, @Err1);
        RETURN;
    END CATCH;
END;
GO

/*
Seed defaults in a separate batch so SQL Server recognizes newly added columns.
Use dynamic SQL so this remains safe even when columns were just created.
*/
DECLARE @ScriptName NVARCHAR(255) = 'lease_document_schema_v2_6_3_fixed.sql';

IF NOT EXISTS (
    SELECT 1
    FROM dbo.SchemaChangeLog
    WHERE ScriptName = @ScriptName
)
BEGIN
    BEGIN TRY
        BEGIN TRANSACTION;

        EXEC(N'
            UPDATE dbo.Properties
            SET LandlordEntityName = CASE
                    WHEN LOWER(LTRIM(RTRIM(ISNULL(PropertyName, '''')))) = ''broadway'' THEN ''Dor-Sal Capital Partners, LLC''
                    WHEN LOWER(LTRIM(RTRIM(ISNULL(PropertyName, '''')))) = ''walnut'' THEN ''Lucido Properties SP, LLC''
                    WHEN LOWER(LTRIM(RTRIM(ISNULL(PropertyName, '''')))) = ''euless'' THEN ''Lucido Properties 508, LLC''
                    ELSE LandlordEntityName
                END,
                PropertyCounty = CASE
                    WHEN PropertyCounty IS NULL OR LTRIM(RTRIM(PropertyCounty)) = '''' THEN ''Dallas''
                    ELSE PropertyCounty
                END,
                PropertyUseDefault = CASE
                    WHEN PropertyUseDefault IS NULL OR LTRIM(RTRIM(PropertyUseDefault)) = '''' THEN ''Office/Warehouse/Showroom''
                    ELSE PropertyUseDefault
                END
            WHERE LandlordEntityName IS NULL
               OR LTRIM(RTRIM(ISNULL(LandlordEntityName, ''''))) = ''''
               OR PropertyCounty IS NULL
               OR LTRIM(RTRIM(ISNULL(PropertyCounty, ''''))) = ''''
               OR PropertyUseDefault IS NULL
               OR LTRIM(RTRIM(ISNULL(PropertyUseDefault, ''''))) = '''';
        ');

        EXEC(N'
            UPDATE dbo.LeaseDocumentPieces
            SET Content = ''
LEASE AGREEMENT

Tenant: {{TenantName}}
Property: {{PropertyName}}
Suite: {{SuiteLabel}}

Base Rent: {{RentAmount}}

Lease Term:
Start: {{LeaseStart}}
End: {{LeaseEnd}}
''
            WHERE LeaseDocumentPieceID = 1
              AND Content IS NULL;
        ');

        INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
        VALUES (
            @ScriptName,
            GETDATE(),
            SYSTEM_USER,
            'Added lease document merge fields, LeaseDocumentPieces.Content, seeded property defaults and one test merge template.'
        );

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        DECLARE @Err2 NVARCHAR(MAX) = ERROR_MESSAGE();
        RAISERROR('Lease document schema seed/log migration failed: %s', 16, 1, @Err2);
    END CATCH;
END;
GO
