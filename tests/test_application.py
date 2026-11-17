from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db import get_engine
from app.models import Card, Hand, Player, Round
from tests.conftest import account


def test_front_page_static_assets_and_health(client):
    response = client.get("/")
    assert response.status_code == 200 and 'lang="ru"' in response.text
    assert "Content-Security-Policy" in response.headers
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/static/../auth.py").status_code == 404


@pytest.mark.parametrize(
    "path", ["/me", "/game/active", "/game/rounds", "/admin/players"]
)
def test_guests_cannot_access_private_data(client, path):
    assert client.get(path).status_code == 401


def test_registration_hash_login_and_duplicate(client):
    headers, _ = account(client, "  alice  ")
    me = client.get("/me", headers=headers).json()
    assert me["nickname"] == "alice" and me["balance"] == 1000
    assert me["is_admin"] is False
    assert "password_hash" not in me
    with Session(get_engine()) as db:
        hashed = db.scalar(select(Player.password_hash))
        assert (
            hashed.startswith("$argon2") and hashed != "example-only-test-pass"
        )
    assert (
        client.post(
            "/register",
            json={"nickname": "alice", "password": "another-test-pass"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            "/login", json={"nickname": "alice", "password": "wrong"}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "nickname,password",
    [
        (" ", "test-password"),
        ("a" * 33, "test-password"),
        ("alice", "short"),
        ("alice", "a" * 129),
        ("bad\nname", "test-password"),
    ],
)
def test_invalid_registration(client, nickname, password):
    assert (
        client.post(
            "/register", json={"nickname": nickname, "password": password}
        ).status_code
        == 422
    )


def test_invalid_and_expired_token(client):
    from unittest.mock import patch
    from app.auth import create_token, TOKEN_LIFETIME_SECONDS

    headers, player_id = account(client)
    forged = {"Authorization": headers["Authorization"] + "tampered"}
    assert client.get("/me", headers=forged).status_code == 401
    with patch("time.time", return_value=1):
        expired = create_token(player_id)
    assert TOKEN_LIFETIME_SECONDS > 0
    assert (
        client.get(
            "/me", headers={"Authorization": "Bearer " + expired}
        ).status_code
        == 401
    )


@pytest.mark.parametrize(
    "bet", [-2, 0, 3, 1002, 2.5, "20", True, 2_147_483_648]
)
def test_invalid_bet_leaves_balance_unchanged(client, bet):
    headers, _ = account(client)
    assert client.post(
        "/game/start", headers=headers, json={"bet": bet}
    ).status_code in (409, 422)
    assert client.get("/me", headers=headers).json()["balance"] == 1000
    with Session(get_engine()) as db:
        assert db.scalar(select(func.count()).select_from(Round)) == 0


def test_resume_hit_stand_history_and_ownership(client, fixed_cards):
    headers, _ = account(client)
    foreign, _ = account(client, "bob")
    start = client.post(
        "/game/start", headers=headers, json={"bet": 100}
    ).json()
    rid = start["round_id"]
    assert start["balance"] == 900 and len(start["dealer_cards"]) == 1
    assert start["dealer_score"] is None and start["payout"] is None
    assert client.get("/game/rounds", headers=headers).json() == []
    get_engine().dispose()
    assert (
        client.get("/game/active", headers=headers).json()["round_id"] == rid
    )
    assert start["started_at"].endswith("Z") or start["started_at"].endswith(
        "+00:00"
    )
    assert client.get(f"/game/round/{rid}", headers=foreign).status_code == 404
    assert (
        client.post(
            "/game/hit", headers=foreign, json={"round_id": rid}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/game/start", headers=headers, json={"bet": 100}
        ).status_code
        == 409
    )
    hit = client.post(
        "/game/hit", headers=headers, json={"round_id": rid}
    ).json()
    assert hit["player_score"] == 19
    finished = client.post(
        "/game/stand", headers=headers, json={"round_id": rid}
    ).json()
    assert finished["status"] == "player_won" and finished["payout"] == 200
    assert finished["balance"] == 1100 and finished["dealer_score"] == 18
    assert client.get("/game/active", headers=headers).json() is None
    for move in ("hit", "stand"):
        assert (
            client.post(
                f"/game/{move}", headers=headers, json={"round_id": rid}
            ).status_code
            == 409
        )
    history = client.get("/game/rounds", headers=headers).json()
    assert len(history) == 1 and len(history[0]["player_cards"]) == 3
    assert client.get("/game/rounds", headers=foreign).json() == []
    assert client.get("/me", headers=headers).json()["rounds_played"] == 1


def test_concurrent_start_only_charges_one_bet(client, fixed_cards):
    headers, _ = account(client)

    def start(_):
        return client.post(
            "/game/start", headers=headers, json={"bet": 100}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(start, range(2))) == [201, 409]
    assert client.get("/me", headers=headers).json()["balance"] == 900


def test_admin_permissions_credit_reset_and_delete(client, fixed_cards):
    headers, player_id = account(client)
    admin, _ = account(client, "operator", admin=True)
    assert client.get("/admin/players", headers=headers).status_code == 403
    assert (
        client.post(
            f"/admin/players/{player_id}/credit",
            headers=headers,
            json={"amount": 500},
        ).status_code
        == 403
    )
    credit = client.post(
        f"/admin/players/{player_id}/credit",
        headers=admin,
        json={"amount": 500},
    )
    assert credit.json()["balance"] == 1500
    start = client.post(
        "/game/start", headers=headers, json={"bet": 100}
    ).json()
    rid = start["round_id"]
    assert (
        client.post(
            f"/admin/players/{player_id}/reset", headers=admin
        ).status_code
        == 409
    )
    assert (
        client.delete(f"/admin/rounds/{rid}", headers=admin).status_code == 409
    )
    client.post("/game/stand", headers=headers, json={"round_id": rid})
    assert (
        client.delete(f"/admin/rounds/{rid}", headers=headers).status_code
        == 403
    )
    deleted = client.delete(f"/admin/rounds/{rid}", headers=admin)
    assert (
        deleted.status_code == 200
        and deleted.json()["player"]["balance"] == 1500
    )
    with Session(get_engine()) as db:
        for model in (Round, Hand, Card):
            assert db.scalar(select(func.count()).select_from(model)) == 0
    assert client.get("/me", headers=headers).json()["rounds_played"] == 0
    assert (
        client.post(f"/admin/players/{player_id}/reset", headers=admin).json()[
            "balance"
        ]
        == 1000
    )
    assert (
        client.get("/admin/players/99999/rounds", headers=admin).status_code
        == 404
    )


@pytest.mark.parametrize("amount", [0, -2, 1.5, True, "10", 2_147_483_647])
def test_admin_invalid_credit_and_overflow(client, amount):
    admin, player_id = account(client, "operator", admin=True)
    response = client.post(
        f"/admin/players/{player_id}/credit",
        headers=admin,
        json={"amount": amount},
    )
    assert response.status_code == 422
    assert client.get("/me", headers=admin).json()["balance"] == 1000


def test_leaderboard_sorting_limits_and_private_fields(client):
    account(client, "zulu")
    account(client, "alpha")
    data = client.get("/leaderboard?limit=1").json()
    assert len(data) == 1 and data[0]["nickname"] == "alpha"
    assert set(data[0]) == {"nickname", "balance", "rounds_played"}
    for limit in (0, 11):
        assert client.get(f"/leaderboard?limit={limit}").status_code == 422


def test_database_failure_does_not_leak_sql_and_recovers(client, monkeypatch):
    engine = get_engine()

    def fail(*args, **kwargs):
        raise OperationalError(
            "SELECT sensitive", {}, Exception("connection failed")
        )

    with monkeypatch.context() as m:
        m.setattr(engine, "connect", fail)
        response = client.get("/leaderboard")
        assert response.status_code == 503 and "SELECT" not in response.text
        assert client.get("/health").status_code == 503
    assert client.get("/health").status_code == 200
    assert client.get("/leaderboard").status_code == 200


def test_ten_players_can_play_concurrently(client, fixed_cards):
    users = [account(client, f"player{i}")[0] for i in range(10)]

    def play(headers):
        start = client.post("/game/start", headers=headers, json={"bet": 20})
        assert start.status_code == 201
        end = client.post(
            "/game/stand",
            headers=headers,
            json={"round_id": start.json()["round_id"]},
        )
        assert end.status_code == 200
        return end.json()

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(play, users))
    assert len({r["round_id"] for r in results}) == 10
    assert all(r["balance"] == 1000 for r in results)


def test_concurrent_final_moves_only_pay_once(client, fixed_cards):
    headers, _ = account(client)
    rid = client.post(
        "/game/start", headers=headers, json={"bet": 100}
    ).json()["round_id"]

    def stand(_):
        return client.post(
            "/game/stand", headers=headers, json={"round_id": rid}
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(stand, range(2))) == [200, 409]
    me = client.get("/me", headers=headers).json()
    assert me["balance"] == 1000 and me["rounds_played"] == 1


def test_blackjack_is_settled_immediately(client, monkeypatch):
    headers, _ = account(client)
    # pop() выдаёт карты в порядке: игрок, дилер, игрок, дилер.
    monkeypatch.setattr(
        "app.game_api.build_deck",
        lambda: [("9", "H"), ("K", "S"), ("Q", "D"), ("A", "C")],
    )
    response = client.post("/game/start", headers=headers, json={"bet": 100})
    assert response.status_code == 201
    result = response.json()
    assert result["status"] == "player_blackjack" and result["payout"] == 250
    assert result["balance"] == 1150
    assert client.get("/game/active", headers=headers).json() is None


def test_database_constraints_are_real(client):
    from sqlalchemy.exc import IntegrityError

    with Session(get_engine()) as db:
        db.add(
            Player(
                nickname="invalid", password_hash="not-a-secret", balance=-1
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()
    with Session(get_engine()) as db:
        db.add(Hand(round_id=9999, owner="player", score=0))
        with pytest.raises(IntegrityError):
            db.commit()


def test_admin_cannot_delete_spent_winnings(client, fixed_cards):
    headers, pid = account(client)
    admin, _ = account(client, "operator", admin=True)
    rid = client.post(
        "/game/start", headers=headers, json={"bet": 100}
    ).json()["round_id"]
    client.post("/game/hit", headers=headers, json={"round_id": rid})
    client.post("/game/stand", headers=headers, json={"round_id": rid})
    with Session(get_engine()) as db:
        db.get(Player, pid).balance = 0
        db.commit()
    response = client.delete(f"/admin/rounds/{rid}", headers=admin)
    assert response.status_code == 409
    assert client.get(f"/game/round/{rid}", headers=headers).status_code == 200


def test_admin_cli_uses_password_hash_and_does_not_overwrite(
    client, monkeypatch
):
    from app.create_admin import main

    monkeypatch.setattr("sys.argv", ["create_admin", "operator"])
    monkeypatch.setattr(
        "app.create_admin.getpass", lambda _: "example-only-test-pass"
    )
    main()
    with Session(get_engine()) as db:
        admin = db.scalar(select(Player).where(Player.nickname == "operator"))
        assert admin.is_admin and admin.password_hash.startswith("$argon2")
    with pytest.raises(SystemExit):
        main()
