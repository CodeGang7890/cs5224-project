"""SQLAlchemy engine and sessions. Created lazily, so importing the app needs no database."""

from functools import lru_cache

from sqlalchemy import URL, Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app import config


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
    # A short run per hour: no point keeping pooled connections open.
    return create_engine(database_url(), poolclass=NullPool)


def get_session() -> Session:
    return sessionmaker(get_engine())()
