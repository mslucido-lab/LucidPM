/*
Lucido Property Manager
Schema cleanup: Lease document naming refactor, Piece -> Section
Run against TEST first only: TenantCRM_Test
Date: 2026-04-27

Purpose:
- Rename lease document backend/database objects from Piece naming to Section naming.
- Preserve behavior. This script only renames tables/columns and logs the change.

Before running:
1. Back up TenantCRM_Test.
2. Confirm the app is stopped.
3. Run this script in SSMS against TenantCRM_Test first.
4. Review PRINT output.
5. Smoke test the app before running against production.
*/

SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRANSACTION;

    PRINT 'Starting lease document naming refactor: Piece -> Section';

    -------------------------------------------------------------------------
    -- 1. Rename tables
    -------------------------------------------------------------------------

    IF OBJECT_ID('dbo.LeaseDocumentPieces', 'U') IS NOT NULL
       AND OBJECT_ID('dbo.LeaseDocumentSections', 'U') IS NULL
    BEGIN
        EXEC sp_rename 'dbo.LeaseDocumentPieces', 'LeaseDocumentSections';
        PRINT 'Renamed table dbo.LeaseDocumentPieces -> dbo.LeaseDocumentSections';
    END
    ELSE
    BEGIN
        PRINT 'Skipped table rename LeaseDocumentPieces -> LeaseDocumentSections';
    END

    IF OBJECT_ID('dbo.LeaseGeneratedDocumentPieces', 'U') IS NOT NULL
       AND OBJECT_ID('dbo.LeaseGeneratedDocumentSections', 'U') IS NULL
    BEGIN
        EXEC sp_rename 'dbo.LeaseGeneratedDocumentPieces', 'LeaseGeneratedDocumentSections';
        PRINT 'Renamed table dbo.LeaseGeneratedDocumentPieces -> dbo.LeaseGeneratedDocumentSections';
    END
    ELSE
    BEGIN
        PRINT 'Skipped table rename LeaseGeneratedDocumentPieces -> LeaseGeneratedDocumentSections';
    END

    -------------------------------------------------------------------------
    -- 2. Rename columns on LeaseDocumentSections
    -------------------------------------------------------------------------

    IF COL_LENGTH('dbo.LeaseDocumentSections', 'LeaseDocumentPieceID') IS NOT NULL
       AND COL_LENGTH('dbo.LeaseDocumentSections', 'LeaseDocumentSectionID') IS NULL
    BEGIN
        EXEC sp_rename 'dbo.LeaseDocumentSections.LeaseDocumentPieceID', 'LeaseDocumentSectionID', 'COLUMN';
        PRINT 'Renamed LeaseDocumentSections.LeaseDocumentPieceID -> LeaseDocumentSectionID';
    END

    IF COL_LENGTH('dbo.LeaseDocumentSections', 'PieceID') IS NOT NULL
       AND COL_LENGTH('dbo.LeaseDocumentSections', 'SectionID') IS NULL
    BEGIN
        EXEC sp_rename 'dbo.LeaseDocumentSections.PieceID', 'SectionID', 'COLUMN';
        PRINT 'Renamed LeaseDocumentSections.PieceID -> SectionID';
    END

    IF COL_LENGTH('dbo.LeaseDocumentSections', 'PieceName') IS NOT NULL
       AND COL_LENGTH('dbo.LeaseDocumentSections', 'SectionName') IS NULL
    BEGIN
        EXEC sp_rename 'dbo.LeaseDocumentSections.PieceName', 'SectionName', 'COLUMN';
        PRINT 'Renamed LeaseDocumentSections.PieceName -> SectionName';
    END

    IF COL_LENGTH('dbo.LeaseDocumentSections', 'PieceType') IS NOT NULL
       AND COL_LENGTH('dbo.LeaseDocumentSections', 'SectionType') IS NULL
    BEGIN
        EXEC sp_rename 'dbo.LeaseDocumentSections.PieceType', 'SectionType', 'COLUMN';
        PRINT 'Renamed LeaseDocumentSections.PieceType -> SectionType';
    END

    IF COL_LENGTH('dbo.LeaseDocumentSections', 'PiecePath') IS NOT NULL
       AND COL_LENGTH('dbo.LeaseDocumentSections', 'SectionPath') IS NULL
    BEGIN
        EXEC sp_rename 'dbo.LeaseDocumentSections.PiecePath', 'SectionPath', 'COLUMN';
        PRINT 'Renamed LeaseDocumentSections.PiecePath -> SectionPath';
    END

    -------------------------------------------------------------------------
    -- 3. Rename columns on LeaseGeneratedDocumentSections
    -------------------------------------------------------------------------

    IF OBJECT_ID('dbo.LeaseGeneratedDocumentSections', 'U') IS NOT NULL
    BEGIN
        IF COL_LENGTH('dbo.LeaseGeneratedDocumentSections', 'LeaseGeneratedDocumentPieceID') IS NOT NULL
           AND COL_LENGTH('dbo.LeaseGeneratedDocumentSections', 'LeaseGeneratedDocumentSectionID') IS NULL
        BEGIN
            EXEC sp_rename 'dbo.LeaseGeneratedDocumentSections.LeaseGeneratedDocumentPieceID', 'LeaseGeneratedDocumentSectionID', 'COLUMN';
            PRINT 'Renamed LeaseGeneratedDocumentSections.LeaseGeneratedDocumentPieceID -> LeaseGeneratedDocumentSectionID';
        END

        IF COL_LENGTH('dbo.LeaseGeneratedDocumentSections', 'PieceID') IS NOT NULL
           AND COL_LENGTH('dbo.LeaseGeneratedDocumentSections', 'SectionID') IS NULL
        BEGIN
            EXEC sp_rename 'dbo.LeaseGeneratedDocumentSections.PieceID', 'SectionID', 'COLUMN';
            PRINT 'Renamed LeaseGeneratedDocumentSections.PieceID -> SectionID';
        END

        IF COL_LENGTH('dbo.LeaseGeneratedDocumentSections', 'PieceName') IS NOT NULL
           AND COL_LENGTH('dbo.LeaseGeneratedDocumentSections', 'SectionName') IS NULL
        BEGIN
            EXEC sp_rename 'dbo.LeaseGeneratedDocumentSections.PieceName', 'SectionName', 'COLUMN';
            PRINT 'Renamed LeaseGeneratedDocumentSections.PieceName -> SectionName';
        END

        IF COL_LENGTH('dbo.LeaseGeneratedDocumentSections', 'PieceType') IS NOT NULL
           AND COL_LENGTH('dbo.LeaseGeneratedDocumentSections', 'SectionType') IS NULL
        BEGIN
            EXEC sp_rename 'dbo.LeaseGeneratedDocumentSections.PieceType', 'SectionType', 'COLUMN';
            PRINT 'Renamed LeaseGeneratedDocumentSections.PieceType -> SectionType';
        END
    END

    -------------------------------------------------------------------------
    -- 4. Rename template/package columns
    -------------------------------------------------------------------------

    IF OBJECT_ID('dbo.LeaseTemplateSections', 'U') IS NOT NULL
    BEGIN
        IF COL_LENGTH('dbo.LeaseTemplateSections', 'DefaultPieceID') IS NOT NULL
           AND COL_LENGTH('dbo.LeaseTemplateSections', 'DefaultSectionID') IS NULL
        BEGIN
            EXEC sp_rename 'dbo.LeaseTemplateSections.DefaultPieceID', 'DefaultSectionID', 'COLUMN';
            PRINT 'Renamed LeaseTemplateSections.DefaultPieceID -> DefaultSectionID';
        END
    END

    IF OBJECT_ID('dbo.LeasePackageSections', 'U') IS NOT NULL
    BEGIN
        IF COL_LENGTH('dbo.LeasePackageSections', 'PieceID') IS NOT NULL
           AND COL_LENGTH('dbo.LeasePackageSections', 'SectionID') IS NULL
        BEGIN
            EXEC sp_rename 'dbo.LeasePackageSections.PieceID', 'SectionID', 'COLUMN';
            PRINT 'Renamed LeasePackageSections.PieceID -> SectionID';
        END
    END

    -------------------------------------------------------------------------
    -- 5. Log schema change
    -------------------------------------------------------------------------

    IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
    BEGIN
        INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
        VALUES (
            'schema_lease_sections_rename.sql',
            SYSDATETIME(),
            SUSER_SNAME(),
            'Renamed lease document backend/database objects from Piece naming to Section naming. Ran table and column renames with existence checks.'
        );
        PRINT 'Logged change to SchemaChangeLog';
    END
    ELSE
    BEGIN
        PRINT 'SchemaChangeLog not found. Skipped logging.';
    END

    -------------------------------------------------------------------------
    -- 6. Post-check summary
    -------------------------------------------------------------------------

    PRINT 'Post-check: remaining lease columns containing Piece';
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE (TABLE_NAME LIKE 'Lease%' OR TABLE_NAME LIKE '%Lease%')
      AND COLUMN_NAME LIKE '%Piece%'
    ORDER BY TABLE_NAME, COLUMN_NAME;

    PRINT 'Post-check: lease tables containing Piece';
    SELECT
        TABLE_SCHEMA,
        TABLE_NAME
    FROM INFORMATION_SCHEMA.TABLES
    WHERE TABLE_NAME LIKE '%Piece%'
    ORDER BY TABLE_NAME;

    COMMIT TRANSACTION;
    PRINT 'Completed lease document naming refactor successfully.';
END TRY
BEGIN CATCH
    IF @@TRANCOUNT > 0
        ROLLBACK TRANSACTION;

    PRINT 'Refactor failed. Transaction rolled back.';
    PRINT ERROR_MESSAGE();
    THROW;
END CATCH;
