-- Multi-suite leases (Handoff 73). One row per suite a lease covers.
-- Leases.SuiteID is retained and must always equal the IsPrimary=1 row's SuiteID.
-- RentAllocationPct: share (0-100) of the lease's rent attributed to this suite
-- for per-suite views (Proforma). Rows for one lease sum to 100.
-- Run against TenantCRM_Test first. Verify. Then run against TenantCRM.

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;

IF OBJECT_ID('dbo.LeaseSuites', 'U') IS NULL
BEGIN
    CREATE TABLE dbo.LeaseSuites (
        LeaseSuiteID      INT IDENTITY(1,1) NOT NULL,
        LeaseID           INT NOT NULL,
        SuiteID           INT NOT NULL,
        IsPrimary         BIT NOT NULL CONSTRAINT DF_LeaseSuites_IsPrimary DEFAULT (0),
        RentAllocationPct DECIMAL(9,6) NOT NULL CONSTRAINT DF_LeaseSuites_Pct DEFAULT (100),
        CreatedDate       DATETIME NOT NULL CONSTRAINT DF_LeaseSuites_Created DEFAULT (GETDATE()),
        CONSTRAINT PK_LeaseSuites PRIMARY KEY CLUSTERED (LeaseSuiteID),
        CONSTRAINT FK_LeaseSuites_Leases FOREIGN KEY (LeaseID)
            REFERENCES dbo.Leases (LeaseID) ON DELETE CASCADE,
        CONSTRAINT FK_LeaseSuites_PropertySuites FOREIGN KEY (SuiteID)
            REFERENCES dbo.PropertySuites (SuiteID),
        CONSTRAINT CK_LeaseSuites_Pct CHECK (RentAllocationPct > 0 AND RentAllocationPct <= 100)
    );
END;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_LeaseSuites_Lease_Suite'
               AND object_id = OBJECT_ID('dbo.LeaseSuites'))
    CREATE UNIQUE INDEX UX_LeaseSuites_Lease_Suite ON dbo.LeaseSuites (LeaseID, SuiteID);

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'UX_LeaseSuites_OnePrimary'
               AND object_id = OBJECT_ID('dbo.LeaseSuites'))
    CREATE UNIQUE INDEX UX_LeaseSuites_OnePrimary ON dbo.LeaseSuites (LeaseID) WHERE IsPrimary = 1;

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_LeaseSuites_SuiteID'
               AND object_id = OBJECT_ID('dbo.LeaseSuites'))
    CREATE INDEX IX_LeaseSuites_SuiteID ON dbo.LeaseSuites (SuiteID) INCLUDE (LeaseID, RentAllocationPct);

-- Backfill: every lease with a SuiteID gets its primary row at 100%.
INSERT INTO dbo.LeaseSuites (LeaseID, SuiteID, IsPrimary, RentAllocationPct)
SELECT l.LeaseID, l.SuiteID, 1, 100
FROM dbo.Leases l
WHERE l.SuiteID IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM dbo.LeaseSuites x WHERE x.LeaseID = l.LeaseID);

-- Verification (run after each execution):
-- Expect count 0: every SuiteID'd lease has exactly one primary row matching it.
-- SELECT COUNT(*)
-- FROM dbo.Leases l
-- LEFT JOIN dbo.LeaseSuites ls ON ls.LeaseID = l.LeaseID AND ls.IsPrimary = 1
-- WHERE l.SuiteID IS NOT NULL AND (ls.SuiteID IS NULL OR ls.SuiteID <> l.SuiteID);

-- Expect no rows: allocations sum to exactly 100.
-- SELECT LeaseID
-- FROM dbo.LeaseSuites
-- GROUP BY LeaseID
-- HAVING SUM(RentAllocationPct) <> 100;

-- Expect no rows: no cross-property links and exactly one primary per linked lease.
-- SELECT ls.LeaseID
-- FROM dbo.LeaseSuites ls
-- JOIN dbo.Leases l ON l.LeaseID = ls.LeaseID
-- JOIN dbo.PropertySuites ps ON ps.SuiteID = ls.SuiteID
-- GROUP BY ls.LeaseID
-- HAVING SUM(CASE WHEN ps.PropertyID <> l.PropertyID THEN 1 ELSE 0 END) > 0
--     OR SUM(CAST(ls.IsPrimary AS INT)) <> 1;
