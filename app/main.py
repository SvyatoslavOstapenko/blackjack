"""Blackjack FastAPI application."""

import logging
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
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
from app.admin_api import profile
from app.admin_api import router as admin_router

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="БлэкДжек")
app.include_router(game_router)
app.include_router(admin_router)
ROOT = Path(__file__).resolve().parent
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
templates = Jinja2Templates(directory=ROOT / "templates")


@app.middleware("http")
async def response_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path not in ("/docs", "/redoc", "/docs/oauth2-redirect"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
        )
    if not request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logger.error("Database request failed: %s", type(exc).__name__)
    return JSONResponse(
        status_code=503,
        content={
            "detail": (
                "База данных временно недоступна. Повторите запрос позже."
            ),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    field = str(exc.errors()[0]["loc"][-1])
    password_min = 8 if request.url.path == "/register" else 1
    limit_max = 10 if request.url.path == "/leaderboard" else 100
    messages = {
        "nickname": "Введите никнейм длиной от 1 до 32 символов.",
        "password": (
            f"Введите пароль длиной от {password_min} до 128 символов."
        ),
        "bet": "Введите положительную чётную целую ставку не больше баланса.",
        "amount": (
            "Введите положительное целое количество фишек "
            "в допустимом диапазоне."
        ),
        "round_id": "Укажите положительный целый номер раздачи.",
        "limit": (
            f"Размер списка должен быть целым числом от 1 до {limit_max}."
        ),
        "offset": "Смещение списка должно быть неотрицательным целым числом.",
    }
    return JSONResponse(
        status_code=422,
        content={
            "detail": messages.get(
                field, "Проверьте поля формы и повторите запрос."
            ),
        },
    )


@app.get("/", include_in_schema=False)
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


class Registration(BaseModel):
    nickname: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=8, max_length=128)


@app.get("/health")
def health() -> dict[str, str]:
    try:
        check_database()
    except (SQLAlchemyError, RuntimeError) as exc:
        logger.error("Database health check failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=503,
            detail="База данных недоступна",
        ) from exc

    return {"status": "ok"}


@app.post("/register", status_code=201)
def register(data: Registration, db: Session = Depends(get_session)):
    nickname = data.nickname.strip()
    if not nickname or any(ord(c) < 32 for c in nickname):
        raise HTTPException(
            status_code=422,
            detail="Введите непустой никнейм без управляющих символов.",
        )

    player = Player(
        nickname=nickname,
        password_hash=hash_password(data.password),
    )
    db.add(player)

    try:
        db.flush()
        result = {
            "id": player.id,
            "nickname": player.nickname,
            "balance": player.balance,
        }
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Никнейм уже занят. Выберите другой.",
        ) from exc

    logger.info("Player registered: id=%s", result["id"])
    return result


@app.get("/leaderboard")
def leaderboard(
    limit: int = Query(default=10, ge=1, le=10),
    db: Session = Depends(get_session),
):
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
    password: str = Field(min_length=1, max_length=128)


@app.post("/login")
def login(data: LoginRequest, db: Session = Depends(get_session)):
    player = db.scalar(
        select(Player).where(Player.nickname == data.nickname.strip())
    )

    if player is None or not verify_password(
        data.password, player.password_hash
    ):
        raise HTTPException(
            status_code=401,
            detail="Неверный никнейм или пароль. Проверьте ввод.",
        )

    return {
        "access_token": create_token(player.id),
        "token_type": "bearer",
    }


@app.get("/me")
def get_profile(player: Player = Depends(get_current_player)):
    return profile(player)
