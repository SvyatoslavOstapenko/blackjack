"""Authenticated Blackjack game API."""

from datetime import datetime, timezone
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_player
from app.chips import record_chip_change
from app.db import get_session
from app.game import (
    build_deck,
    dealer_should_hit,
    hand_score,
    is_blackjack,
    settle,
)
from app.models import Card, Hand, Player, Round

router = APIRouter(prefix="/game", tags=["game"])
logger = logging.getLogger("app.game_api")
MAX_BALANCE = 2_147_483_647


class BetRequest(BaseModel):
    bet: int = Field(strict=True, gt=0, le=2_147_483_647)


class RoundRequest(BaseModel):
    round_id: int = Field(strict=True, gt=0)


def locked_player(db: Session, player: Player, *, read=False) -> Player:
    return db.scalar(
        select(Player)
        .where(Player.id == player.id)
        .with_for_update(read=read)
        .execution_options(populate_existing=True)
    )


def pending_payout(db: Session, player_id: int) -> int:
    bet = db.scalar(
        select(Round.bet).where(
            Round.player_id == player_id,
            Round.status == "in_progress",
        )
    )
    # Блэкджек завершается при раздаче. Для активной руки максимум — 2 ставки.
    return 2 * bet if bet is not None else 0


def get_owned_round(db: Session, player: Player, round_id: int):
    game_round = db.scalar(
        select(Round).where(
            Round.id == round_id,
            Round.player_id == player.id,
        )
    )
    if game_round is None:
        raise HTTPException(
            status_code=404,
            detail="Раздача не найдена. Откройте свою историю.",
        )
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


def finish_round(db, game_round, player, player_cards, dealer_cards):
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
    record_chip_change(db, player, "payout", payout, game_round.id)
    player.rounds_played += 1

    logger.info(
        "Round %s finished: %s, payout=%s",
        game_round.id,
        status,
        payout,
    )


def dealer_turn(db, game_round, player, hands, cards):
    player_cards = cards["player"]
    dealer_cards = cards["dealer"]
    used = set(player_cards + dealer_cards)
    remaining = [card for card in build_deck() if card not in used]

    while dealer_should_hit(hand_score(dealer_cards)):
        add_card(db, hands["dealer"], dealer_cards, remaining.pop())

    finish_round(db, game_round, player, player_cards, dealer_cards)


def round_state(db, game_round, player):
    _, cards = get_hands_and_cards(db, game_round.id)
    player_cards = cards["player"]
    dealer_cards = cards["dealer"]
    finished = game_round.status != "in_progress"

    def present(items):
        return [{"rank": rank, "suit": suit} for rank, suit in items]

    def timestamp(value):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    return {
        "round_id": game_round.id,
        "status": game_round.status,
        "bet": game_round.bet,
        "payout": game_round.payout if finished else None,
        "balance": player.balance,
        "max_balance": player.max_balance,
        "rounds_played": player.rounds_played,
        "player_cards": present(player_cards),
        "player_score": hand_score(player_cards),
        "dealer_cards": present(
            dealer_cards if finished else dealer_cards[:1]
        ),
        "dealer_score": hand_score(dealer_cards) if finished else None,
        "started_at": timestamp(game_round.started_at),
        "finished_at": timestamp(game_round.finished_at),
    }


@router.post("/start", status_code=201)
def start_game(
    data: BetRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player)

    if data.bet % 2:
        raise HTTPException(
            status_code=422,
            detail="Ставка должна быть чётной. Введите 2, 4, 6…",
        )

    active = db.scalar(
        select(Round.id).where(
            Round.player_id == player.id,
            Round.status == "in_progress",
        )
    )
    if active is not None:
        raise HTTPException(
            status_code=409, detail="Сначала завершите текущую раздачу."
        )

    if player.balance < data.bet:
        raise HTTPException(
            status_code=409, detail="Недостаточно фишек. Уменьшите ставку."
        )

    if player.balance + data.bet * 3 // 2 > MAX_BALANCE:
        raise HTTPException(
            status_code=422,
            detail=(
                "Возможная выплата превысит предел баланса. "
                "Уменьшите ставку."
            ),
        )

    player.balance -= data.bet
    game_round = Round(
        player_id=player.id,
        bet=data.bet,
        status="in_progress",
        payout=0,
    )
    db.add(game_round)
    db.flush()
    record_chip_change(db, player, "stake", -data.bet, game_round.id)

    hands = {
        "player": Hand(
            round_id=game_round.id,
            owner="player",
            score=0,
        ),
        "dealer": Hand(
            round_id=game_round.id,
            owner="dealer",
            score=0,
        ),
    }
    db.add_all(hands.values())
    db.flush()

    cards = {"player": [], "dealer": []}
    deck = build_deck()

    for owner in ("player", "dealer", "player", "dealer"):
        add_card(db, hands[owner], cards[owner], deck.pop())

    if is_blackjack(cards["player"]) or is_blackjack(cards["dealer"]):
        finish_round(db, game_round, player, cards["player"], cards["dealer"])

    db.flush()
    result = round_state(db, game_round, player)
    db.commit()
    return result


@router.post("/hit")
def hit(
    data: RoundRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player)
    game_round = get_owned_round(db, player, data.round_id)

    if game_round.status != "in_progress":
        raise HTTPException(
            status_code=409, detail="Раздача завершена. Начните новую."
        )

    hands, cards = get_hands_and_cards(db, game_round.id)
    used = set(cards["player"] + cards["dealer"])
    remaining = [card for card in build_deck() if card not in used]

    add_card(db, hands["player"], cards["player"], remaining.pop())

    score = hand_score(cards["player"])
    if score > 21:
        finish_round(db, game_round, player, cards["player"], cards["dealer"])
    elif score == 21:
        dealer_turn(db, game_round, player, hands, cards)

    db.flush()
    result = round_state(db, game_round, player)
    db.commit()
    return result


@router.post("/stand")
def stand(
    data: RoundRequest,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player)
    game_round = get_owned_round(db, player, data.round_id)

    if game_round.status != "in_progress":
        raise HTTPException(
            status_code=409, detail="Раздача завершена. Начните новую."
        )

    hands, cards = get_hands_and_cards(db, game_round.id)
    dealer_turn(db, game_round, player, hands, cards)

    db.flush()
    result = round_state(db, game_round, player)
    db.commit()
    return result


@router.get("/rounds")
def round_history(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player, read=True)
    rounds = db.scalars(
        select(Round)
        .where(Round.player_id == player.id, Round.status != "in_progress")
        .order_by(Round.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [round_state(db, item, player) for item in rounds]


@router.get("/active")
def active_round(
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player, read=True)
    current = db.scalar(
        select(Round).where(
            Round.player_id == player.id,
            Round.status == "in_progress",
        )
    )
    return round_state(db, current, player) if current else None


@router.get("/round/{round_id}")
def round_details(
    round_id: int,
    player: Player = Depends(get_current_player),
    db: Session = Depends(get_session),
):
    player = locked_player(db, player, read=True)
    game_round = get_owned_round(db, player, round_id)
    return round_state(db, game_round, player)
