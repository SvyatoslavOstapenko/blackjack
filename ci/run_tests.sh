#!/usr/bin/env bash
set -euo pipefail

build_number=${1:?Pass the numeric TeamCity build number}
if [[ ! $build_number =~ ^[0-9]+$ ]]; then
    printf 'Invalid build number: %s\n' "$build_number" >&2
    exit 2
fi

image="svyat06/blackjack:ci-$build_number"
mkdir -p -- logs
report_dir=$(mktemp -d "logs/lab7-$build_number.XXXXXX")
report="$report_dir/pytest.xml"

container=$(docker create \
    --entrypoint /bin/sh \
    --workdir /app \
    --env TEST_POSTGRES_URL= \
    --env DATABASE_URL= \
    --env AUTH_SECRET= \
    --env APP_LOG_DIR=/tmp/blackjack-lab7-logs \
    "$image" -ec '
        python -m pip install --disable-pip-version-check --no-cache-dir -r requirements-dev.txt
        exec python -m pytest -q -p no:cacheprovider --junitxml=/tmp/lab7-pytest.xml tests
    ')
trap 'docker rm --force "$container" >/dev/null || printf "Could not remove the test container.\n" >&2' EXIT

attach_exit=0
docker start --attach "$container" || attach_exit=$?
state=$(docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' "$container")
read -r container_state test_exit <<< "$state"
if [[ $container_state != exited || ! $test_exit =~ ^[0-9]+$ ]]; then
    printf 'Test container did not finish (state: %s, attach exit: %s).\n' "$state" "$attach_exit" >&2
    exit 1
fi

printf 'TEST_CONTAINER_EXIT=%s\n' "$test_exit"
if ! docker cp "$container:/tmp/lab7-pytest.xml" "$report"; then
    printf 'The test container did not produce JUnit XML.\n' >&2
    if (( test_exit != 0 )); then
        exit "$test_exit"
    fi
    exit 1
fi

printf "##teamcity[importData type='junit' path='%s']\n" "$report"
printf "##teamcity[publishArtifacts '%s => automated-tests']\n" "$report"
if (( test_exit != 0 )); then
    exit "$test_exit"
fi
if (( attach_exit != 0 )); then
    exit "$attach_exit"
fi

python3 - "$report" <<'PY'
import sys
from xml.etree import ElementTree

cases = ElementTree.parse(sys.argv[1]).findall('.//testcase')
skipped = sum(case.find('skipped') is not None for case in cases)
print(f'Test cases: {len(cases)}, skipped: {skipped}')
if not cases or skipped:
    sys.exit('Expected a nonempty test run without skipped cases.')
PY
