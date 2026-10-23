"""
Async SQLAlchemy engine/session setup for PostgreSQL with SQLite fallback.
"""
import logging
from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.core.config import settings

logger = logging.getLogger("certiverify.db")

_session_factory = None
engine = None

def _normalize_db_url(db_url: str) -> str:
    if "@db:" in db_url:
        import socket
        try:
            socket.gethostbyname("db")
        except socket.gaierror:
            logger.info("Host 'db' not resolvable in current environment; falling back to 'localhost'.")
            return db_url.replace("@db:", "@localhost:")
    return db_url


def _create_engine_and_session(db_url: str):
    db_url = _normalize_db_url(db_url)
    connect_args = {}
    engine_kwargs = {
        "echo": settings.DEBUG,
        "future": True,
    }
    if db_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        connect_args["timeout"] = 60.0
    else:
        # PostgreSQL asyncpg connection pool configuration
        engine_kwargs["pool_pre_ping"] = getattr(settings, "DB_POOL_PRE_PING", True)
        engine_kwargs["pool_size"] = getattr(settings, "DB_POOL_SIZE", 20)
        engine_kwargs["max_overflow"] = getattr(settings, "DB_MAX_OVERFLOW", 10)
        engine_kwargs["pool_recycle"] = getattr(settings, "DB_POOL_RECYCLE_SECONDS", 1800)
        engine_kwargs["pool_timeout"] = getattr(settings, "DB_POOL_TIMEOUT_SECONDS", 30)

    eng = create_async_engine(
        db_url,
        connect_args=connect_args,
        **engine_kwargs,
    )

    if db_url.startswith("sqlite"):
        @event.listens_for(eng.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record):
            try:
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA busy_timeout=60000")
                cursor.execute("PRAGMA synchronous=NORMAL")
                cursor.close()
            except Exception as e:
                logger.debug("Failed setting SQLite pragmas: %s", e)

    sess_factory = async_sessionmaker(bind=eng, expire_on_commit=False, class_=AsyncSession)
    return eng, sess_factory


class AsyncSessionLocalProxy:
    """Proxy class ensuring callers importing AsyncSessionLocal at module load
    always invoke the currently active async_sessionmaker even after reinit_engine()."""
    def __call__(self, *args, **kwargs):
        if _session_factory is None:
            raise RuntimeError("Database session factory is not initialized.")
        return _session_factory(*args, **kwargs)

    def __getattr__(self, item):
        if _session_factory is None:
            raise RuntimeError("Database session factory is not initialized.")
        return getattr(_session_factory, item)


engine, _session_factory = _create_engine_and_session(settings.DATABASE_URL)
AsyncSessionLocal = AsyncSessionLocalProxy()
Base = declarative_base()


def reinit_engine(db_url: str):
    """Utility function to switch DB engine (e.g. for testing with SQLite)."""
    global engine, _session_factory
    engine, _session_factory = _create_engine_and_session(db_url)
    return engine, AsyncSessionLocal


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Create all tables. If PostgreSQL connection fails, fall back to SQLite in dev, or abort in prod."""
    global engine, _session_factory
    try:
        async with engine.begin() as conn:
            from app.models import models  # noqa: F401 ensures models are registered
            await conn.run_sync(Base.metadata.create_all)
            if "postgresql" in str(engine.url) or "postgres" in str(engine.url):
                from sqlalchemy import text
                await conn.execute(text("ALTER TABLE certificates ADD COLUMN IF NOT EXISTS is_history_hidden BOOLEAN NOT NULL DEFAULT FALSE;"))
                await conn.execute(text("ALTER TABLE certificates ADD COLUMN IF NOT EXISTS history_deleted_at TIMESTAMP WITHOUT TIME ZONE;"))
    except Exception as exc:
        is_prod = settings.ENV.lower() in ("production", "prod")
        if is_prod:
            logger.critical("PostgreSQL unreachable in production mode (%s). Aborting startup.", exc)
            raise RuntimeError(f"Database connection failed in production mode: {exc}") from exc

        if "postgresql" in settings.DATABASE_URL or "postgres" in settings.DATABASE_URL:
            logger.warning("PostgreSQL unreachable (%s). Falling back to SQLite dev database.", exc)
            fallback_url = "sqlite+aiosqlite:///./certiverify_dev.db"
            reinit_engine(fallback_url)
            async with engine.begin() as conn:
                from app.models import models  # noqa: F401
                await conn.run_sync(Base.metadata.create_all)
        else:
            raise exc


