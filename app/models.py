from datetime import datetime

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey,
    Integer, String, UniqueConstraint, func, text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    balance: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("1000"))
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_players_balance"),
        CheckConstraint("rounds_played >= 0", name="ck_players_rounds_played"),
    )


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), nullable=False, index=True)
    bet: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default=text("'in_progress'"))
    payout: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("bet > 0 AND bet % 2 = 0", name="ck_rounds_bet"),
        CheckConstraint("payout >= 0", name="ck_rounds_payout"),
        CheckConstraint(
            "status IN ('in_progress', 'player_won', 'dealer_won', "
            "'push', 'player_blackjack', 'player_bust', 'dealer_bust')",
            name="ck_rounds_status",
        ),
    )


class Hand(Base):
    __tablename__ = "hands"

    id: Mapped[int] = mapped_column(primary_key=True)
    round_id: Mapped[int] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
    owner: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        CheckConstraint("owner IN ('player', 'dealer')", name="ck_hands_owner"),
        CheckConstraint("score >= 0", name="ck_hands_score"),
        UniqueConstraint("round_id", "owner", name="uq_hands_round_owner"),
    )


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    hand_id: Mapped[int] = mapped_column(ForeignKey("hands.id", ondelete="CASCADE"), nullable=False)
    rank: Mapped[str] = mapped_column(String(2), nullable=False)
    suit: Mapped[str] = mapped_column(String(1), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("hand_id", "rank", "suit", name="uq_cards_hand_card"),
        UniqueConstraint("hand_id", "order_no", name="uq_cards_hand_order"),
        CheckConstraint("order_no > 0", name="ck_cards_order"),
    )