"""Database connection and sessions."""

import os
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


@lru_cache(maxsize=1)
def get_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    return create_engine(url, pool_pre_ping=True)


def get_session():
    with Session(get_engine()) as session:
        yield session


def check_database():
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))