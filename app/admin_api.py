"""Управление игроками и исправление ошибочных раздач."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.auth import get_current_player
from app.db import get_session
from app.game_api import (
    MAX_BALANCE,
    get_owned_round,
    locked_player,
    pending_payout,
    round_state,
)
from app.models import Card, Hand, Player, Round

router = APIRouter(prefix="/admin", tags=["admin"])


def get_admin(player: Player = Depends(get_current_player)) -> Player:
    if not player.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Этот раздел доступен только администратору.",
        )
    return player


def profile(player):
    return {
        "id": player.id,
        "nickname": player.nickname,
        "balance": player.balance,
        "max_balance": player.max_balance,
        "rounds_played": player.rounds_played,
        "is_admin": player.is_admin,
    }


def target_player(db, player_id, *, read=False):
    target = db.get(Player, player_id)
    if target is None:
        raise HTTPException(
            status_code=404, detail="Игрок не найден. Обновите список."
        )
    return locked_player(db, target, read=read)


class CreditRequest(BaseModel):
    amount: int = Field(strict=True, gt=0, le=MAX_BALANCE)


@router.get("/players")
def players(
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: Player = Depends(get_admin),
    db: Session = Depends(get_session),
):
    return [
        profile(p)
        for p in db.scalars(
            select(Player).order_by(Player.id).offset(offset).limit(limit)
        )
    ]


@router.post("/players/{player_id}/credit")
def credit(
    player_id: int,
    data: CreditRequest,
    admin: Player = Depends(get_admin),
    db: Session = Depends(get_session),
):
    target = target_player(db, player_id)
    if (
        target.balance + data.amount + pending_payout(db, player_id)
        > MAX_BALANCE
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Превышен предел баланса с учётом возможной выплаты. "
                "Уменьшите начисление или завершите раздачу."
            ),
        )
    target.balance += data.amount
    db.flush()
    result = profile(target)
    db.commit()
    return result


@router.post("/players/{player_id}/reset")
def reset(
    player_id: int,
    admin: Player = Depends(get_admin),
    db: Session = Depends(get_session),
):
    target = target_player(db, player_id)
    active = db.scalar(
        select(Round.id).where(
            Round.player_id == target.id,
            Round.status == "in_progress",
        )
    )
    if active is not None:
        raise HTTPException(
            status_code=409, detail="Игрок должен сначала завершить раздачу."
        )
    target.balance = 1000
    db.flush()
    result = profile(target)
    db.commit()
    return result


@router.get("/players/{player_id}/rounds")
def rounds(
    player_id: int,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    admin: Player = Depends(get_admin),
    db: Session = Depends(get_session),
):
    target = target_player(db, player_id, read=True)
    items = db.scalars(
        select(Round)
        .where(
            Round.player_id == player_id,
            Round.status != "in_progress",
        )
        .order_by(Round.id.desc())
        .offset(offset)
        .limit(limit)
    )
    return [round_state(db, item, target) for item in items]


@router.delete("/rounds/{round_id}")
def remove_round(
    round_id: int,
    admin: Player = Depends(get_admin),
    db: Session = Depends(get_session),
):
    player_id = db.scalar(select(Round.player_id).where(Round.id == round_id))
    if player_id is None:
        raise HTTPException(
            status_code=404, detail="Раздача не найдена. Обновите историю."
        )
    target = target_player(db, player_id)
    item = get_owned_round(db, target, round_id)
    if item.status == "in_progress":
        raise HTTPException(
            status_code=409, detail="Нельзя удалить незавершённую раздачу."
        )
    balance = target.balance + item.bet - item.payout
    if not 0 <= balance <= MAX_BALANCE:
        raise HTTPException(
            status_code=409,
            detail=(
                "Невозможно отменить выплату при текущем балансе. "
                "Сначала скорректируйте баланс."
            ),
        )
    if balance + pending_payout(db, player_id) > MAX_BALANCE:
        raise HTTPException(
            status_code=409,
            detail=(
                "Отмена раздачи превысит предел баланса с учётом активной "
                "руки. Сначала завершите текущую раздачу."
            ),
        )
    hand_ids = select(Hand.id).where(Hand.round_id == item.id)
    db.execute(delete(Card).where(Card.hand_id.in_(hand_ids)))
    db.execute(delete(Hand).where(Hand.round_id == item.id))
    db.delete(item)
    target.balance = balance
    target.rounds_played = max(0, target.rounds_played - 1)
    db.flush()
    result = {
        "message": "Раздача удалена, её ставка и выплата отменены.",
        "player": profile(target),
    }
    db.commit()
    return result
