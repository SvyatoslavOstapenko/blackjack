"""Deterministic integration tests for Blackjack game API."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Base, Card, Hand, Player, Round


def fixed_deck():
    ranks = ("2", "3", "4", "5", "6", "7", "8",
             "9", "10", "J", "Q", "K", "A")
    suits = ("S", "H", "D", "C")
    all_cards = [(rank, suit) for suit in suits for rank in ranks]

    # pop() deals from the end.
    tail = [
        ("3", "H"),
        ("2", "C"),
        ("9", "C"),
        ("7", "D"),
        ("6", "H"),
        ("10", "S"),
    ]
    return [card for card in all_cards if card not in tail] + tail


class GameApiTests(unittest.TestCase):

    def test_deterministic_hit_and_stand(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)

        def test_session():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_session] = test_session

        try:
            with (
                patch.dict(os.environ, {
                    "AUTH_SECRET": "deterministic-test-secret-" * 3
                }),
                patch("app.game_api.build_deck", side_effect=fixed_deck),
                TestClient(app) as client,
            ):
                for nickname in ("alice", "bob"):
                    response = client.post(
                        "/register",
                        json={
                            "nickname": nickname,
                            "password": "test-password-123",
                        },
                    )
                    self.assertEqual(response.status_code, 201, response.text)

                def login(nickname):
                    response = client.post(
                        "/login",
                        json={
                            "nickname": nickname,
                            "password": "test-password-123",
                        },
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    return {
                        "Authorization":
                        "Bearer " + response.json()["access_token"]
                    }

                alice = login("alice")
                bob = login("bob")

                for bet in (-2, 0, 101):
                    response = client.post(
                        "/game/start", json={"bet": bet}, headers=alice
                    )
                    self.assertEqual(response.status_code, 422)
                print("INVALID BETS: PASSED")

                response = client.post(
                    "/game/start", json={"bet": 100}, headers=alice
                )
                self.assertEqual(response.status_code, 201, response.text)
                state = response.json()
                first_id = state["round_id"]

                self.assertEqual(state["status"], "in_progress")
                self.assertEqual(state["player_score"], 17)
                self.assertEqual(state["balance"], 900)
                self.assertEqual(len(state["dealer_cards"]), 1)
                self.assertIsNone(state["dealer_score"])
                print("DETERMINISTIC START AND HIDDEN CARD: PASSED")

                response = client.post(
                    "/game/start", json={"bet": 100}, headers=alice
                )
                self.assertEqual(response.status_code, 409)
                print("SECOND ACTIVE ROUND BLOCKED: PASSED")

                response = client.get(
                    f"/game/round/{first_id}", headers=bob
                )
                self.assertEqual(response.status_code, 404)
                print("FOREIGN ROUND ACCESS BLOCKED: PASSED")

                response = client.post(
                    "/game/hit",
                    json={"round_id": first_id},
                    headers=alice,
                )
                self.assertEqual(response.status_code, 200, response.text)
                state = response.json()
                self.assertEqual(state["status"], "in_progress")
                self.assertEqual(state["player_score"], 19)
                self.assertEqual(len(state["player_cards"]), 3)
                print("HIT: PASSED")

                response = client.post(
                    "/game/stand",
                    json={"round_id": first_id},
                    headers=alice,
                )
                self.assertEqual(response.status_code, 200, response.text)
                state = response.json()

                self.assertEqual(state["status"], "player_won")
                self.assertEqual(state["dealer_score"], 18)
                self.assertEqual(state["payout"], 200)
                self.assertEqual(state["balance"], 1100)
                print("STAND AND WIN PAYOUT: PASSED")

                for endpoint in ("hit", "stand"):
                    response = client.post(
                        f"/game/{endpoint}",
                        json={"round_id": first_id},
                        headers=alice,
                    )
                    self.assertEqual(response.status_code, 409)
                print("REPEATED MOVES BLOCKED: PASSED")

                response = client.post(
                    "/game/start", json={"bet": 5000}, headers=alice
                )
                self.assertEqual(response.status_code, 409)
                print("INSUFFICIENT BALANCE: PASSED")

                response = client.post(
                    "/game/start", json={"bet": 100}, headers=alice
                )
                self.assertEqual(response.status_code, 201, response.text)
                state = response.json()
                second_id = state["round_id"]
                self.assertEqual(state["status"], "in_progress")
                self.assertEqual(state["balance"], 1000)

                response = client.post(
                    "/game/stand",
                    json={"round_id": second_id},
                    headers=alice,
                )
                self.assertEqual(response.status_code, 200, response.text)
                state = response.json()

                self.assertEqual(state["status"], "push")
                self.assertEqual(state["payout"], 100)
                self.assertEqual(state["balance"], 1100)
                print("STAND AND DRAW PAYOUT: PASSED")

                response = client.get("/game/rounds", headers=alice)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    [r["round_id"] for r in response.json()],
                    [second_id, first_id],
                )

                response = client.get("/game/rounds", headers=bob)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])
                print("PRIVATE HISTORY: PASSED")

            with Session(engine) as db:
                player = db.scalar(
                    select(Player).where(Player.nickname == "alice")
                )
                self.assertEqual(player.balance, 1100)
                self.assertEqual(player.rounds_played, 2)

                rounds = db.scalars(
                    select(Round).where(Round.player_id == player.id)
                ).all()
                self.assertEqual(len(rounds), 2)

                for game_round in rounds:
                    hands = db.scalars(
                        select(Hand).where(Hand.round_id == game_round.id)
                    ).all()
                    self.assertEqual(len(hands), 2)

                    all_cards = []
                    for hand in hands:
                        cards = db.scalars(
                            select(Card)
                            .where(Card.hand_id == hand.id)
                            .order_by(Card.order_no)
                        ).all()
                        self.assertEqual(
                            [card.order_no for card in cards],
                            list(range(1, len(cards) + 1)),
                        )
                        all_cards.extend(
                            (card.rank, card.suit) for card in cards
                        )

                    self.assertEqual(len(all_cards), len(set(all_cards)))

                print("DATABASE, CARD ORDER AND UNIQUENESS: PASSED")

            print("ALL DETERMINISTIC GAME TESTS PASSED")

        finally:
            app.dependency_overrides.pop(get_session, None)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()