import os
from datetime import timedelta


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")

    SQL_DRIVER = os.environ.get("SQL_DRIVER", "ODBC Driver 17 for SQL Server")
    SQL_SERVER = os.environ.get("SQL_SERVER", "localhost")
    SQL_DATABASE = os.environ.get("SQL_DATABASE", "quotation")
    SQL_USER = os.environ.get("SQL_USER", "")
    SQL_PASSWORD = os.environ.get("SQL_PASSWORD", "")

    MAX_CONTENT_LENGTH = 2 * 1024 * 1024        # logo uploads limited to 2 MB

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(days=14)   # length of "Keep me signed in"
    WTF_CSRF_TIME_LIMIT = None                  # form tokens last as long as the session