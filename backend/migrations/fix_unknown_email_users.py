"""
Fix users with unknown@example.com email.
This cleans up users created due to missing email in OAuth tokens.
"""

import sys
import asyncio
import aiosqlite
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.database import DB_PATH


async def fix_unknown_users():
    """Delete users with unknown@example.com email."""
    print("=" * 80)
    print("DocuFlow - Fix Unknown Email Users")
    print("=" * 80)
    print()
    print("This will DELETE all users with 'unknown@example.com' email.")
    print("These are invalid users created due to OAuth token missing email.")
    print()

    async with aiosqlite.connect(DB_PATH) as db:
        # Get count of unknown users
        cursor = await db.execute(
            "SELECT COUNT(*) FROM users WHERE email = 'unknown@example.com'"
        )
        count = (await cursor.fetchone())[0]

        print(f"Found {count} users with unknown@example.com")
        print()

        if count == 0:
            print("✅ No unknown users to clean up!")
            return

        # Get their details
        cursor = await db.execute(
            """SELECT id, auth0_user_id, name, organization_id, created_at
               FROM users WHERE email = 'unknown@example.com'"""
        )
        users = await cursor.fetchall()

        print("Users to be deleted:")
        for user in users:
            print(f"  - ID: {user[0]}, Auth0: {user[1]}, Name: {user[2]}, Org: {user[3]}, Created: {user[4]}")
        print()

        # Delete unknown users
        await db.execute("DELETE FROM users WHERE email = 'unknown@example.com'")
        await db.commit()

        print(f"✓ Deleted {count} invalid users")
        print()
        print("✅ Cleanup complete!")
        print()
        print("Next steps:")
        print("1. Restart your backend server")
        print("2. Clear browser localStorage: localStorage.clear()")
        print("3. Log in again - email will now be fetched from Auth0")
        print("4. Each Google account will create a separate user")
        print()


if __name__ == "__main__":
    asyncio.run(fix_unknown_users())
