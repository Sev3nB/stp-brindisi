from flask import current_app
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

_pools = {}


def _configure(connection):
    connection.execute("SET search_path TO gtfs, public")
    connection.commit()


def get_pool():
    url = current_app.config.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL non configurato. Copia .env.example in .env.")
    if url not in _pools:
        _pools[url] = ConnectionPool(
            conninfo=url,
            min_size=1,
            max_size=5,
            kwargs={"row_factory": dict_row, "autocommit": True},
            configure=_configure,
            open=True,
        )
    return _pools[url]


def get_db():
    """Context manager per una connessione prelevata dal pool."""
    return get_pool().connection()


def close_pool():
    for pool in _pools.values():
        pool.close()
    _pools.clear()
