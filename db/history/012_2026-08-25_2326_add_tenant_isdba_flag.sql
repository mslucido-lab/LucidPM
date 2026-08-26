-- Add IsDBA flag to Tenants: marks a tenant as an individual/partnership
-- operating under TenantName as a d.b.a. (trade name), rather than TenantName
-- being that individual's/entity's own legal name. Drives the
-- DBAName/TenantNameWithDBA merge tokens in lease_merge.py.
-- Run against TenantCRM_Test first. Verify. Then run against TenantCRM.

IF COL_LENGTH('dbo.Tenants', 'IsDBA') IS NULL
BEGIN
    ALTER TABLE dbo.Tenants ADD IsDBA BIT NOT NULL DEFAULT 0;
END;

IF OBJECT_ID('dbo.SchemaChangeLog', 'U') IS NOT NULL
    AND NOT EXISTS (
        SELECT 1
        FROM dbo.SchemaChangeLog
        WHERE ScriptName = 'add_tenant_isdba_flag.sql'
    )
BEGIN
    INSERT INTO dbo.SchemaChangeLog (ScriptName, AppliedOn, AppliedBy, Notes)
    VALUES (
        'add_tenant_isdba_flag.sql',
        GETDATE(),
        SUSER_SNAME(),
        'Added Tenants.IsDBA (bit, default 0) so the existing DBAName/TenantNameWithDBA merge tokens can resolve to real d.b.a. phrasing instead of always being blank/plain tenant name.'
    );
END;
