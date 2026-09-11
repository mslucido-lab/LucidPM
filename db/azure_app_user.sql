/*  Azure SQL — contained application user for LucidPM
    ---------------------------------------------------------------------------
    Azure Migration, Cycle 2.2 prep. The cloud build must NOT use the server
    admin (lucidadmin). This creates a least-privilege contained user with a
    password, scoped to plain DML on dbo.

    Contained users are PER DATABASE. Run this script once against each database,
    with the SAME password both times, so a single connection string (differing
    only by DATABASE=) works for the Test/Prod toggle:

        1. In SSMS, connect to lucidpm-sql-24899 as lucidadmin.
        2. Set the connection's database to  TenantCRM       -> run this script.
        3. New query, set database to        TenantCRM_Test  -> run it again.

    Azure SQL has no USE statement — the query must already be in the target DB.

    Password policy: >= 8 chars, 3 of 4 of {upper, lower, digit, symbol}, and it
    must not contain 'lucidpm_app'. Generate 24+ random chars in a password
    manager and store it there; replace the placeholder below before running.
    Do NOT commit the real password.

    Grants rationale (verified against live code 2026-09-09): the app issues
    parameterized SELECT / INSERT / UPDATE / DELETE against dbo tables only — no
    DDL, no stored procedures, no sys.* / INFORMATION_SCHEMA reads. db_datareader
    + db_datawriter is sufficient. If a workflow later hits a permission error,
    add the one missing grant rather than broadening to db_owner.
    ---------------------------------------------------------------------------  */

CREATE USER [lucidpm_app] WITH PASSWORD = 'REPLACE_WITH_STRONG_PASSWORD';

ALTER ROLE db_datareader ADD MEMBER [lucidpm_app];
ALTER ROLE db_datawriter ADD MEMBER [lucidpm_app];

/* verify — expect two rows: db_datareader, db_datawriter */
SELECT  dp.name        AS principal,
        dp.type_desc,
        r.name         AS role_membership
FROM        sys.database_principals      dp
LEFT JOIN   sys.database_role_members    drm ON drm.member_principal_id = dp.principal_id
LEFT JOIN   sys.database_principals      r   ON r.principal_id          = drm.role_principal_id
WHERE   dp.name = 'lucidpm_app';

/* also confirm which database you just ran in */
SELECT DB_NAME() AS ran_in_database;

/* ---------------------------------------------------------------------------
   To roll back in a database:
       ALTER ROLE db_datawriter DROP MEMBER [lucidpm_app];
       ALTER ROLE db_datareader DROP MEMBER [lucidpm_app];
       DROP USER [lucidpm_app];
   --------------------------------------------------------------------------- */
