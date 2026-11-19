from pathlib import Path

from alembic import context, op


revision = "002_chip_transactions"
down_revision = "001_max_balance"
branch_labels = None
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[1] / "sql/002_chip_transactions.sql"
    sql = path.read_text(encoding="utf-8")
    if context.is_offline_mode():
        op.execute(sql)
    else:
        op.get_bind().exec_driver_sql(
            sql, execution_options={"no_parameters": True}
        )


def downgrade():
    raise RuntimeError("Export and verify the chip ledger before removing it")
