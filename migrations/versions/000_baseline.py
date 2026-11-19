from pathlib import Path
import re

from alembic import context, op


revision = "000_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    path = Path(__file__).resolve().parents[2] / "db/schema/000_baseline.sql"
    source = path.read_text(encoding="utf-8")
    sql = re.sub(r"(?m)^\\(?:un)?restrict [A-Za-z0-9]+\n", "", source)
    if context.is_offline_mode():
        op.execute(sql)
    else:
        op.get_bind().exec_driver_sql(
            sql, execution_options={"no_parameters": True}
        )


def downgrade():
    raise RuntimeError("The initial schema cannot be dropped by Alembic")
