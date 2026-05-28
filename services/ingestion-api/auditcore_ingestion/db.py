from collections.abc import Iterator
from contextlib import contextmanager

from psycopg import Connection
from psycopg_pool import ConnectionPool

from .config import settings

_pool: ConnectionPool | None = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(settings.db_dsn, min_size=1, max_size=10, open=True)
    return _pool


@contextmanager
def conn() -> Iterator[Connection]:
    pool = get_pool()
    with pool.connection() as c:
        yield c


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
