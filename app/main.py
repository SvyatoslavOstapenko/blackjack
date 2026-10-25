"""Blackjack FastAPI application."""

import logging

from fastapi import Depends, FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import check_database, get_session
from app.models import Player
from app.logging_config import configure_logging
from app.security import hash_password, verify_password
from app.auth import create_token, get_current_player
from app.game_api import router as game_router

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="БлэкДжек")
app.include_router(game_router)


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
def leaderboard(limit: int = Query(default=10, ge=1, le=10), db: Session = Depends(get_session)):
    players = db.scalars(
        select(Player)
        .order_by(Player.balance.desc(), Player.nickname)
        .limit(limit)
    ).all()

    return [
        {
            "nickname": player.nickname,
            "balance": player.balance,
            "rounds_played": player.rounds_played,
        }
        for player in players
    ]

class LoginRequest(BaseModel):
    nickname: str = Field(min_length=1, max_length=32)
    password: str


@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_session)):
    player = db.scalar(
        select(Player).where(Player.nickname == data.nickname)
    )

    if player is None or not verify_password(
        data.password, player.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Неверный никнейм или пароль",
        )

    return {
        "access_token": create_token(player.id),
        "token_type": "bearer",
    }


@app.get("/me")
def get_profile(player: Player = Depends(get_current_player)):
    return {
        "id": player.id,
        "nickname": player.nickname,
        "balance": player.balance,
        "rounds_played": player.rounds_played,
    }