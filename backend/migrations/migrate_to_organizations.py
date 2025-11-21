"""
Migration script to transform DocuFlow into a multi-tenant SaaS application.

This script:
1. Creates new tables (organizations, organization_settings, usage_logs, subscriptions)
2. Adds columns to existing tables (users, batches)
3. Migrates existing users to the organization model
4. Migrates connector configs to organization-level settings

Run this script ONCE after deploying the new code.

Usage:
    python backend/migrations/migrate_to_organizations.py
"""

import sys
import asyncio
import aiosqlite
from pathlib import Path
from datetime import datetime, date
import json

# Add parent directory to path to import from backend
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.database import DB_PATH

# Read the SQL migration file
MIGRATION_SQL_PATH = Path(__file__).parent / "001_add_organizations.sql"


async def check_column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = await cursor.fetchall()
    column_names = [col[1] for col in columns]
    return column in column_names


async def run_migration():
    """Run the complete migration."""
    print("=" * 80)
    print("DocuFlow Multi-Tenant Migration")
    print("=" * 80)
    print()

    # Connect to database
    print(f"Connecting to database: {DB_PATH}")
    async with aiosqlite.connect(DB_PATH) as db:
        # Enable foreign keys
        await db.execute("PRAGMA foreign_keys = ON")
        print("✓ Connected to database")
        print()

        # ========================================================================
        # STEP 1: Create new tables from SQL file
        # ========================================================================
        print("[1/6] Creating new tables...")

        with open(MIGRATION_SQL_PATH, 'r') as f:
            sql_script = f.read()

        # Execute the SQL migration
        await db.executescript(sql_script)
        print("✓ Created organizations table")
        print("✓ Created organization_settings table")
        print("✓ Created usage_logs table")
        print("✓ Created subscriptions table")
        print()

        # ========================================================================
        # STEP 2: Add columns to existing tables
        # ========================================================================
        print("[2/6] Updating existing tables...")

        # Add organization_id to users table
        if not await check_column_exists(db, "users", "organization_id"):
            await db.execute("ALTER TABLE users ADD COLUMN organization_id INTEGER REFERENCES organizations(id)")
            print("✓ Added organization_id column to users table")
        else:
            print("  - organization_id column already exists in users table")

        # Add role to users table
        if not await check_column_exists(db, "users", "role"):
            await db.execute("ALTER TABLE users ADD COLUMN role TEXT DEFAULT 'member'")
            print("✓ Added role column to users table")
        else:
            print("  - role column already exists in users table")

        # Add organization_id to batches table
        if not await check_column_exists(db, "batches", "organization_id"):
            await db.execute("ALTER TABLE batches ADD COLUMN organization_id INTEGER REFERENCES organizations(id)")
            print("✓ Added organization_id column to batches table")
        else:
            print("  - organization_id column already exists in batches table")

        await db.commit()
        print()

        # ========================================================================
        # STEP 3: Get existing users
        # ========================================================================
        print("[3/6] Checking existing users...")
        cursor = await db.execute("SELECT id, email, name, created_at FROM users WHERE organization_id IS NULL")
        existing_users = await cursor.fetchall()

        if not existing_users:
            print("  - No existing users found (or all users already migrated)")
            print()
        else:
            print(f"  Found {len(existing_users)} users to migrate")
            print()

            # ====================================================================
            # STEP 4: Create organizations for existing users
            # ====================================================================
            print("[4/6] Creating organizations for existing users...")

            user_org_mapping = {}  # user_id -> org_id

            for user_row in existing_users:
                user_id, email, name, created_at = user_row

                # Create organization name from email or name
                if name:
                    org_name = f"{name}'s Organization"
                else:
                    org_name = f"{email.split('@')[0]}'s Organization"

                # Create organization
                cursor = await db.execute(
                    """INSERT INTO organizations
                       (name, created_at, subscription_plan, billing_email, status)
                       VALUES (?, ?, ?, ?, ?)""",
                    (org_name, created_at, 'trial', email, 'active')
                )
                org_id = cursor.lastrowid
                user_org_mapping[user_id] = org_id

                # Update user with organization_id and set as owner
                await db.execute(
                    "UPDATE users SET organization_id = ?, role = ? WHERE id = ?",
                    (org_id, 'owner', user_id)
                )

                print(f"  ✓ Created organization '{org_name}' (ID: {org_id}) for user {email}")

            await db.commit()
            print()

            # ====================================================================
            # STEP 5: Migrate connector configs to organization settings
            # ====================================================================
            print("[5/6] Migrating connector configurations...")

            # Get all active connector configs
            cursor = await db.execute(
                """SELECT id, user_id, connector_type, config_json, created_at, updated_at
                   FROM connector_configs WHERE is_active = TRUE"""
            )
            connector_configs = await cursor.fetchall()

            if not connector_configs:
                print("  - No connector configurations to migrate")
            else:
                print(f"  Found {len(connector_configs)} connector configs to migrate")

                for config_row in connector_configs:
                    config_id, user_id, connector_type, config_json, created_at, updated_at = config_row

                    # Get organization for this user
                    org_id = user_org_mapping.get(user_id)
                    if not org_id:
                        # User already had organization, fetch it
                        cursor = await db.execute(
                            "SELECT organization_id FROM users WHERE id = ?",
                            (user_id,)
                        )
                        row = await cursor.fetchone()
                        if row:
                            org_id = row[0]

                    if org_id:
                        # Check if organization already has this connector type
                        cursor = await db.execute(
                            "SELECT id FROM organization_settings WHERE organization_id = ? AND connector_type = ?",
                            (org_id, connector_type)
                        )
                        existing = await cursor.fetchone()

                        if not existing:
                            # Migrate to organization_settings
                            await db.execute(
                                """INSERT INTO organization_settings
                                   (organization_id, connector_type, config_encrypted, is_active,
                                    created_at, updated_at, created_by_user_id)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (org_id, connector_type, config_json, True, created_at, updated_at, user_id)
                            )
                            print(f"  ✓ Migrated {connector_type} config for organization {org_id}")
                        else:
                            print(f"  - Organization {org_id} already has {connector_type} config, skipping")

                await db.commit()

            print()

            # ====================================================================
            # STEP 6: Create default subscriptions
            # ====================================================================
            print("[6/6] Creating default subscriptions...")

            for user_id, org_id in user_org_mapping.items():
                # Check if subscription already exists
                cursor = await db.execute(
                    "SELECT id FROM subscriptions WHERE organization_id = ?",
                    (org_id,)
                )
                existing_sub = await cursor.fetchone()

                if not existing_sub:
                    # Create default per-document subscription
                    today = date.today()
                    await db.execute(
                        """INSERT INTO subscriptions
                           (organization_id, plan_type, price_per_document,
                            billing_cycle_start, current_period_start, current_period_end, status)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (org_id, 'per_document', 0.10, today, today, today, 'active')
                    )
                    print(f"  ✓ Created subscription for organization {org_id}")

            await db.commit()
            print()

        # ========================================================================
        # STEP 7: Update batches with organization_id
        # ========================================================================
        print("[7/7] Updating batches with organization IDs...")

        # Update batches to have organization_id from their user
        await db.execute(
            """UPDATE batches
               SET organization_id = (
                   SELECT organization_id FROM users WHERE users.id = batches.user_id
               )
               WHERE organization_id IS NULL"""
        )
        await db.commit()
        print("✓ Updated batches with organization IDs")
        print()

        # ========================================================================
        # SUMMARY
        # ========================================================================
        print("=" * 80)
        print("Migration Summary")
        print("=" * 80)

        # Count organizations
        cursor = await db.execute("SELECT COUNT(*) FROM organizations")
        org_count = (await cursor.fetchone())[0]
        print(f"Total organizations: {org_count}")

        # Count users
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        user_count = (await cursor.fetchone())[0]
        print(f"Total users: {user_count}")

        # Count organization settings
        cursor = await db.execute("SELECT COUNT(*) FROM organization_settings")
        settings_count = (await cursor.fetchone())[0]
        print(f"Total organization settings: {settings_count}")

        # Count subscriptions
        cursor = await db.execute("SELECT COUNT(*) FROM subscriptions")
        sub_count = (await cursor.fetchone())[0]
        print(f"Total subscriptions: {sub_count}")

        print()
        print("✅ Migration completed successfully!")
        print()
        print("Next steps:")
        print("1. Restart the backend server")
        print("2. Test user login and organization context")
        print("3. Verify connector settings are accessible")
        print("4. Monitor usage logs for billing data")
        print()


if __name__ == "__main__":
    import sys

    # Check for --yes flag to skip confirmation
    if '--yes' in sys.argv or '-y' in sys.argv:
        asyncio.run(run_migration())
    else:
        print()
        print("⚠️  WARNING: This migration will modify your database structure.")
        print("   Make sure you have a backup of your database before proceeding.")
        print()

        response = input("Do you want to continue? (yes/no): ")
        if response.lower() in ['yes', 'y']:
            asyncio.run(run_migration())
        else:
            print("Migration cancelled.")
