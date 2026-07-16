INSERT INTO dbo.SchemaChangeLog
(
    ScriptName,
    AppliedOn,
    AppliedBy,
    Notes
)
VALUES
(
    'lease_section_schema_cleanup_v2_8_6',
    SYSDATETIME(),
    SUSER_SNAME(),
    'v2.8.6 / v2.7.5 - Lease document cleanup complete. Migrated LeaseDocumentPieces to LeaseDocumentSections, standardized Section naming, removed legacy Piece compatibility, aligned Admin Lease Documents and Lease Package Builder modules, changed package template selection to ID-based binding, and confirmed deterministic template-section generation.'
);