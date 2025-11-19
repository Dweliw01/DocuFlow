"""
Quick Database Reset - Clear documents and start fresh

This is a simplified version that clears documents and storage files
while keeping your user accounts, organizations, and connector configs.

Perfect for: Starting fresh with document processing while keeping your setup.
"""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path

# Paths
DB_PATH = Path(__file__).parent.parent.parent / "docuflow.db"
STORAGE_PATH = Path(__file__).parent.parent / "storage"


def quick_reset():
    """Quick reset: Clear documents and storage files"""

    print("\n" + "=" * 60)
    print("DocuFlow Quick Reset")
    print("=" * 60)
    print("\nThis will:")
    print("  ✓ Clear all documents and batches")
    print("  ✓ Clear all field corrections")
    print("  ✓ Clear uploaded files")
    print("  ✓ Clear processed files")
    print("\nThis will KEEP:")
    print("  ✓ User accounts")
    print("  ✓ Organizations")
    print("  ✓ Connector configurations")
    print("=" * 60)

    confirm = input("\nType 'YES' to proceed: ").strip()

    if confirm != 'YES':
        print("\n[CANCELLED] No changes made")
        return

    # Create backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / f"docuflow.db.backup_{timestamp}"
    print(f"\n[BACKUP] Creating backup...")
    shutil.copy2(DB_PATH, backup_path)
    print(f"[OK] Backup: {backup_path}")

    # Connect to database
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    try:
        print("\n[CLEARING] Database records...")

        # Clear field corrections
        cursor.execute("DELETE FROM field_corrections")
        corrections = cursor.rowcount

        # Clear documents
        cursor.execute("DELETE FROM document_metadata")
        documents = cursor.rowcount

        # Clear batches
        cursor.execute("DELETE FROM batches")
        batches = cursor.rowcount

        conn.commit()

        print(f"  ✓ Cleared {corrections} field corrections")
        print(f"  ✓ Cleared {documents} documents")
        print(f"  ✓ Cleared {batches} batches")

        # Clear storage files
        print("\n[CLEARING] Storage files...")

        # Clear uploads
        uploads_path = STORAGE_PATH / "uploads"
        if uploads_path.exists():
            count = 0
            for item in uploads_path.iterdir():
                if item.name not in ['.gitkeep', '.gitignore']:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    count += 1
            print(f"  ✓ Cleared {count} items from uploads/")

        # Clear processed
        processed_path = STORAGE_PATH / "processed"
        if processed_path.exists():
            count = 0
            for item in processed_path.iterdir():
                if item.name not in ['.gitkeep', '.gitignore']:
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                    count += 1
            print(f"  ✓ Cleared {count} items from processed/")

        print("\n" + "=" * 60)
        print("[SUCCESS] Database reset complete!")
        print("=" * 60)
        print("\nYou can now start processing documents with a clean slate.")
        print(f"Backup saved to: {backup_path.name}")

    except Exception as e:
        print(f"\n[ERROR] Reset failed: {e}")
        conn.rollback()
        raise

    finally:
        conn.close()


if __name__ == '__main__':
    try:
        quick_reset()
    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Interrupted by user")
    except Exception as e:
        print(f"\n[ERROR] {e}")
