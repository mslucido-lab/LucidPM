"""
Generates db/baseline_schema.sql: a deterministic, from-scratch CREATE TABLE
snapshot of the live database's current schema.

This is a snapshot of "now," not a replay of history -- rerun it any time the
schema changes rather than hand-editing the output. See db/history/ for the
(incomplete) historical record of how the schema got here, and
db/history/CHANGELOG.md for the authoritative timeline from dbo.SchemaChangeLog.

Usage (from an activated .venv at the repo root):
    python db/generate_baseline_schema.py [DB_NAME]

Defaults to TEST_DB_NAME (TenantCRM_Test) if no argument is given.
"""

import sys
import datetime
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from LucidPM.state import get_conn, TEST_DB_NAME

SQL_TYPE_WITH_LENGTH = {"nvarchar", "varchar", "nchar", "char", "varbinary", "binary"}
SQL_TYPE_WITH_PRECISION = {"decimal", "numeric"}


def column_type_sql(col: dict) -> str:
    dtype = col["DATA_TYPE"]
    if dtype in SQL_TYPE_WITH_LENGTH:
        length = col["CHARACTER_MAXIMUM_LENGTH"]
        length_sql = "MAX" if length == -1 else str(length)
        return f"{dtype.upper()}({length_sql})"
    if dtype in SQL_TYPE_WITH_PRECISION:
        return f"{dtype.upper()}({col['NUMERIC_PRECISION']},{col['NUMERIC_SCALE']})"
    if dtype == "datetime2" and col["DATETIME_PRECISION"] is not None:
        return f"DATETIME2({col['DATETIME_PRECISION']})"
    return dtype.upper()


def build_create_table(cursor, table: str) -> str:
    cursor.execute(
        """
        SELECT c.COLUMN_NAME, c.DATA_TYPE, c.CHARACTER_MAXIMUM_LENGTH,
               c.NUMERIC_PRECISION, c.NUMERIC_SCALE, c.DATETIME_PRECISION,
               c.IS_NULLABLE, c.COLUMN_DEFAULT, c.ORDINAL_POSITION,
               COLUMNPROPERTY(OBJECT_ID(?), c.COLUMN_NAME, 'IsIdentity') AS IS_IDENTITY
        FROM INFORMATION_SCHEMA.COLUMNS c
        WHERE c.TABLE_SCHEMA = 'dbo' AND c.TABLE_NAME = ?
        ORDER BY c.ORDINAL_POSITION
        """,
        f"dbo.{table}",
        table,
    )
    cols = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]

    cursor.execute(
        """
        SELECT ic.COLUMN_NAME
        FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
        JOIN INFORMATION_SCHEMA.KEY_COLUMN_USAGE ic
          ON tc.CONSTRAINT_NAME = ic.CONSTRAINT_NAME AND tc.TABLE_NAME = ic.TABLE_NAME
        WHERE tc.TABLE_SCHEMA = 'dbo' AND tc.TABLE_NAME = ? AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        ORDER BY ic.ORDINAL_POSITION
        """,
        table,
    )
    pk_cols = [row[0] for row in cursor.fetchall()]

    lines = [f"CREATE TABLE dbo.[{table}] ("]
    col_defs = []
    for col in cols:
        parts = [f"    [{col['COLUMN_NAME']}]", column_type_sql(col)]
        if col["IS_IDENTITY"]:
            parts.append("IDENTITY(1,1)")
        parts.append("NULL" if col["IS_NULLABLE"] == "YES" else "NOT NULL")
        if col["COLUMN_DEFAULT"] is not None:
            parts.append(f"DEFAULT {col['COLUMN_DEFAULT']}")
        col_defs.append(" ".join(parts))
    if pk_cols:
        pk_list = ", ".join(f"[{c}]" for c in pk_cols)
        col_defs.append(f"    CONSTRAINT [PK_{table}] PRIMARY KEY CLUSTERED ({pk_list})")
    lines.append(",\n".join(col_defs))
    lines.append(");")
    return "\n".join(lines)


