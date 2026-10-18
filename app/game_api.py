"""Authenticated Blackjack game API."""

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_player
from app.db import get_session
from app.game import (
    build_deck, dealer_should_hit, hand_score,
    is_blackjack, settle,
)
from app.models import Card, Hand, Player, Round

router = APIRouter(prefix="/game", tags=["game"])
logger = logging.getLogger("app.game_api")


class BetRequest(BaseModel):
    bet: int = Field(gt=0)


class RoundRequest(BaseModel):
    round_id: int = Field(gt=0)


def locked_player(db: Session, player: Player) -> Player:
    return db.scalar(
        select(Player)
        .where(Player.id == player.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def get_owned_round(db: Session, player: Player, round_id: int):
    game_round = db.scalar(
        select(Round).where(
            Round.id == round_id,
            Round.player_id == player.id,
        )
    )
    if game_round is None:
        raise HTTPException(status_code=404, detail="Round not found")
    return game_round


def get_hands_and_cards(db: Session, round_id: int):
    hands = {
        hand.owner: hand
        for hand in db.scalars(
            select(Hand).where(Hand.round_id == round_id)
        ).all()
    }
    cards = {}
    for owner, hand in hands.items():
        cards[owner] = [
            (card.rank, card.suit)
            for card in db.scalars(
                select(Card)
                .where(Card.hand_id == hand.id)
                .order_by(Card.order_no)
            ).all()
        ]
    return hands, cards


def add_card(db, hand, cards, card):
    cards.append(card)
    db.add(
        Card(
            hand_id=hand.id,
            rank=card[0],
            suit=card[1],
            order_no=len(cards),
        )
    )
    hand.score = hand_score(cards)


def finish_round(game_round, player, player_cards, dealer_cards):
    player_score = hand_score(player_cards)
    dealer_score = hand_score(dealer_cards)

    if is_blackjack(player_cards):
        status = "push" if is_blackjack(dealer_cards) else "player_blackjack"
    elif is_blackjack(dealer_cards):
        status = "dealer_won"
    elif player_score > 21:
        status = "player_bust"
    elif dealer_score > 21:
        status = "dealer_bust"
    elif player_score > dealer_score:
        status = "player_won"
    elif player_score == dealer_score:
        status = "push"
    else:
        status = "dealer_won"

    payout = settle(player_cards, dealer_cards, game_round.bet)
    game_round.status = status
    game_round.payout = payout
    game_round.finished_at = datetime.now(timezone.utc)
    player.balance += payout
    player.rounds_played += 1

    logger.info(
        "Round %s finished: %s, payout=%s",
        game_round.id, status, payout,
    )


def dealer_turn(db, game_round, player, hands, cards):
    player_cards = cards["player"]
    dealer_cards = cards["dealer"]
    used = set(player_cards + dealer_cards)
    remaining = [card for card in build_deck() if card not in used]

    while dealer_should_hit(hand_score(dealer_cards)):
        add_card(db, hands["dealer"], dealer_cards, remaining.pop())

    finish_round(game_round, player, player_cards, dealer_cards)


def round_state(db, game_round, player):
    _, cards = get_hands_and_cards(db, game_round.id)
    player_cards = cards["player"]
    dealer_cards = cards["dealer"]
    finished = game_round.status != "in_progress"

    def present(items):
        return [{"rank": rank, "suit": suit} for rank, suit in items]

    return {
        "round_id": game_round.id,
        "status": game_round.status,
        "bet": game_round.bet,
        "payout": game_round.payout if finished else None,
        "balance": player.balance,
        "player_cards": present(player_cards),
        "player_score": hand_score(player_cards),
        "dealer_cards": present(
            dealer_cards if finished else dealer_cards[:1]
        ),
        "dealer_score": hand_score(dealer_cards) if finished else None,
    }


@router.post("/start", status_code=201)
def start_game(
    data: BetRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player)

    if data.bet % 2:
        raise HTTPException(status_code=422, detail="Bet must be even")

    active = db.scalar(
        select(Round.id).where(
            Round.player_id == player.id,
            Round.status == "in_progress",
        )
    )
    if active is not None:
        raise HTTPException(status_code=409, detail="Finish current round")

    if player.balance < data.bet:
        raise HTTPException(status_code=409, detail="Insufficient balance")

    player.balance -= data.bet
    game_round = Round(
        player_id=player.id,
        bet=data.bet,
        status="in_progress",
        payout=0,
    )
    db.add(game_round)
    db.flush()

    hands = {
        "player": Hand(
            round_id=game_round.id, owner="player", score=0,
        ),
        "dealer": Hand(
            round_id=game_round.id, owner="dealer", score=0,
        ),
    }
    db.add_all(hands.values())
    db.flush()

    cards = {"player": [], "dealer": []}
    deck = build_deck()

    for owner in ("player", "dealer", "player", "dealer"):
        add_card(db, hands[owner], cards[owner], deck.pop())

    if is_blackjack(cards["player"]) or is_blackjack(cards["dealer"]):
        finish_round(
            game_round, player, cards["player"], cards["dealer"]
        )

    db.commit()
    return round_state(db, game_round, player)


@router.post("/hit")
def hit(
    data: RoundRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player)
    game_round = get_owned_round(db, player, data.round_id)

    if game_round.status != "in_progress":
        raise HTTPException(status_code=409, detail="Round already finished")

    hands, cards = get_hands_and_cards(db, game_round.id)
    used = set(cards["player"] + cards["dealer"])
    remaining = [card for card in build_deck() if card not in used]

    add_card(db, hands["player"], cards["player"], remaining.pop())

    score = hand_score(cards["player"])
    if score > 21:
        finish_round(
            game_round, player, cards["player"], cards["dealer"]
        )
    elif score == 21:
        dealer_turn(db, game_round, player, hands, cards)

    db.commit()
    return round_state(db, game_round, player)


@router.post("/stand")
def stand(
    data: RoundRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player)
    game_round = get_owned_round(db, player, data.round_id)

    if game_round.status != "in_progress":
        raise HTTPException(status_code=409, detail="Round already finished")

    hands, cards = get_hands_and_cards(db, game_round.id)
    dealer_turn(db, game_round, player, hands, cards)

    db.commit()
    return round_state(db, game_round, player)


@router.get("/rounds")
def round_history(
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    rounds = db.scalars(
        select(Round)
        .where(Round.player_id == player.id)
        .order_by(Round.id.desc())
        .limit(20)
    ).all()
    return [
        {
            "round_id": item.id,
            "bet": item.bet,
            "status": item.status,
            "payout": item.payout,
        }
        for item in rounds
    ]


@router.get("/round/{round_id}")
def round_details(
    round_id: int,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    game_round = get_owned_round(db, player, round_id)
    return round_state(db, game_round, player)