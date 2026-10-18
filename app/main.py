"""Blackjack FastAPI application."""

import logging

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import check_database, get_session
from app.models import Player
from app.logging_config import configure_logging
from app.security import hash_password

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="БлэкДжек")


class Registration(BaseModel):
    nickname: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=8, max_length=128)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        check_database()
    except (SQLAlchemyError, RuntimeError) as exc:
        logger.exception("Database health check failed")
        raise HTTPException(
            status_code=503,
            detail="База данных недоступна",
        ) from exc

    return {"status": "ok"}


@app.post("/register", status_code=201)
def register(data: Registration, db: Session = Depends(get_session)):
    nickname = data.nickname.strip()
    if not nickname:
        raise HTTPException(status_code=422, detail="Пустой никнейм")

    player = Player(
        nickname=nickname,
        password_hash=hash_password(data.password),
    )
    db.add(player)

    try:
        db.commit()
        db.refresh(player)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Никнейм уже занят",
        ) from exc

    logger.info("Player registered: id=%s", player.id)

    return {
        "id": player.id,
        "nickname": player.nickname,
        "balance": player.balance,
    }


@app.get("/leaderboard")
def leaderboard(db: Session = Depends(get_session)):
    players = db.scalars(
        select(Player)
        .order_by(Player.balance.desc(), Player.nickname)
        .limit(10)
    ).all()

    return [
        {
            "nickname": player.nickname,
            "balance": player.balance,
            "rounds_played": player.rounds_played,
        }
        for player in players
    ]