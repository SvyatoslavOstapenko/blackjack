"""Signed, expiring authentication tokens."""

import os

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Player

bearer = HTTPBearer(auto_error=False)
TOKEN_LIFETIME_SECONDS = 8 * 60 * 60


def token_serializer():
    secret = os.environ.get("AUTH_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("AUTH_SECRET must contain at least 32 characters")
    return URLSafeTimedSerializer(secret, salt="blackjack-auth-v1")


def create_token(player_id: int) -> str:
    return token_serializer().dumps({"id": player_id})


def unauthorized():
    raise HTTPException(
        status_code=401,
        detail="Invalid or missing authentication token",
        headers={"WWW-Authenticate": "Bearer"},
    )


def get_current_player(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_session),
) -> Player:
    if credentials is None or credentials.scheme.lower() != "bearer":
        unauthorized()

    try:
        payload = token_serializer().loads(
            credentials.credentials,
            max_age=TOKEN_LIFETIME_SECONDS,
        )
    except BadSignature:
        unauthorized()

    if not isinstance(payload, dict):
        unauthorized()

    player_id = payload.get("id")
    if type(player_id) is not int or player_id <= 0:
        unauthorized()

    player = db.get(Player, player_id)
    if player is None:
        unauthorized()

    return player