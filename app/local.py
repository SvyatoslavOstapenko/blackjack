"""Локальный запуск с отдельной SQLite-базой и постоянным ключом сеанса."""

import argparse
import os
from pathlib import Path
from secrets import token_urlsafe
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8006)
    parser.add_argument("--data-dir", type=Path, default=Path("data/local"))
    parser.add_argument("--create-admin", metavar="НИКНЕЙМ")
    args = parser.parse_args()
    data = args.data_dir.resolve()
    data.mkdir(parents=True, exist_ok=True)
    key = data / "auth.key"
    if not key.exists():
        with key.open("x", encoding="utf-8") as stream:
            stream.write(token_urlsafe(48))
    os.environ["AUTH_SECRET"] = key.read_text(encoding="utf-8").strip()
    os.environ["DATABASE_URL"] = (
        "sqlite:///" + (data / "blackjack.sqlite3").as_posix()
    )
    os.environ["APP_LOG_DIR"] = str(data / "logs")

    from app.init_db import main as initialize

    initialize()
    if args.create_admin:
        from app.create_admin import main as create_admin

        sys.argv = [sys.argv[0], args.create_admin]
        create_admin()
        return

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
