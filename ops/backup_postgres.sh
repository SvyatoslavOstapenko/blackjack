#!/usr/bin/env bash
set -euo pipefail

project=${1:?Pass the verified Compose project}
backup_dir=${2:?Pass an absolute backup directory}
[[ $# == 2 && $project =~ ^[a-z0-9][a-z0-9_-]*$ && $backup_dir == /* ]]
umask 077
install -d -m 0700 -- "$backup_dir"
mapfile -t databases < <(docker ps --filter "label=com.docker.compose.project=$project" \
    --filter label=com.docker.compose.service=db --format '{{.ID}}')
[[ ${#databases[@]} == 1 ]]
db=${databases[0]}

archive=$(mktemp "$backup_dir/.blackjack-pending.XXXXXX")
trap 'rm -f -- "$archive"' EXIT
docker exec "$db" sh -ec '
    user=${POSTGRES_USER:-postgres}
    exec pg_dump --format=custom -U "$user" -d "${POSTGRES_DB:-$user}"
' > "$archive"
test -s "$archive"
catalog=$(docker exec -i "$db" pg_restore --list < "$archive")
for table in cards hands players rounds; do
    grep -q "TABLE DATA public $table " <<< "$catalog"
done
docker exec -i "$db" pg_restore --exit-on-error --file=/dev/null < "$archive"
final="$backup_dir/blackjack_$(date -u +%Y%m%dT%H%M%S%NZ).dump"
[[ ! -e $final ]]
mv -T -- "$archive" "$final"
printf 'BACKUP_READY=%s BYTES=%s SHA256=%s\n' "$final" "$(stat -c %s -- "$final")" \
    "$(sha256sum "$final" | cut -d' ' -f1)"
