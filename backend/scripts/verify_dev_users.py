"""
Dev DB Utility: Verify Existing Users
Marks all existing users in the database as email-verified so developers are not locked out.

Usage:
    python backend/scripts/verify_dev_users.py [--email user@example.com]
"""
import asyncio
import os
import sys
import argparse

# Ensure backend root is on sys.path
backend_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_root not in sys.path:
    sys.path.insert(0, backend_root)

from sqlalchemy import select, update
from app.db.database import AsyncSessionLocal, init_db
from app.models.models import User


async def mark_users_verified(target_email: str | None = None) -> int:
    await init_db()
    async with AsyncSessionLocal() as session:
        if target_email:
            stmt = (
                update(User)
                .where(User.email == target_email)
                .values(is_email_verified=True, is_active=True)
            )
        else:
            stmt = (
                update(User)
                .where(User.is_email_verified == False)  # noqa: E712
                .values(is_email_verified=True, is_active=True)
            )
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount


def main():
    parser = argparse.ArgumentParser(description="Mark users as email-verified in dev database.")
    parser.add_argument("--email", help="Specific email to verify (defaults to all unverified users)", default=None)
    args = parser.parse_args()

    count = asyncio.run(mark_users_verified(args.email))
    if args.email:
        print(f"[CertiVerify Dev] Verified user '{args.email}' (rows affected: {count})")
    else:
        print(f"[CertiVerify Dev] Marked {count} unverified users as email-verified.")


if __name__ == "__main__":
    main()
