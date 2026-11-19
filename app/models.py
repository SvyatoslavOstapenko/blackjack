from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Identity,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates


class Base(DeclarativeBase):
    pass


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)
    nickname: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    balance: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1000")
    )
    max_balance: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("1000")
    )
    rounds_played: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_players_balance"),
        CheckConstraint(
            "max_balance >= balance", name="ck_players_max_balance"
        ),
        CheckConstraint("rounds_played >= 0", name="ck_players_rounds_played"),
    )

    @validates("balance")
    def record_balance(self, _key: str, value: int) -> int:
        previous = self.max_balance
        self.max_balance = max(value, 0 if previous is None else previous)
        return value


class Round(Base):
    __tablename__ = "rounds"

    id: Mapped[int] = mapped_column(primary_key=True)
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id"), nullable=False, index=True
    )
    bet: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default=text("'in_progress'")
    )
    payout: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
    round_id: Mapped[int] = mapped_column(
        ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False
    )
    owner: Mapped[str] = mapped_column(String(10), nullable=False)
    score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )

    __table_args__ = (
        CheckConstraint(
            "owner IN ('player', 'dealer')", name="ck_hands_owner"
        ),
        CheckConstraint("score >= 0", name="ck_hands_score"),
        UniqueConstraint("round_id", "owner", name="uq_hands_round_owner"),
    )


class Card(Base):
    __tablename__ = "cards"

    id: Mapped[int] = mapped_column(primary_key=True)
    hand_id: Mapped[int] = mapped_column(
        ForeignKey("hands.id", ondelete="CASCADE"), nullable=False
    )
    rank: Mapped[str] = mapped_column(String(2), nullable=False)
    suit: Mapped[str] = mapped_column(String(1), nullable=False)
    order_no: Mapped[int] = mapped_column(Integer, nullable=False)

    __table_args__ = (
        UniqueConstraint("hand_id", "rank", "suit", name="uq_cards_hand_card"),
        UniqueConstraint("hand_id", "order_no", name="uq_cards_hand_order"),
        CheckConstraint("order_no > 0", name="ck_cards_order"),
    )


class ChipTransaction(Base):
    __tablename__ = "chip_transactions"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        Identity(),
        primary_key=True,
    )
    player_id: Mapped[int] = mapped_column(
        ForeignKey("players.id"), index=True
    )
    # Retain the historical identifier when a game is reversed and removed.
    round_id: Mapped[int | None]
    kind: Mapped[str] = mapped_column(String(16))
    delta: Mapped[int]
    balance_after: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "kind IN ('opening', 'stake', 'payout', 'credit', "
            "'reset', 'round_reversal')",
            name="ck_chip_transaction_kind",
        ),
        CheckConstraint(
            "balance_after >= 0", name="ck_chip_transaction_balance"
        ),
        CheckConstraint(
            "(kind IN ('opening', 'payout') AND delta >= 0) "
            "OR (kind = 'credit' AND delta > 0) "
            "OR (kind = 'stake' AND delta < 0) "
            "OR kind IN ('reset', 'round_reversal')",
            name="ck_chip_transaction_delta",
        ),
    )
