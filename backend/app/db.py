import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Any
import anyio

logger = logging.getLogger("mb_associates.db")

# Detect available PostgreSQL driver: psycopg v3 or psycopg2 fallback
PSYCOPG_VERSION = None
try:
    import psycopg
    from psycopg.rows import dict_row
    from psycopg_pool import AsyncConnectionPool
    PSYCOPG_VERSION = 3
    logger.info("Using psycopg v3 with AsyncConnectionPool")
except ImportError:
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from psycopg2.pool import ThreadedConnectionPool
        PSYCOPG_VERSION = 2
        logger.info("Using psycopg2 with ThreadedConnectionPool async adapter")
    except ImportError:
        logger.warning("Neither psycopg v3 nor psycopg2 is available.")

_pool: Any = None

# Async adapter for psycopg2
class Psycopg2AsyncCursor:
    def __init__(self, sync_cur):
        self._cur = sync_cur

    async def execute(self, query: str, params: Any = None):
        return await anyio.to_thread.run_sync(self._cur.execute, query, params)

    async def fetchone(self):
        return await anyio.to_thread.run_sync(self._cur.fetchone)

    async def fetchall(self):
        return await anyio.to_thread.run_sync(self._cur.fetchall)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await anyio.to_thread.run_sync(self._cur.close)

class Psycopg2AsyncConnection:
    def __init__(self, sync_conn, pool=None):
        self._conn = sync_conn
        self._pool = pool

    def cursor(self):
        cur = self._conn.cursor(cursor_factory=RealDictCursor)
        return Psycopg2AsyncCursor(cur)

    async def commit(self):
        await anyio.to_thread.run_sync(self._conn.commit)

    async def rollback(self):
        await anyio.to_thread.run_sync(self._conn.rollback)

    async def close(self):
        if self._pool:
            self._pool.putconn(self._conn)
        else:
            await anyio.to_thread.run_sync(self._conn.close)

async def init_db_pool(conn_str: Optional[str] = None):
    """Initialize the PostgreSQL connection pool."""
    global _pool
    from app.config import get_settings
    settings = get_settings()
    url = conn_str or settings.database_url

    if not url or "your-project-ref" in url:
        logger.warning(
            "DATABASE_URL contains placeholder values. "
            "Database pool not initialized. Configure backend/.env with your Supabase credentials."
        )
        return None

    try:
        if PSYCOPG_VERSION == 3:
            _pool = AsyncConnectionPool(
                conninfo=url,
                min_size=1,
                max_size=10,
                timeout=10.0,
                max_idle=300.0,
                kwargs={"row_factory": dict_row}
            )
            await _pool.open()
            logger.info("Database pool (psycopg v3) successfully initialized.")
            return _pool
        elif PSYCOPG_VERSION == 2:
            _pool = ThreadedConnectionPool(1, 10, url)
            logger.info("Database pool (psycopg2) successfully initialized.")
            return _pool
    except Exception as exc:
        logger.error(f"Failed to connect to PostgreSQL database: {exc}")
        _pool = None
        return None

async def close_db_pool() -> None:
    """Close the database connection pool gracefully."""
    global _pool
    if _pool is not None:
        try:
            if PSYCOPG_VERSION == 3:
                await _pool.close()
            elif PSYCOPG_VERSION == 2:
                _pool.closeall()
        except Exception as e:
            logger.error(f"Error closing DB pool: {e}")
        _pool = None
        logger.info("Database connection pool closed.")

def get_pool():
    """Return the global connection pool."""
    return _pool

def set_pool(pool):
    """Override pool (useful for test suites with isolated database)."""
    global _pool
    _pool = pool

@asynccontextmanager
async def get_db_connection():
    """
    Context manager yielding an async connection.
    Works seamlessly with psycopg v3 or psycopg2 adapter.
    """
    if _pool is None:
        raise RuntimeError(
            "Database pool is not available. Ensure DATABASE_URL is configured in backend/.env "
            "and migrations have been applied."
        )

    if PSYCOPG_VERSION == 3:
        async with _pool.connection() as conn:
            yield conn
    elif PSYCOPG_VERSION == 2:
        sync_conn = await anyio.to_thread.run_sync(_pool.getconn)
        async_conn = Psycopg2AsyncConnection(sync_conn, _pool)
        try:
            yield async_conn
        finally:
            await async_conn.close()
