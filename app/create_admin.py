"""Создание учётной записи администратора из локальной консоли."""

import argparse
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Player
from app.security import hash_password


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("nickname")
    args = parser.parse_args()
    nickname = args.nickname.strip()
    if not 1 <= len(nickname) <= 32 or any(ord(c) < 32 for c in nickname):
        parser.error("Никнейм должен содержать от 1 до 32 символов.")
    password = getpass("Пароль (8–128 символов): ")
    if (
        not 8 <= len(password) <= 128
        or getpass("Повторите пароль: ") != password
    ):
        parser.error("Пароли не совпадают или имеют неподходящую длину.")
    with Session(get_engine()) as db:
        if db.scalar(select(Player.id).where(Player.nickname == nickname)):
            parser.error(
                "Никнейм занят. Укажите новый; "
                "существующий аккаунт не изменён."
            )
        db.add(
            Player(
                nickname=nickname,
                password_hash=hash_password(password),
                is_admin=True,
            )
        )
        db.commit()
    print("Администратор создан.")


if __name__ == "__main__":
    main()
