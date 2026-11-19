import os
import re
import subprocess
import sys
from pathlib import Path

import pglast
from pglast import ast, enums, parser
from pglast.visitors import Visitor


class SqlPolicy(Visitor):
    def __init__(self):
        super().__init__()
        self.violations = set()

    def visit_CopyStmt(self, ancestors, node):
        if node.filename is not None or node.is_program:
            self.violations.add(("BJ001", "COPY must not access a server file or PROGRAM"))

    def visit_GrantStmt(self, ancestors, node):
        is_public = any(
            role.roletype == enums.RoleSpecType.ROLESPEC_PUBLIC
            for role in node.grantees
        )
        if node.is_grant and is_public:
            self.violations.add(("BJ002", "GRANT to PUBLIC is not allowed"))

    def visit_TruncateStmt(self, ancestors, node):
        self.violations.add(("BJ003", "TRUNCATE is not allowed in tracked SQL"))

    def visit_DeleteStmt(self, ancestors, node):
        if node.whereClause is None:
            self.violations.add(("BJ004", "DELETE must have a WHERE clause"))

    def visit_DropStmt(self, ancestors, node):
        if node.behavior == enums.DropBehavior.DROP_CASCADE:
            self.violations.add(("BJ005", "DROP ... CASCADE is not allowed"))

    def visit_AlterTableCmd(self, ancestors, node):
        if node.behavior == enums.DropBehavior.DROP_CASCADE:
            self.violations.add(("BJ005", "ALTER TABLE ... CASCADE is not allowed"))

    def visit_CreateFunctionStmt(self, ancestors, node):
        if any(option.defname == "security" and isinstance(option.arg, ast.Boolean)
               and option.arg.boolval for option in node.options or ()):
            self.violations.add(("BJ006", "SECURITY DEFINER is not allowed"))


def sql_files():
    if not Path(".git").exists():
        files = []
        for directory, folders, names in os.walk("."):
            folders[:] = [
                folder for folder in folders
                if not folder.startswith(".")
                and folder not in {"logs", "node_modules", "venv"}
            ]
            files.extend(
                Path(directory, filename) for filename in names
                if filename.endswith(".sql")
            )
        return sorted(files)
    result = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "*.sql"],
        check=True, capture_output=True,
    )
    return sorted({Path(name) for name in result.stdout.decode("utf-8").split("\0") if name})


def read_sql(path):
    if not path.is_file() or path.is_symlink():
        raise ValueError("expected a regular SQL file")
    source = path.read_text(encoding="utf-8-sig")
    if path.parent == Path("db/schema") and source.startswith("--\n-- PostgreSQL database dump\n--\n"):
        # pg_dump's randomized psql guard is framing. Never skip other psql directives.
        start = re.search(r"\A--\n-- PostgreSQL database dump\n--\n\n\\restrict ([A-Za-z0-9]+)\n", source)
        if start:
            end = re.search(r"\n\\unrestrict " + re.escape(start[1]) + r"\n*\Z", source)
            if not end:
                raise ValueError("unmatched pg_dump restrict guard")
            source = "\n" * source[:start.end()].count("\n") + source[start.end():end.start()]
    return source


def check_file(path):
    try:
        source = read_sql(path)
        statements = parser.parse_sql(source)
        if not statements:
            raise ValueError("no SQL statements")
    except (OSError, ValueError, parser.ParseError) as error:
        print(f"{path}: BJ000 {error}")
        return 1

    violations = 0
    for index, statement in enumerate(statements, start=1):
        policy = SqlPolicy()
        policy(statement)
        for code, reason in sorted(policy.violations):
            print(f"{path}: statement {index}: {code} {reason}")
            violations += 1
    if not violations:
        print(f"{path}: PASS ({len(statements)} statements)")
    return violations


def main():
    version = parser.get_postgresql_version()
    print(f"pglast {pglast.__version__}, PostgreSQL grammar {'.'.join(map(str, version))}")
    paths = [Path(name) for name in sys.argv[1:]] or sql_files()
    if not paths:
        print("BJ000 no SQL files found")
        return 1
    violations = sum(check_file(path) for path in paths)
    print(f"SQL files: {len(paths)} | violations: {violations}")
    return int(violations > 0)


if __name__ == "__main__":
    sys.exit(main())
