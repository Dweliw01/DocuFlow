"""
Reset organization for testing onboarding flow.
This script removes organization_id from users and deletes organizations.
"""

import sys
import asyncio
import aiosqlite
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.database import DB_PATH


async def reset_organization():
    """Reset organization data."""
    print("=" * 80)
    print("DocuFlow Organization Reset")
    print("=" * 80)
    print()
    print("This will:")
    print("  - Remove organization_id from all users")
    print("  - Delete all organizations")
    print("  - Delete all organization_settings")
    print("  - Delete all subscriptions")
    print("  - Delete all usage_logs")
    print()
    print("Users will be redirected to onboarding on next login.")
    print()

    async with aiosqlite.connect(DB_PATH) as db:
        # Get current state
        cursor = await db.execute("SELECT COUNT(*) FROM organizations")
        org_count = (await cursor.fetchone())[0]

        cursor = await db.execute("SELECT COUNT(*) FROM users WHERE organization_id IS NOT NULL")
        user_count = (await cursor.fetchone())[0]

        print(f"Found {org_count} organizations and {user_count} users with organizations")
        print()

        # Reset users
        await db.execute("UPDATE users SET organization_id = NULL, role = 'member'")
        print("✓ Removed organization_id from all users")

        # Delete organizations (cascade will delete settings, subscriptions, usage_logs)
        await db.execute("DELETE FROM organizations")
        print("✓ Deleted all organizations")

        await db.execute("DELETE FROM organization_settings")
        print("✓ Deleted all organization settings")

        await db.execute("DELETE FROM subscriptions")
        print("✓ Deleted all subscriptions")

        await db.execute("DELETE FROM usage_logs")
        print("✓ Deleted all usage logs")

        await db.commit()

        print()
        print("✅ Reset complete!")
        print()
        print("Next steps:")
        print("1. Clear your browser's localStorage (or use incognito mode)")
        print("2. Log in to DocuFlow")
        print("3. You'll be redirected to the onboarding flow")
        print()


if __name__ == "__main__":
    asyncio.run(reset_organization())
