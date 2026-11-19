#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 1 || ! $1 =~ ^ci-[0-9]+$ || $(hostname -s) != apzhc-stage ]]; then
    echo 'Expected the STAGE host and a numeric CI image tag.' >&2
    exit 2
fi
export STAGE_TAG=$1
compose=(
    /usr/bin/docker compose
    --project-directory /home/svyat/projects/blackjack
    --env-file /etc/blackjack-stage/runtime.env
    -p blackjack-lb3
    -f /etc/blackjack-stage/compose.yaml
    -f /etc/blackjack-stage/compose.stage.yaml
)
exec 8>/run/lock/blackjack-stage-release.lock
flock -n 8
scratch=$(mktemp -d)
app=''
cleanup() {
    [[ -z $app ]] || docker rm -v "$app" >/dev/null
    rm -rf -- "$scratch"
}
trap cleanup EXIT

"${compose[@]}" pull app
image=$("${compose[@]}" config --images | grep -Fx "svyat06/blackjack:$STAGE_TAG")
app=$(docker create --network none "$image")
plan=migrations/plans/stage.sql
if ! docker cp "$app:/app/$plan" "$scratch/stage.sql"; then
    echo 'The deployment image does not contain a verified stage migration plan.' >&2
    exit 1
fi
docker cp "$app:/app/db/schema/001_max_balance.sql" "$scratch/previous.sql"
docker cp "$app:/app/db/schema/blackjack.sql" "$scratch/reference.sql"
bash /etc/blackjack-stage/lab8/ops/apply_db_plan.sh apzhc-stage blackjack-lb3 \
    "$scratch/previous.sql" "$scratch/reference.sql" "$scratch/stage.sql"
"${compose[@]}" up -d --no-build --no-deps app
for attempt in {1..30}; do
    if curl -fsS --max-time 2 http://127.0.0.1:8000/health; then
        printf '\nSTAGE_DEPLOYED=%s\n' "$STAGE_TAG"
        exit 0
    fi
    sleep 1
done
echo 'The updated STAGE application did not become ready.' >&2
exit 1