def build_foreign_keys(cursor) -> list[str]:
    cursor.execute(
        """
        SELECT
            fk.name AS FK_NAME,
            tp.name AS PARENT_TABLE,
            cp.name AS PARENT_COLUMN,
            tr.name AS REF_TABLE,
            cr.name AS REF_COLUMN
        FROM sys.foreign_keys fk
        JOIN sys.foreign_key_columns fkc ON fkc.constraint_object_id = fk.object_id
        JOIN sys.tables tp ON tp.object_id = fkc.parent_object_id
        JOIN sys.columns cp ON cp.object_id = fkc.parent_object_id AND cp.column_id = fkc.parent_column_id
        JOIN sys.tables tr ON tr.object_id = fkc.referenced_object_id
        JOIN sys.columns cr ON cr.object_id = fkc.referenced_object_id AND cr.column_id = fkc.referenced_column_id
        ORDER BY tp.name, fk.name
        """
    )
    rows = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
    return [
        f"ALTER TABLE dbo.[{r['PARENT_TABLE']}] ADD CONSTRAINT [{r['FK_NAME']}] "
        f"FOREIGN KEY ([{r['PARENT_COLUMN']}]) REFERENCES dbo.[{r['REF_TABLE']}] ([{r['REF_COLUMN']}]);"
        for r in rows
    ]


def build_indexes(cursor) -> list[str]:
    cursor.execute(
        """
        SELECT t.name AS TABLE_NAME, i.name AS INDEX_NAME, i.is_unique,
               c.name AS COLUMN_NAME, ic.key_ordinal
        FROM sys.indexes i
        JOIN sys.tables t ON t.object_id = i.object_id
        JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
        JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
        WHERE i.is_primary_key = 0 AND i.is_unique_constraint = 0 AND i.name IS NOT NULL
        ORDER BY t.name, i.name, ic.key_ordinal
        """
    )
    rows = [dict(zip([d[0] for d in cursor.description], row)) for row in cursor.fetchall()]
    by_index: dict[tuple, dict] = {}
    for r in rows:
        key = (r["TABLE_NAME"], r["INDEX_NAME"])
        by_index.setdefault(key, {"unique": r["is_unique"], "cols": []})
        by_index[key]["cols"].append(r["COLUMN_NAME"])
    stmts = []
    for (table, idx_name), info in by_index.items():
        unique_sql = "UNIQUE " if info["unique"] else ""
        col_list = ", ".join(f"[{c}]" for c in info["cols"])
        stmts.append(
            f"CREATE {unique_sql}INDEX [{idx_name}] ON dbo.[{table}] ({col_list});"
        )
    return stmts


def main():
    db_name = sys.argv[1] if len(sys.argv) > 1 else TEST_DB_NAME
    conn = get_conn(db_name)
    cursor = conn.cursor()

    cursor.execute(
        "SELECT name FROM sys.tables ORDER BY name"
    )
    tables = [row[0] for row in cursor.fetchall()]

    out = [
        "-- Generated baseline schema snapshot.",
        f"-- Source database: {db_name}",
        f"-- Generated: {datetime.datetime.now().isoformat(timespec='seconds')}",
        "-- Regenerate with: python db/generate_baseline_schema.py",
        "-- This is a snapshot of the live schema at generation time, NOT a replay",
        "-- of history -- see db/history/CHANGELOG.md for that.",
        "",
        "-- ============================================================",
        "-- Tables",
        "-- ============================================================",
        "",
    ]

    for table in tables:
        out.append(build_create_table(cursor, table))
        out.append("")

    fk_stmts = build_foreign_keys(cursor)
    out.append("-- ============================================================")
    out.append("-- Foreign keys")
    out.append("-- ============================================================")
    out.append("")
    out.extend(fk_stmts)
    out.append("")

    index_stmts = build_indexes(cursor)
    out.append("-- ============================================================")
    out.append("-- Indexes")
    out.append("-- ============================================================")
    out.append("")
    out.extend(index_stmts)
    out.append("")

    conn.close()

    out_path = pathlib.Path(__file__).resolve().parent / "baseline_schema.sql"
    out_path.write_text("\n".join(out), encoding="utf-8")
    print(f"Wrote {out_path} ({len(tables)} tables, {len(fk_stmts)} FKs, {len(index_stmts)} indexes)")


if __name__ == "__main__":
    main()
