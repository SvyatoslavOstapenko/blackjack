import argparse
import io
import re

from alembic import command
from alembic.config import Config
from pglast import ast, parser


def sql_without_transaction(config, operation, revision):
    stream = io.StringIO()
    config.output_buffer = stream
    operation(config, revision, sql=True)
    output = stream.getvalue().strip()
    transaction = re.fullmatch(
        r"BEGIN;\s+(.*)\s+COMMIT;", output, flags=re.DOTALL
    )
    if not transaction:
        raise ValueError("Expected a single Alembic transaction")
    sql = transaction[1].strip()
    if any(
        isinstance(statement.stmt, ast.TransactionStmt)
        for statement in parser.parse_sql(sql)
    ):
        raise ValueError("Unexpected transaction command in migration")
    return sql


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("current", choices=("base", "000_baseline", "001_max_balance"))
    cli.add_argument("--adopt", action="store_true")
    args = cli.parse_args()
    if args.adopt and args.current == "base":
        cli.error("Only a known existing revision can be adopted")
    config = Config("alembic.ini")
    if args.adopt:
        print(sql_without_transaction(config, command.stamp, args.current))
    print(sql_without_transaction(config, command.upgrade, f"{args.current}:head"))


if __name__ == "__main__":
    main()
