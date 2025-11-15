"""
Clear all users from database for fresh testing.
"""

import sys
import asyncio
import aiosqlite
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.database import DB_PATH


async def clear_users():
    """Clear all users."""
    print("=" * 80)
    print("DocuFlow User Reset")
    print("=" * 80)
    print()
    print("This will delete ALL users from the database.")
    print()

    async with aiosqlite.connect(DB_PATH) as db:
        # Get current state
        cursor = await db.execute("SELECT COUNT(*) FROM users")
        user_count = (await cursor.fetchone())[0]

        print(f"Found {user_count} users")
        print()

        # Delete all users
        await db.execute("DELETE FROM users")
        print("✓ Deleted all users")

        await db.commit()

        print()
        print("✅ Reset complete!")
        print()
        print("All Gmail accounts can now sign up fresh.")
        print()


if __name__ == "__main__":
    asyncio.run(clear_users())
