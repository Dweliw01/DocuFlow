"""
Database migration: Add Review Workflow Support

Adds:
- status and confidence_score columns to document_metadata
- field_corrections table for tracking user corrections
- review settings columns to organizations table
"""

import sqlite3
import os
from datetime import datetime

def run_migration():
    """Run the review workflow migration"""

    # Get database path
    db_path = os.path.join(os.path.dirname(__file__), '..', '..', 'docuflow.db')

    print(f"Running migration on database: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Create document_metadata table
        print("\n1. Creating document_metadata table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS document_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                batch_id TEXT,
                filename TEXT NOT NULL,
                file_path TEXT NOT NULL,
                category TEXT,
                extracted_data TEXT,
                status TEXT DEFAULT 'pending_review',
                confidence_score REAL DEFAULT 0.0,
                connector_type TEXT,
                uploaded_to_connector BOOLEAN DEFAULT 0,
                connector_result TEXT,
                error_message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                processed_at TIMESTAMP,
                approved_at TIMESTAMP,

                FOREIGN KEY (organization_id) REFERENCES organizations(id)
            )
        """)
        print("   ✓ Created document_metadata table")

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_document_status
            ON document_metadata(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_document_org_status
            ON document_metadata(organization_id, status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_document_batch
            ON document_metadata(batch_id)
        """)
        print("   ✓ Created indexes on document_metadata")

        # 2. Create field_corrections table
        print("\n2. Creating field_corrections table...")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS field_corrections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                organization_id INTEGER NOT NULL,
                document_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                original_value TEXT,
                corrected_value TEXT NOT NULL,
                original_confidence REAL,
                correction_method TEXT DEFAULT 'manual',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,

                FOREIGN KEY (organization_id) REFERENCES organizations(id),
                FOREIGN KEY (document_id) REFERENCES document_metadata(id) ON DELETE CASCADE
            )
        """)
        print("   ✓ Created field_corrections table")

        # Create indexes
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_corrections_doc
            ON field_corrections(document_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_corrections_org
            ON field_corrections(organization_id)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_corrections_field
            ON field_corrections(field_name)
        """)
        print("   ✓ Created indexes on field_corrections")

        # 3. Add review settings to organizations table
        print("\n3. Adding review settings to organizations table...")

        cursor.execute("PRAGMA table_info(organizations)")
        org_columns = [col[1] for col in cursor.fetchall()]

        if 'review_mode' not in org_columns:
            cursor.execute("""
                ALTER TABLE organizations
                ADD COLUMN review_mode TEXT DEFAULT 'review_all'
            """)
            print("   ✓ Added 'review_mode' column")
        else:
            print("   - 'review_mode' column already exists")

        if 'confidence_threshold' not in org_columns:
            cursor.execute("""
                ALTER TABLE organizations
                ADD COLUMN confidence_threshold REAL DEFAULT 0.90
            """)
            print("   ✓ Added 'confidence_threshold' column")
        else:
            print("   - 'confidence_threshold' column already exists")

        if 'auto_upload_enabled' not in org_columns:
            cursor.execute("""
                ALTER TABLE organizations
                ADD COLUMN auto_upload_enabled BOOLEAN DEFAULT 0
            """)
            print("   ✓ Added 'auto_upload_enabled' column")
        else:
            print("   - 'auto_upload_enabled' column already exists")

        # Commit changes
        conn.commit()

        print("\n[SUCCESS] Migration completed successfully!")
        print("\nSummary:")
        print("- document_metadata: Table created with status, confidence_score columns")
        print("- field_corrections: Table created with indexes")
        print("- organizations: Added review_mode, confidence_threshold, auto_upload_enabled")

    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Migration failed: {e}")
        raise

    finally:
        conn.close()


if __name__ == '__main__':
    print("=" * 60)
    print("DocuFlow - Review Workflow Migration")
    print("=" * 60)

    run_migration()

    print("\n" + "=" * 60)
    print("Migration completed at:", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    print("=" * 60)
