"""SQLAlchemy engine and sessions for configuration-service's PostgreSQL. Created lazily, so
building the app needs no database (tests pass their own sessionmaker, on SQLite)."""

from functools import lru_cache

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import sessionmaker

from . import config


def database_url() -> str | URL:
    if config.DATABASE_URL:
        return config.DATABASE_URL
    # Cloud Run mounts Cloud SQL at /cloudsql/<instance>; psycopg expects this
    # directory as a libpq host parameter, rather than as the URL hostname.
    unix_socket = config.POSTGRES_HOST.startswith('/')
    return URL.create(
        'postgresql+psycopg',
        username=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
        host=None if unix_socket else config.POSTGRES_HOST,
        port=None if unix_socket else config.POSTGRES_PORT,
        database=config.POSTGRES_DB,
        query={'host': config.POSTGRES_HOST} if unix_socket else {},
    )


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping: the service runs for days; drop connections the database has closed.
    return create_engine(database_url(), pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker:
    """Sessions whose objects stay usable after their transaction ends (expire_on_commit=False):
    the chat flow reads in short sessions, closed before the (slow) LLM calls, like Django's
    autocommit, so no transaction is left open while it waits for the model."""
    return sessionmaker(get_engine(), expire_on_commit=False)
