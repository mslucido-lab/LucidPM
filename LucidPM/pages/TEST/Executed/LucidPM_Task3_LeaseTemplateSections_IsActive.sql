/* Lucid Property Manager - Task 3 SQL support
   Adds IsActive to LeaseTemplateSections if Task 2 table already exists without it.
   Safe to run multiple times against TenantCRM_Test first.
*/
IF OBJECT_ID('dbo.LeaseTemplateSections', 'U') IS NOT NULL
AND COL_LENGTH('dbo.LeaseTemplateSections', 'IsActive') IS NULL
BEGIN
    ALTER TABLE dbo.LeaseTemplateSections
    ADD IsActive BIT NOT NULL
        CONSTRAINT DF_LeaseTemplateSections_IsActive2 DEFAULT (1);
END;
