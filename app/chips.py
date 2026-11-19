from app.models import ChipTransaction, Player


def record_chip_change(db, player: Player, kind: str, delta: int, round_id=None):
    db.add(
        ChipTransaction(
            player_id=player.id,
            round_id=round_id,
            kind=kind,
            delta=delta,
            balance_after=player.balance,
        )
    )
