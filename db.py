from contextlib import contextmanager
import pyodbc
from flask import current_app


def _connection_string():
    cfg = current_app.config
    parts = [
        f"DRIVER={{{cfg['SQL_DRIVER']}}}",
        f"SERVER={cfg['SQL_SERVER']}",
        f"DATABASE={cfg['SQL_DATABASE']}",
        "TrustServerCertificate=yes",       # fine for local dev; use a real cert in production
    ]
    if cfg["SQL_USER"]:
        parts += [f"UID={cfg['SQL_USER']}", f"PWD={cfg['SQL_PASSWORD']}"]
    else:
        parts.append("Trusted_Connection=yes")   # Windows authentication
    return ";".join(parts)


@contextmanager
def get_conn():
    conn = pyodbc.connect(_connection_string(), autocommit=False)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def rows_as_dicts(cursor):
    cols = [c[0] for c in cursor.description]
    return [dict(zip(cols, row)) for row in cursor.fetchall()]