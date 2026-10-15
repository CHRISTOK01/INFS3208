"""Database connections for this service's own database.

Rather than opening a new connection for every request, we keep a small pool of open ones
and lend them out.
"""
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app import config

# open=False: don't connect yet. The pool gets opened when the app starts up.
# dict_row: each row comes back as a dict, like {"id": 1, "key": "energy"}.
pool = ConnectionPool(
    config.DATABASE_URL,
    min_size=1,
    max_size=config.DB_POOL_SIZE,
    open=False,
    kwargs={"row_factory": dict_row},
)


def open_pool():
    # wait=False: start up even if the database isn't ready yet.
    # /ready will say 503 until it is.
    pool.open(wait=False)


def close_pool():
    pool.close()


def check_db():
    """Run a tiny query. Raises an error if the database doesn't answer within 2 seconds."""
    with pool.connection(timeout=2) as conn:
        conn.execute("SELECT 1")


def get_conn():
    """Lend a connection to one request (FastAPI calls this for us).

    If the request goes fine, its changes are saved (committed). If it fails, they're undone.
    """
    with pool.connection(timeout=5) as conn:
        yield conn
