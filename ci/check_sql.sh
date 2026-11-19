#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
venv=$(mktemp -d)
trap 'rm -rf -- "$venv"' EXIT
python3 -m venv "$venv"
"$venv/bin/python" -m pip install --disable-pip-version-check -r ci/requirements-sql.txt
exec_status=0
"$venv/bin/python" ci/check_sql.py "$@" || exec_status=$?
printf 'SQL_CHECK_EXIT=%s\n' "$exec_status"
exit "$exec_status"
