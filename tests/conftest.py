import os
from secrets import token_urlsafe
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db import get_engine
from app.main import app
from app.models import Base


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("AUTH_SECRET", token_urlsafe(48))
    database_url = "sqlite:///" + (tmp_path / "test.db").as_posix()
    maintenance = None
    schema = None
    postgres_url = os.environ.get("TEST_POSTGRES_URL")
    if postgres_url:
        url = make_url(postgres_url)
        if url.host != "127.0.0.1" or url.database != "blackjack_verify":
            pytest.fail(
                "PostgreSQL-проверки разрешены только "
                "в локальной blackjack_verify."
            )
        maintenance = create_engine(url)
        schema = "verify_" + uuid4().hex
        with maintenance.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        database_url = url.update_query_dict(
            {"options": f"-csearch_path={schema}"}
        ).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_engine.cache_clear()
    engine = get_engine()
    try:
        Base.metadata.create_all(engine)
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()
        get_engine.cache_clear()
        if maintenance is not None:
            with maintenance.begin() as connection:
                connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
            maintenance.dispose()


@pytest.fixture
def fixed_cards(monkeypatch):
    from app.game import RANKS, SUITS

    tail = [
        ("3", "H"),
        ("2", "C"),
        ("9", "C"),
        ("7", "D"),
        ("6", "H"),
        ("10", "S"),
    ]
    deck = [(r, s) for s in SUITS for r in RANKS if (r, s) not in tail] + tail
    monkeypatch.setattr("app.game_api.build_deck", lambda: deck.copy())


def account(client, nickname="alice", admin=False):
    from sqlalchemy import select
    from sqlalchemy.orm import Session
    from app.models import Player

    password = token_urlsafe(18)
    response = client.post(
        "/register", json={"nickname": nickname, "password": password}
    )
    assert response.status_code == 201
    if admin:
        with Session(get_engine()) as db:
            db.scalar(
                select(Player).where(Player.nickname == nickname)
            ).is_admin = True
            db.commit()
    login = client.post(
        "/login", json={"nickname": nickname, "password": password}
    )
    assert login.status_code == 200
    return {
        "Authorization": "Bearer " + login.json()["access_token"]
    }, response.json()["id"]
