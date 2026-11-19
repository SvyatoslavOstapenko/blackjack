#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
output=${1:?Pass a build-specific absolute output directory}
[[ $output == /* ]]
mkdir -p -- "$output"
tmp=$(mktemp -d)
tag="lab8-schema-$(basename -- "$tmp" | tr '[:upper:].' '[:lower:]-')"
fresh="$tag-fresh"
existing="$tag-existing"
cleanup() {
    docker rm -f -v "$fresh" "$existing" >/dev/null 2>&1 || true
    rm -rf -- "$tmp"
}
trap cleanup EXIT
python3 -m venv "$tmp/venv"
python="$tmp/venv/bin/python"
"$python" -m pip install --disable-pip-version-check -r ci/requirements-sql.txt -r requirements-migrations.txt
"$python" ci/render_migration.py base > "$tmp/fresh.sql"
"$python" ci/render_migration.py 001_max_balance --adopt > "$tmp/upgrade.sql"
"$python" ci/render_migration.py 000_baseline --adopt > "$tmp/prod-from-baseline.sql"
cmp -- "$tmp/upgrade.sql" migrations/plans/stage.sql
cmp -- "$tmp/prod-from-baseline.sql" migrations/plans/prod_from_baseline.sql

psql_db() {
    local container=$1
    shift
    docker exec -i "$container" psql -qX -v ON_ERROR_STOP=1 -U postgres -d blackjack_verify "$@"
}
for container in "$fresh" "$existing"; do
    docker run -d --name "$container" --network none -e POSTGRES_HOST_AUTH_METHOD=trust \
        -e POSTGRES_DB=blackjack_verify postgres:16-bookworm >/dev/null
    deadline=$((SECONDS + 40))
    until docker exec "$container" pg_isready -q -h 127.0.0.1 -U postgres -d blackjack_verify; do
        [[ $(docker inspect -f '{{.State.Running}}' "$container") == true ]]
        sleep 1
        (( SECONDS < deadline ))
    done
done
psql_db "$fresh" --single-transaction --file=- < "$tmp/fresh.sql"
psql_db "$existing" --single-transaction --file=- < db/schema/001_max_balance.sql
psql_db "$existing" -c "INSERT INTO public.players(nickname, password_hash, balance) VALUES ('lab8-contract', 'fixture', 1430)"
psql_db "$existing" --single-transaction --file=- < "$tmp/upgrade.sql"

for container in "$fresh" "$existing"; do
    revision=$(psql_db "$container" -At -c 'SELECT version_num FROM public.alembic_version')
    [[ $revision == 002_chip_transactions ]]
    docker exec "$container" pg_dump --schema-only --no-owner --no-acl -U postgres -d blackjack_verify > "$tmp/$container.sql"
    "$python" ci/compare_schema.py db/schema/blackjack.sql "$tmp/$container.sql"
done
opening=$(psql_db "$existing" -At -c "SELECT balance_after FROM public.chip_transactions WHERE kind='opening'")
[[ $opening == 1430 ]]
cp -- "$tmp/$existing.sql" "$output/test-reference.sql"
cp -- "$tmp/upgrade.sql" "$output/stage-upgrade.sql"
cp -- "$tmp/prod-from-baseline.sql" "$output/prod-from-baseline.sql"
printf 'MIGRATION_CONTRACT_OK revision=%s preserved_balance=%s\n' "$revision" "$opening"
