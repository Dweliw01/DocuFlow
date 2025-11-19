"""
Database migration: Add Connector Config Snapshot

Adds connector_config_snapshot column to document_metadata table
to preserve the exact connector configuration used when processing each document.

This ensures that when viewing old documents, they display the fields
that were relevant at processing time, not the current active connector config.
"""

import sqlite3
import os
from datetime import datetime

def run_migration():
    """Add connector_config_snapshot column to document_metadata"""

    # Get database path
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docuflow.db')

    print(f"Running migration on database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        print("\n1. Adding connector_config_snapshot column to document_metadata...")

        # Check if column already exists
        cursor.execute("PRAGMA table_info(document_metadata)")
        columns = [col[1] for col in cursor.fetchall()]

        if 'connector_config_snapshot' not in columns:
            cursor.execute("""
                ALTER TABLE document_metadata
                ADD COLUMN connector_config_snapshot TEXT
            """)
            print("   [OK] Added 'connector_config_snapshot' column")
        else:
            print("   - 'connector_config_snapshot' column already exists")

        # Commit changes
        conn.commit()

        print("\n[SUCCESS] Migration completed successfully!")
        print("\nSummary:")
        print("- document_metadata: Added connector_config_snapshot column")
        print("- This column stores the full connector config used during document processing")
        print("- Ensures documents always display with their original processing configuration")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 60)
    print("DocuFlow - Connector Config Snapshot Migration")
    print("=" * 60)

    run_migration()

    print("\n" + "=" * 60)
    print("Migration completed at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
