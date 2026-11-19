#!/usr/bin/env bash
set -euo pipefail

usage='Pass the verified host, Compose project, current schema, reference schema, SQL plan and optionally a backup directory'
[[ $# == 5 || $# == 6 ]] || { echo "$usage" >&2; exit 2; }
expected_host=$1
project=$2
previous=$3
reference=$4
plan=$5
backup_dir=${6:-}
[[ $expected_host =~ ^apzhc-(stage|prod)$ && $(hostname -s) == "$expected_host" ]]
[[ $project =~ ^[a-z0-9][a-z0-9_-]*$ ]]
if [[ $expected_host == apzhc-prod && -z $backup_dir ]]; then
    echo 'A verified backup is required before applying a plan on PROD.' >&2
    exit 2
fi

scripts=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec 9>"/run/lock/blackjack-$project-schema.lock"
flock -n 9
mapfile -t databases < <(docker ps --filter "label=com.docker.compose.project=$project" \
    --filter label=com.docker.compose.service=db --format '{{.ID}}')
[[ ${#databases[@]} == 1 ]]
db=${databases[0]}
actual=$(mktemp)
stopped_app=''
dump_schema() {
    docker exec "$db" sh -ec 'exec pg_dump --schema-only --no-owner --no-acl \
        -U "$POSTGRES_USER" -d "$POSTGRES_DB"' > "$actual"
}
compare() {
    python3 "$scripts/../ci/compare_schema.py" "$1" "$actual"
}
verify_revision() {
    local revision
    revision=$(docker exec "$db" sh -ec 'exec psql -XAt -v ON_ERROR_STOP=1 \
        -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
        -c "SELECT version_num FROM public.alembic_version"')
    [[ $revision == 002_chip_transactions ]]
}
cleanup() {
    local status=$?
    if (( status != 0 )) && [[ -n $stopped_app ]]; then
        if dump_schema && compare "$previous" >/dev/null; then
            docker start "$stopped_app" >/dev/null || true
        else
            printf '%s\n' 'Previous application remains stopped after schema changed.' >&2
        fi
    fi
    rm -f -- "$actual"
    exit "$status"
}
trap cleanup EXIT

dump_schema
if compare "$reference"; then
    verify_revision
    printf 'ALREADY_AT_REFERENCE=%s\n' "$expected_host"
    exit 0
fi
compare "$previous"
[[ -s $plan ]]
mapfile -t apps < <(docker ps --filter "label=com.docker.compose.project=$project" \
    --filter label=com.docker.compose.service=app --format '{{.ID}}')
[[ ${#apps[@]} -le 1 ]]
if [[ ${#apps[@]} == 1 ]]; then
    docker stop "${apps[0]}" >/dev/null
    stopped_app=${apps[0]}
fi
dump_schema
compare "$previous" >/dev/null
if [[ -n $backup_dir ]]; then
    bash "$scripts/backup_postgres.sh" "$project" "$backup_dir"
fi

# The plan contains no transaction commands and is executed as one transaction.
docker exec -i "$db" sh -ec 'exec psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" \
    -d "$POSTGRES_DB" --single-transaction --file=-' < "$plan"
dump_schema
compare "$reference"
verify_revision
printf 'SCHEMA_PROMOTED=%s\n' "$expected_host"
