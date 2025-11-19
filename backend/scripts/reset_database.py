"""
Database Reset Script for DocuFlow

Provides options to clear different parts of the database for fresh starts.
Creates automatic backups before any destructive operations.
"""

import sqlite3
import os
import shutil
from datetime import datetime
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent.parent.parent / "docuflow.db"


def create_backup():
    """Create a backup of the database before clearing"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / f"docuflow.db.backup_{timestamp}"

    print(f"\n[BACKUP] Creating backup at: {backup_path}")
    shutil.copy2(DB_PATH, backup_path)
    print(f"[OK] Backup created successfully")
    return backup_path


def clear_all_data(conn):
    """NUCLEAR OPTION: Clear ALL data from database (keeps structure)"""
    cursor = conn.cursor()

    tables = [
        'field_corrections',
        'document_metadata',
        'batches',
        'field_mappings',
        'connector_configs',
        'organization_settings',
        'usage_logs',
        'subscriptions',
        'users',
        'organizations'
    ]

    print("\n[WARNING] Clearing ALL data from database...")
    for table in tables:
        try:
            cursor.execute(f"DELETE FROM {table}")
            count = cursor.rowcount
            print(f"  - Cleared {count} rows from {table}")
        except sqlite3.Error as e:
            print(f"  - Error clearing {table}: {e}")

    conn.commit()
    print("\n[OK] All data cleared!")


def clear_documents_only(conn):
    """Clear only documents and batches (keep users, orgs, configs)"""
    cursor = conn.cursor()

    print("\n[INFO] Clearing documents and batches...")

    # Clear field corrections first (foreign key constraint)
    cursor.execute("DELETE FROM field_corrections")
    corrections_count = cursor.rowcount
    print(f"  - Cleared {corrections_count} field corrections")

    # Clear documents
    cursor.execute("DELETE FROM document_metadata")
    docs_count = cursor.rowcount
    print(f"  - Cleared {docs_count} documents")

    # Clear batches
    cursor.execute("DELETE FROM batches")
    batches_count = cursor.rowcount
    print(f"  - Cleared {batches_count} batches")

    conn.commit()
    print("\n[OK] Documents and batches cleared!")
    print(f"[INFO] Kept: users, organizations, connector configs")


def clear_completed_documents_only(conn):
    """Clear only completed/uploaded documents (keep pending review)"""
    cursor = conn.cursor()

    print("\n[INFO] Clearing only completed documents...")

    # Get document IDs to delete
    cursor.execute("""
        SELECT id FROM document_metadata
        WHERE status IN ('completed', 'uploaded', 'failed')
    """)
    doc_ids = [row[0] for row in cursor.fetchall()]

    if not doc_ids:
        print("[INFO] No completed documents to clear")
        return

    # Clear corrections for these documents
    placeholders = ','.join('?' * len(doc_ids))
    cursor.execute(f"""
        DELETE FROM field_corrections
        WHERE document_id IN ({placeholders})
    """, doc_ids)
    corrections_count = cursor.rowcount
    print(f"  - Cleared {corrections_count} field corrections")

    # Clear completed documents
    cursor.execute(f"""
        DELETE FROM document_metadata
        WHERE id IN ({placeholders})
    """, doc_ids)
    docs_count = cursor.rowcount
    print(f"  - Cleared {docs_count} completed documents")

    conn.commit()
    print("\n[OK] Completed documents cleared!")
    print(f"[INFO] Kept: pending review documents, users, organizations, configs")


def clear_storage_files(storage_path):
    """Clear uploaded and processed files from storage directories"""
    print("\n[INFO] Clearing storage files...")

    # Clear uploads
    uploads_path = storage_path / "uploads"
    if uploads_path.exists():
        count = 0
        for item in uploads_path.iterdir():
            if item.name not in ['.gitkeep', '.gitignore']:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                count += 1
        print(f"  - Cleared {count} items from uploads/")

    # Clear processed
    processed_path = storage_path / "processed"
    if processed_path.exists():
        count = 0
        for item in processed_path.iterdir():
            if item.name not in ['.gitkeep', '.gitignore']:
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
                count += 1
        print(f"  - Cleared {count} items from processed/")

    print("[OK] Storage files cleared!")


def show_database_stats(conn):
    """Show current database statistics"""
    cursor = conn.cursor()

    print("\n" + "=" * 60)
    print("CURRENT DATABASE STATISTICS")
    print("=" * 60)

    tables = {
        'organizations': 'Organizations',
        'users': 'Users',
        'organization_settings': 'Connector Configs',
        'document_metadata': 'Documents',
        'field_corrections': 'Field Corrections',
        'batches': 'Batches'
    }

    for table, label in tables.items():
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"  {label:.<30} {count:>5} rows")
        except sqlite3.Error:
            print(f"  {label:.<30} [ERROR]")

    # Show pending review count
    try:
        cursor.execute("SELECT COUNT(*) FROM document_metadata WHERE status = 'pending_review'")
        pending = cursor.fetchone()[0]
        print(f"  {'  - Pending Review':.<30} {pending:>5} docs")
    except sqlite3.Error:
        pass

    print("=" * 60)


def main():
    """Main interactive menu"""
    print("=" * 60)
    print("DocuFlow Database Reset Tool")
    print("=" * 60)

    if not DB_PATH.exists():
        print(f"\n[ERROR] Database not found at: {DB_PATH}")
        return

    # Connect to database
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Show current stats
    show_database_stats(conn)

    # Show menu
    print("\n" + "=" * 60)
    print("RESET OPTIONS")
    print("=" * 60)
    print("1. Clear ALL data (nuclear option - clears everything)")
    print("2. Clear documents and batches only (keep users/orgs/configs)")
    print("3. Clear completed documents only (keep pending review)")
    print("4. Clear storage files only (keep database)")
    print("5. Clear documents + storage files")
    print("6. Show database statistics")
    print("0. Exit")
    print("=" * 60)

    choice = input("\nEnter your choice (0-6): ").strip()

    if choice == '0':
        print("\n[INFO] Exiting without changes")
        conn.close()
        return

    if choice == '6':
        show_database_stats(conn)
        conn.close()
        return

    # Confirm action
    print("\n" + "!" * 60)
    print("WARNING: This action will modify/delete data!")
    print("!" * 60)
    confirm = input("\nType 'YES' to confirm (or anything else to cancel): ").strip()

    if confirm != 'YES':
        print("\n[INFO] Operation cancelled")
        conn.close()
        return

    # Create backup
    backup_path = create_backup()
    print(f"[INFO] Backup saved to: {backup_path}")

    # Execute chosen action
    try:
        if choice == '1':
            clear_all_data(conn)
            storage_path = DB_PATH.parent / "backend" / "storage"
            clear_storage_files(storage_path)

        elif choice == '2':
            clear_documents_only(conn)

        elif choice == '3':
            clear_completed_documents_only(conn)

        elif choice == '4':
            storage_path = DB_PATH.parent / "backend" / "storage"
            clear_storage_files(storage_path)

        elif choice == '5':
            clear_documents_only(conn)
            storage_path = DB_PATH.parent / "backend" / "storage"
            clear_storage_files(storage_path)

        else:
            print("\n[ERROR] Invalid choice")
            conn.close()
            return

        # Show new stats
        show_database_stats(conn)

        print("\n" + "=" * 60)
        print("[SUCCESS] Database reset completed!")
        print("=" * 60)
        print(f"\nBackup available at: {backup_path}")
        print("\nYou can now start fresh with a clean database.")

    except Exception as e:
        print(f"\n[ERROR] Operation failed: {e}")
        print(f"[INFO] Database backup available at: {backup_path}")
        conn.rollback()

    finally:
        conn.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[INFO] Operation cancelled by user")
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
