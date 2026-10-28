"""
Database Connection & Transaction Management Layer (MySQL 8+)
Uses parameterized SQL queries exclusively to prevent SQL injection.
"""

from contextlib import contextmanager
import mysql.connector
from mysql.connector import Error
from config import Config


def get_server_connection():
    """Connect to MySQL Server as root without selecting a database (used ONLY during initial schema & user setup)."""
    return mysql.connector.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_ROOT_USER,
        password=Config.DB_ROOT_PASSWORD,
        charset="utf8mb4",
        use_unicode=True,
    )


def get_db_connection():
    """Return a new MySQL connection to `refind_db` with autocommit disabled by default."""
    return mysql.connector.connect(
        host=Config.DB_HOST,
        port=Config.DB_PORT,
        user=Config.DB_USER,
        password=Config.DB_PASSWORD,
        database=Config.DB_NAME,
        charset="utf8mb4",
        use_unicode=True,
        autocommit=False,
    )


@contextmanager
def db_cursor(dictionary=True, commit=False):
    """
    Context manager for standard parameterized SQL queries.
    Automatically commits if `commit=True` and rolls back on any exception.
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=dictionary)
        yield cursor
        if commit:
            conn.commit()
    except Error:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


@contextmanager
def db_transaction():
    """
    Explicit ACID transaction context manager.
    Used for multi-step atomic operations such as Claim Approval + Item Status Update
    + Competing Claim Rejection + Activity Logging with row-level locks (SELECT ... FOR UPDATE).
    """
    conn = None
    cursor = None
    try:
        conn = get_db_connection()
        conn.start_transaction(isolation_level="READ COMMITTED")
        cursor = conn.cursor(dictionary=True)
        yield conn, cursor
        conn.commit()
    except Exception:
        if conn and conn.is_connected():
            conn.rollback()
        raise
    finally:
        if cursor:
            cursor.close()
        if conn and conn.is_connected():
            conn.close()


def query_all(sql: str, params: tuple = ()) -> list[dict]:
    """Execute a parameterized SELECT query and return all rows as dicts."""
    with db_cursor(dictionary=True, commit=False) as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    """Execute a parameterized SELECT query and return a single row as dict."""
    with db_cursor(dictionary=True, commit=False) as cur:
        cur.execute(sql, params)
        return cur.fetchone()


def execute_write(sql: str, params: tuple = ()) -> int:
    """Execute a parameterized INSERT/UPDATE/DELETE and return lastrowid or rowcount."""
    with db_cursor(dictionary=True, commit=True) as cur:
        cur.execute(sql, params)
        return cur.lastrowid if cur.lastrowid else cur.rowcount


def log_activity(
    user_id: int | None,
    action_type: str,
    entity_type: str,
    entity_id: int,
    summary: str,
    cursor=None,
) -> None:
    """
    Record an audit event in `activity_logs`.
    Can participate in an existing transaction cursor or run standalone.
    """
    sql = """
        INSERT INTO activity_logs (user_id, action_type, entity_type, entity_id, summary)
        VALUES (%s, %s, %s, %s, %s)
    """
    params = (user_id, action_type, entity_type, entity_id, summary[:300])
    if cursor is not None:
        cursor.execute(sql, params)
    else:
        execute_write(sql, params)
