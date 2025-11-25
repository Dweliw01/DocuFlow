#!/usr/bin/env python3
"""
SQLite to PostgreSQL Data Migration Script

This script migrates all data from SQLite (docuflow.db) to PostgreSQL.
It preserves all IDs and relationships.

Usage:
    # Set PostgreSQL URL
    export POSTGRES_URL="postgresql://docuflow:docuflow_dev_password@localhost:5432/docuflow"

    # Run migration
    python migrations/migrate_sqlite_to_postgres.py

    # Or with explicit paths
    python migrations/migrate_sqlite_to_postgres.py --sqlite ./docuflow.db --postgres postgresql://...

Prerequisites:
    1. PostgreSQL database must exist and be empty (or tables dropped)
    2. Run Alembic migrations first: alembic upgrade head
    3. SQLite database must have data to migrate
"""

import argparse
import sqlite3
import sys
import os
from pathlib import Path
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("Error: psycopg2 not installed. Run: pip install psycopg2-binary")
    sys.exit(1)


# Tables in dependency order (parent tables first)
TABLES_IN_ORDER = [
    'organizations',
    'users',
    'subscriptions',
    'batches',
    'connector_configs',
    'organization_settings',
    'usage_logs',
    'document_metadata',
    'field_mappings',
    'field_corrections',
]


