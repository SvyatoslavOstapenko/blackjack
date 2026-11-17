"""Database connection and sessions."""

import os
from functools import lru_cache

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import Session


@lru_cache(maxsize=1)
def get_engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not configured")
    options = {}
    if url.startswith("sqlite:"):
        options["connect_args"] = {"check_same_thread": False, "timeout": 15}
    engine = create_engine(url, pool_pre_ping=True, **options)
    if engine.dialect.name == "sqlite":

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            connection.isolation_level = None
            connection.execute("PRAGMA foreign_keys=ON")

        @event.listens_for(engine, "begin")
        def begin_sqlite(connection):
            connection.exec_driver_sql("BEGIN IMMEDIATE")

    return engine


def get_session():
    with Session(get_engine()) as session:
        yield session


def check_database():
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
