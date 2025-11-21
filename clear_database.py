"""
Database Clearing Script for DocuFlow
Clears all data from all tables while preserving the schema.
Useful for testing and development.
"""
import asyncio
import aiosqlite
from pathlib import Path

# Database file path
DB_PATH = Path(__file__).parent / "docuflow.db"


async def clear_all_data():
    """
    Clear all data from all tables in the database.
    Deletes in the correct order to respect foreign key constraints.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable foreign keys to ensure constraints are respected
        await db.execute("PRAGMA foreign_keys = ON")

        print("Starting database cleanup...")
        print(f"Database: {DB_PATH}")
        print("-" * 50)

        # Delete in order: child tables first, parent tables last
        tables_to_clear = [
            "field_mappings",           # Depends on connector_configs
            "connector_configs",        # Depends on users
            "batches",                  # Depends on users and organizations
            "organization_settings",    # Depends on organizations and users
            "usage_logs",               # Depends on organizations and users
            "subscriptions",            # Depends on organizations
            "users",                    # Depends on organizations
            "organizations"             # Parent table
        ]

        total_deleted = 0

        for table in tables_to_clear:
            # Count records before deletion
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
            count = (await cursor.fetchone())[0]

            if count > 0:
                # Delete all records
                await db.execute(f"DELETE FROM {table}")
                print(f"✓ Cleared {count:4d} records from {table}")
                total_deleted += count
            else:
                print(f"  {table} was already empty")

        # Commit all changes
        await db.commit()

        # Reset auto-increment counters (optional but recommended for clean testing)
        print("-" * 50)
        print("Resetting auto-increment counters...")
        await db.execute("DELETE FROM sqlite_sequence")
        await db.commit()

        print("-" * 50)
        print(f"✓ Database cleared successfully!")
        print(f"Total records deleted: {total_deleted}")
        print(f"All tables are now empty and ready for testing.")


async def verify_empty():
    """
    Verify that all tables are empty after clearing.
    """
    async with aiosqlite.connect(DB_PATH) as db:
        tables = [
            "organizations", "users", "batches", "organization_settings",
            "usage_logs", "subscriptions", "connector_configs", "field_mappings"
        ]

        print("\nVerifying database is empty...")
        print("-" * 50)

        all_empty = True
        for table in tables:
            cursor = await db.execute(f"SELECT COUNT(*) FROM {table}")
            count = (await cursor.fetchone())[0]

            if count == 0:
                print(f"✓ {table}: 0 records")
            else:
                print(f"✗ {table}: {count} records (NOT EMPTY!)")
                all_empty = False

        print("-" * 50)
        if all_empty:
            print("✓ All tables are empty!")
        else:
            print("✗ Some tables still have data!")

        return all_empty


async def main():
    """Main execution function."""
    print("=" * 50)
    print("DocuFlow Database Clearing Script")
    print("=" * 50)
    print()

    # Confirm before proceeding
    response = input("⚠️  This will DELETE ALL DATA from the database. Continue? (yes/no): ")

    if response.lower() not in ['yes', 'y']:
        print("Operation cancelled.")
        return

    print()

    # Clear all data
    await clear_all_data()

    # Verify it worked
    print()
    await verify_empty()

    print()
    print("=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