def get_sqlite_connection(db_path: str) -> sqlite3.Connection:
    """Connect to SQLite database."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"SQLite database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def get_postgres_connection(postgres_url: str):
    """Connect to PostgreSQL database."""
    return psycopg2.connect(postgres_url)


def get_table_columns(sqlite_conn: sqlite3.Connection, table_name: str) -> list:
    """Get column names for a table."""
    cursor = sqlite_conn.execute(f"PRAGMA table_info({table_name})")
    return [row['name'] for row in cursor.fetchall()]


def get_table_data(sqlite_conn: sqlite3.Connection, table_name: str) -> list:
    """Get all rows from a table."""
    cursor = sqlite_conn.execute(f"SELECT * FROM {table_name}")
    return [dict(row) for row in cursor.fetchall()]


def migrate_table(
    sqlite_conn: sqlite3.Connection,
    pg_conn,
    table_name: str,
    dry_run: bool = False
) -> int:
    """Migrate a single table from SQLite to PostgreSQL."""

    # Get columns and data
    columns = get_table_columns(sqlite_conn, table_name)
    rows = get_table_data(sqlite_conn, table_name)

    if not rows:
        print(f"  {table_name}: 0 rows (empty)")
        return 0

    # Build INSERT statement
    col_names = ', '.join(columns)
    placeholders = ', '.join(['%s'] * len(columns))

    insert_sql = f"""
        INSERT INTO {table_name} ({col_names})
        VALUES ({placeholders})
        ON CONFLICT DO NOTHING
    """

    # Prepare data tuples
    data_tuples = []
    for row in rows:
        values = tuple(row.get(col) for col in columns)
        data_tuples.append(values)

    if dry_run:
        print(f"  {table_name}: {len(rows)} rows (dry run)")
        return len(rows)

    # Execute insert
    pg_cursor = pg_conn.cursor()
    try:
        for values in data_tuples:
            pg_cursor.execute(insert_sql, values)

        # Reset sequence for serial columns if table has 'id' column
        if 'id' in columns:
            reset_sequence_sql = f"""
                SELECT setval(
                    pg_get_serial_sequence('{table_name}', 'id'),
                    COALESCE((SELECT MAX(id) FROM {table_name}), 0) + 1,
                    false
                )
            """
            pg_cursor.execute(reset_sequence_sql)

        pg_conn.commit()
        print(f"  {table_name}: {len(rows)} rows migrated")
        return len(rows)

    except Exception as e:
        pg_conn.rollback()
        print(f"  {table_name}: ERROR - {e}")
        raise


def verify_migration(sqlite_conn: sqlite3.Connection, pg_conn, table_name: str) -> bool:
    """Verify row counts match between SQLite and PostgreSQL."""

    # SQLite count
    sqlite_cursor = sqlite_conn.execute(f"SELECT COUNT(*) FROM {table_name}")
    sqlite_count = sqlite_cursor.fetchone()[0]

    # PostgreSQL count
    pg_cursor = pg_conn.cursor()
    pg_cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    pg_count = pg_cursor.fetchone()[0]

    match = sqlite_count == pg_count
    status = "OK" if match else "MISMATCH"
    print(f"  {table_name}: SQLite={sqlite_count}, PostgreSQL={pg_count} [{status}]")

    return match


def clear_postgres_tables(pg_conn, tables: list):
    """Clear all data from PostgreSQL tables (in reverse order for FK constraints)."""
    pg_cursor = pg_conn.cursor()

    # Disable FK checks temporarily
    pg_cursor.execute("SET session_replication_role = 'replica';")

    for table in reversed(tables):
        try:
            pg_cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
            print(f"  Cleared: {table}")
        except Exception as e:
            print(f"  Warning: Could not clear {table}: {e}")

    # Re-enable FK checks
    pg_cursor.execute("SET session_replication_role = 'origin';")
    pg_conn.commit()


def main():
    parser = argparse.ArgumentParser(
        description="Migrate data from SQLite to PostgreSQL"
    )
    parser.add_argument(
        '--sqlite',
        default=str(Path(__file__).parent.parent / 'docuflow.db'),
        help='Path to SQLite database (default: backend/docuflow.db)'
    )
    parser.add_argument(
        '--postgres',
        default=os.getenv('POSTGRES_URL', os.getenv('DATABASE_URL', '')),
        help='PostgreSQL connection URL (default: $POSTGRES_URL or $DATABASE_URL)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be migrated without actually migrating'
    )
    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear PostgreSQL tables before migration'
    )
    parser.add_argument(
        '--verify-only',
        action='store_true',
        help='Only verify existing migration (no data transfer)'
    )

    args = parser.parse_args()

    # Validate PostgreSQL URL
    if not args.postgres or args.postgres.startswith('sqlite'):
        print("Error: PostgreSQL URL required.")
        print("Set POSTGRES_URL environment variable or use --postgres flag")
        print("Example: postgresql://user:password@localhost:5432/docuflow")
        sys.exit(1)

    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)
    print(f"SQLite:     {args.sqlite}")
    print(f"PostgreSQL: {args.postgres.split('@')[1] if '@' in args.postgres else args.postgres}")
    print(f"Dry Run:    {args.dry_run}")
    print("=" * 60)

    # Connect to databases
    print("\nConnecting to databases...")
    try:
        sqlite_conn = get_sqlite_connection(args.sqlite)
        print("  SQLite: Connected")
    except Exception as e:
        print(f"  SQLite: FAILED - {e}")
        sys.exit(1)

    try:
        pg_conn = get_postgres_connection(args.postgres)
        print("  PostgreSQL: Connected")
    except Exception as e:
        print(f"  PostgreSQL: FAILED - {e}")
        sys.exit(1)

    # Verify only mode
    if args.verify_only:
        print("\nVerifying migration...")
        all_match = True
        for table in TABLES_IN_ORDER:
            if not verify_migration(sqlite_conn, pg_conn, table):
                all_match = False

        print("\n" + "=" * 60)
        if all_match:
            print("Verification PASSED: All row counts match")
        else:
            print("Verification FAILED: Some tables have mismatched counts")
        sys.exit(0 if all_match else 1)

    # Clear tables if requested
    if args.clear and not args.dry_run:
        print("\nClearing PostgreSQL tables...")
        clear_postgres_tables(pg_conn, TABLES_IN_ORDER)

    # Migrate tables
    print("\nMigrating tables...")
    total_rows = 0
    start_time = datetime.now()

    for table in TABLES_IN_ORDER:
        try:
            rows = migrate_table(sqlite_conn, pg_conn, table, args.dry_run)
            total_rows += rows
        except Exception as e:
            print(f"\nMigration FAILED at table '{table}': {e}")
            sys.exit(1)

    elapsed = (datetime.now() - start_time).total_seconds()

    # Verify migration
    if not args.dry_run:
        print("\nVerifying migration...")
        all_match = True
        for table in TABLES_IN_ORDER:
            if not verify_migration(sqlite_conn, pg_conn, table):
                all_match = False

        print("\n" + "=" * 60)
        print(f"Migration {'COMPLETE' if all_match else 'COMPLETED WITH WARNINGS'}")
        print(f"Total rows: {total_rows}")
        print(f"Time: {elapsed:.2f} seconds")

        if not all_match:
            print("\nWarning: Some row counts don't match. Check for duplicates or constraints.")
    else:
        print("\n" + "=" * 60)
        print(f"Dry run complete. Would migrate {total_rows} rows.")

    # Close connections
    sqlite_conn.close()
    pg_conn.close()


if __name__ == '__main__':
    main()
