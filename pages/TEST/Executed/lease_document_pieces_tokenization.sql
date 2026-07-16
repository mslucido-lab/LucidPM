DECLARE @ScriptName NVARCHAR(255) = 'lease_document_content_migration_v2_6_2.sql';

IF NOT EXISTS (
    SELECT 1 FROM SchemaChangeLog WHERE ScriptName = @ScriptName
)
BEGIN
    BEGIN TRY
        BEGIN TRANSACTION;

        -- Add Content column if it does not exist
        IF NOT EXISTS (
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_NAME = 'LeaseDocumentPieces'
              AND COLUMN_NAME = 'Content'
        )
        BEGIN
            ALTER TABLE LeaseDocumentPieces
            ADD Content NVARCHAR(MAX) NULL;
        END

        -- Seed a basic template ONLY if Content is NULL
        UPDATE LeaseDocumentPieces
        SET Content = '
LEASE AGREEMENT

Tenant: {{TenantName}}
Property: {{PropertyName}}
Suite: {{SuiteLabel}}

Base Rent: {{RentAmount}}

Lease Term:
Start: {{LeaseStart}}
End: {{LeaseEnd}}
'
        WHERE LeaseDocumentPieceID = 1
          AND Content IS NULL;

        -- Log the schema change
        INSERT INTO SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
        VALUES (
            @ScriptName,
            GETDATE(),
            SYSTEM_USER,
            'Added Content column to LeaseDocumentPieces and seeded initial merge template'
        );

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        ROLLBACK TRANSACTION;

        DECLARE @ErrorMessage NVARCHAR(MAX) = ERROR_MESSAGE();
        RAISERROR('Schema migration failed: %s', 16, 1, @ErrorMessage);
    END CATCH
END