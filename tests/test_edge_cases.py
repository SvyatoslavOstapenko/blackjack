"""Проверки финансовых границ и ответов после фиксации транзакций."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Player
from tests.conftest import account

MAX_BALANCE = 2_147_483_647


def set_balance(player_id, amount):
    with Session(get_engine()) as db:
        db.get(Player, player_id).balance = amount
        db.commit()


def test_credit_reserves_space_for_active_round_payout(client, fixed_cards):
    player, player_id = account(client)
    admin, _ = account(client, "operator", admin=True)
    set_balance(player_id, MAX_BALANCE - 2000)
    rid = client.post(
        "/game/start", headers=player, json={"bet": 1000}
    ).json()["round_id"]
    assert (
        client.post(
            "/game/hit", headers=player, json={"round_id": rid}
        ).status_code
        == 200
    )
    credit = client.post(
        f"/admin/players/{player_id}/credit",
        headers=admin,
        json={"amount": 2000},
    )
    assert credit.status_code == 422
    safe_credit = client.post(
        f"/admin/players/{player_id}/credit",
        headers=admin,
        json={"amount": 1000},
    )
    assert safe_credit.status_code == 200
    finished = client.post(
        "/game/stand", headers=player, json={"round_id": rid}
    )
    assert finished.status_code == 200
    assert finished.json()["balance"] == MAX_BALANCE


def test_delete_reserves_space_for_other_active_round(client, fixed_cards):
    player, player_id = account(client)
    admin, _ = account(client, "operator", admin=True)
    old_id = client.post(
        "/game/start", headers=player, json={"bet": 1000}
    ).json()["round_id"]
    for _ in range(2):
        result = client.post(
            "/game/hit", headers=player, json={"round_id": old_id}
        )
        assert result.status_code == 200
    assert result.json()["status"] == "player_bust"
    set_balance(player_id, MAX_BALANCE - 2000)
    current = client.post(
        "/game/start", headers=player, json={"bet": 1000}
    ).json()
    assert (
        client.post(
            f"/admin/players/{player_id}/credit",
            headers=admin,
            json={"amount": 1000},
        ).status_code
        == 200
    )
    deleted = client.delete(f"/admin/rounds/{old_id}", headers=admin)
    assert deleted.status_code == 409
    assert (
        client.get(f"/game/round/{old_id}", headers=player).status_code == 200
    )
    finished = client.post(
        "/game/stand", headers=player, json={"round_id": current["round_id"]}
    )
    assert finished.status_code == 200
    assert finished.json()["balance"] <= MAX_BALANCE


def test_concurrent_credits_do_not_overflow(client):
    player, player_id = account(client)
    admin, _ = account(client, "operator", admin=True)
    set_balance(player_id, MAX_BALANCE - 1500)

    def credit(_):
        return client.post(
            f"/admin/players/{player_id}/credit",
            headers=admin,
            json={"amount": 1000},
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(credit, range(2))) == [200, 422]
    assert (
        client.get("/me", headers=player).json()["balance"]
        == MAX_BALANCE - 500
    )


@pytest.mark.parametrize(
    "action",
    ["register", "start", "hit", "stand", "credit", "reset", "delete"],
)
def test_success_response_needs_no_database_reads_after_commit(
    client, fixed_cards, monkeypatch, action
):
    player, player_id = account(client)
    admin, _ = account(client, "operator", admin=True)
    rid = None
    if action in ("hit", "stand", "delete"):
        rid = client.post(
            "/game/start", headers=player, json={"bet": 100}
        ).json()["round_id"]
        if action == "delete":
            client.post("/game/stand", headers=player, json={"round_id": rid})
    routes = {
        "register": (
            "POST",
            "/register",
            {"nickname": "new_player", "password": "example-only-test-pass"},
            {},
        ),
        "start": ("POST", "/game/start", {"bet": 100}, player),
        "hit": ("POST", "/game/hit", {"round_id": rid}, player),
        "stand": ("POST", "/game/stand", {"round_id": rid}, player),
        "credit": (
            "POST",
            f"/admin/players/{player_id}/credit",
            {"amount": 100},
            admin,
        ),
        "reset": ("POST", f"/admin/players/{player_id}/reset", None, admin),
        "delete": ("DELETE", f"/admin/rounds/{rid}", None, admin),
    }
    engine = get_engine()
    original_commit = Session.commit

    def unavailable(*args, **kwargs):
        raise OperationalError(
            "SELECT after commit", {}, Exception("connection unavailable")
        )

    def commit_then_disconnect(db):
        original_commit(db)
        scoped.setattr(engine, "connect", unavailable)

    with monkeypatch.context() as scoped:
        # The request may commit, then lose its next database connection.
        scoped.setattr(Session, "commit", commit_then_disconnect)
        method, url, body, headers = routes[action]
        response = client.request(method, url, json=body, headers=headers)
        assert response.status_code == (
            201 if action in ("register", "start") else 200
        )


def test_details_remain_consistent_during_concurrent_delete(
    client, fixed_cards, monkeypatch
):
    import app.game_api as game_api

    player, _ = account(client)
    admin, _ = account(client, "operator", admin=True)
    rid = client.post("/game/start", headers=player, json={"bet": 100}).json()[
        "round_id"
    ]
    client.post("/game/stand", headers=player, json={"round_id": rid})
    reading, delete_finished = Event(), Event()
    original = game_api.get_hands_and_cards

    def read_cards(db, round_id):
        reading.set()
        delete_finished.wait(0.5)
        return original(db, round_id)

    monkeypatch.setattr(game_api, "get_hands_and_cards", read_cards)

    def remove():
        assert reading.wait(5)
        try:
            return client.delete(f"/admin/rounds/{rid}", headers=admin)
        finally:
            delete_finished.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        deleting = pool.submit(remove)
        response = client.get(f"/game/round/{rid}", headers=player)
        assert response.status_code == 200
        assert len(response.json()["player_cards"]) == 2
        assert deleting.result(timeout=5).status_code == 200


@pytest.mark.parametrize(
    "url,expected",
    [
        ("/leaderboard?limit=11", "1 до 10"),
        ("/game/rounds?limit=101", "1 до 100"),
        ("/game/rounds?offset=-1", "Смещение"),
    ],
)
def test_validation_messages_name_the_actual_field(client, url, expected):
    player, _ = account(client)
    response = client.get(url, headers=player)
    assert response.status_code == 422
    assert expected in response.json()["detail"]
    assert "пароль" not in response.json()["detail"].lower()
