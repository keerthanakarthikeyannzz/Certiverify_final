"""
Pytest configuration and global fixtures for backend unit tests.
Configures an isolated SQLite database so tests run fast without requiring local PostgreSQL.
"""
import os
import pytest
import pytest_asyncio

# Force SQLite test DB URL and development mode before importing app modules
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_certiverify.db"
os.environ["ENV"] = "development"

from app.core.config import settings
settings.DATABASE_URL = "sqlite+aiosqlite:///./test_certiverify.db"
settings.ENV = "development"

from app.db.database import reinit_engine, init_db, engine
from app.models.models import Base


def find_sample_pdf() -> str:
    """Recursively locates sample_certificate.pdf climbing parent directories."""
    curr = os.path.abspath(__file__)
    for _ in range(6):
        curr = os.path.dirname(curr)
        candidate = os.path.join(curr, "sample_certificate.pdf")
        if os.path.exists(candidate):
            return candidate
    if os.path.exists("./sample_certificate.pdf"):
        return os.path.abspath("./sample_certificate.pdf")
    raise FileNotFoundError("sample_certificate.pdf could not be found.")


def generate_valid_pdf_bytes(text: str = "CertiVerify Verified Certificate") -> bytes:
    """Generates valid PDF byte stream using PyMuPDF."""
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 72), text, fontsize=14)
    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


def verify_test_user_email_sync(email: str):
    """Directly verifies user email in SQLite test database for synchronous tests."""
    import sqlite3
    conn = sqlite3.connect("./test_certiverify.db")
    cur = conn.cursor()
    cur.execute("UPDATE users SET is_email_verified = 1 WHERE email = ?", (email,))
    conn.commit()
    conn.close()


async def verify_test_user_email(email: str):
    """Directly verifies user email in SQLite test database for asynchronous tests."""
    from app.db.database import AsyncSessionLocal
    from app.models.models import User
    from sqlalchemy import update
    async with AsyncSessionLocal() as session:
        await session.execute(
            update(User).where(User.email == email).values(is_email_verified=True)
        )
        await session.commit()


@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_test_db():
    reinit_engine("sqlite+aiosqlite:///./test_certiverify.db")
    await init_db()
    yield
    try:
        from app.db.database import engine
        if engine:
            await engine.dispose()
        for suffix in ["", "-wal", "-shm"]:
            fpath = f"./test_certiverify.db{suffix}"
            if os.path.exists(fpath):
                os.remove(fpath)
    except Exception:
        pass

