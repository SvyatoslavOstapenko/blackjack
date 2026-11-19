from pathlib import Path

from alembic import context, op


revision = "001_max_balance"
down_revision = "000_baseline"
branch_labels = None
depends_on = None


def execute_script(name):
    path = Path(__file__).resolve().parents[1] / "sql" / name
    sql = path.read_text(encoding="utf-8")
    if context.is_offline_mode():
        op.execute(sql)
    else:
        op.get_bind().exec_driver_sql(
            sql, execution_options={"no_parameters": True}
        )


def upgrade():
    execute_script("001_max_balance.sql")


def downgrade():
    execute_script("001_max_balance.down.sql")
