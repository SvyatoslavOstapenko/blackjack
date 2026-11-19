from alembic import context
from app.db import get_engine


def run():
    settings = {
        "version_table_schema": "public",
        "transactional_ddl": True,
    }
    if context.is_offline_mode():
        context.configure(
            dialect_name="postgresql", literal_binds=True,
            dialect_opts={"paramstyle": "named"}, **settings,
        )
        with context.begin_transaction():
            context.run_migrations()
        return

    engine = get_engine()
    try:
        with engine.connect() as connection:
            if connection.dialect.name != "postgresql":
                raise RuntimeError("Migrations require PostgreSQL")
            context.configure(connection=connection, **settings)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


run()
