"""Initialize database tables."""

from app.db import get_engine
from app.models import Base


def main():
    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    print("Database tables initialized successfully")


if __name__ == "__main__":
    main()