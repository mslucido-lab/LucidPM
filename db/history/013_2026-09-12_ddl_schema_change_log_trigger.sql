-- Automatically log future schema-object DDL in dbo.SchemaChangeLog.
-- Run against TenantCRM_Test first; verify with the Handoff 70 scratch tests;
-- then run against TenantCRM and the corresponding Azure SQL databases.
--
-- This is the final history script that writes its own manual SchemaChangeLog
-- record. Later schema scripts rely on the database-level trigger instead.

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE OR ALTER TRIGGER trg_LogSchemaChanges
ON DATABASE
FOR
    CREATE_TABLE,     ALTER_TABLE,     DROP_TABLE,
    CREATE_INDEX,     ALTER_INDEX,     DROP_INDEX,
    CREATE_VIEW,      ALTER_VIEW,      DROP_VIEW,
    CREATE_PROCEDURE, ALTER_PROCEDURE, DROP_PROCEDURE,
    CREATE_FUNCTION,  ALTER_FUNCTION,  DROP_FUNCTION,
    CREATE_TRIGGER,   ALTER_TRIGGER,   DROP_TRIGGER
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        DECLARE @data XML = EVENTDATA();
        DECLARE @eventType NVARCHAR(100) =
            @data.value('(/EVENT_INSTANCE/EventType)[1]', 'nvarchar(100)');
        DECLARE @schemaName NVARCHAR(128) =
            @data.value('(/EVENT_INSTANCE/SchemaName)[1]', 'nvarchar(128)');
        DECLARE @objectName NVARCHAR(128) =
            @data.value('(/EVENT_INSTANCE/ObjectName)[1]', 'nvarchar(128)');
        DECLARE @loginName NVARCHAR(128) =
            @data.value('(/EVENT_INSTANCE/LoginName)[1]', 'nvarchar(128)');
        DECLARE @rawCommand NVARCHAR(MAX) =
            @data.value('(/EVENT_INSTANCE/TSQLCommand/CommandText)[1]', 'nvarchar(max)');

        DECLARE @truncationSuffix NVARCHAR(20) = N' ...[TRUNCATED]';
        DECLARE @commandText NVARCHAR(1000) =
            CASE
                WHEN @rawCommand IS NULL THEN NULL
                WHEN LEN(@rawCommand) > 1000
                    THEN LEFT(@rawCommand, 1000 - LEN(@truncationSuffix)) + @truncationSuffix
                ELSE @rawCommand
            END;

        DECLARE @scriptNameSuffix NVARCHAR(80) =
            N' @ ' + CONVERT(NVARCHAR(30), SYSDATETIME(), 121)
            + N' #' + REPLACE(CONVERT(NVARCHAR(36), NEWID()), N'-', N'');
        DECLARE @prefix NVARCHAR(255) =
            N'[AUTO] ' + ISNULL(@eventType, N'DDL')
            + CASE
                  WHEN @objectName IS NOT NULL
                      THEN N' on ' + ISNULL(@schemaName + N'.', N'') + @objectName
                  ELSE N''
              END;
        IF LEN(@prefix) > 255 - LEN(@scriptNameSuffix)
            SET @prefix = LEFT(@prefix, 255 - LEN(@scriptNameSuffix));
        DECLARE @scriptName NVARCHAR(255) = @prefix + @scriptNameSuffix;

        INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
        VALUES (@scriptName, SYSDATETIME(), ISNULL(@loginName, SUSER_SNAME()), @commandText);
    END TRY
    BEGIN CATCH
        -- Logging must never block the actual schema change.
    END CATCH;
END;
GO

IF OBJECT_ID(N'dbo.SchemaChangeLog', N'U') IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM dbo.SchemaChangeLog
        WHERE ScriptName = N'013_2026-09-12_ddl_schema_change_log_trigger.sql'
    )
BEGIN
    INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
    VALUES (
        N'013_2026-09-12_ddl_schema_change_log_trigger.sql',
        SYSDATETIME(),
        SUSER_SNAME(),
        N'Added database-level trg_LogSchemaChanges to auto-log CREATE, ALTER, and DROP operations for schema objects. Auto rows use [AUTO] names and capture T-SQL up to 1000 characters.'
    );
END;
GO
