"""SQLAlchemy engine and sessions. Created lazily, so building the app needs no database."""

from functools import lru_cache

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from . import config


def database_url() -> str | URL:
    if config.DATABASE_URL:
        return config.DATABASE_URL
    return URL.create(
        'postgresql+psycopg',
        username=config.POSTGRES_USER,
        password=config.POSTGRES_PASSWORD,
        host=config.POSTGRES_HOST,
        port=config.POSTGRES_PORT,
        database=config.POSTGRES_DB,
    )


@lru_cache
def get_engine() -> Engine:
    # pool_pre_ping: the consumer runs for days; drop connections the database has closed.
    return create_engine(database_url(), pool_pre_ping=True)


def get_session() -> Session:
    return sessionmaker(get_engine())()
