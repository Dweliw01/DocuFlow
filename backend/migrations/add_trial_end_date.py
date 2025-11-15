"""
Add trial_end_date column to subscriptions table.
This enables tracking of when trial subscriptions expire.
"""

import sys
import asyncio
import aiosqlite
from pathlib import Path

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from backend.database import DB_PATH


async def add_trial_end_date_column():
    """Add trial_end_date column to subscriptions table."""
    print("=" * 80)
    print("DocuFlow - Add trial_end_date Column Migration")
    print("=" * 80)
    print()

    async with aiosqlite.connect(DB_PATH) as db:
        # Check if column already exists
        cursor = await db.execute("PRAGMA table_info(subscriptions)")
        columns = await cursor.fetchall()
        column_names = [col[1] for col in columns]

        if "trial_end_date" in column_names:
            print("✓ Column 'trial_end_date' already exists in subscriptions table")
            return

        print("Adding 'trial_end_date' column to subscriptions table...")

        # Add the column
        await db.execute("""
            ALTER TABLE subscriptions
            ADD COLUMN trial_end_date TIMESTAMP
        """)

        await db.commit()

        print("✓ Added trial_end_date column")
        print()
        print("=" * 80)
        print("Migration complete!")
        print("=" * 80)


if __name__ == "__main__":
    asyncio.run(add_trial_end_date_column())
