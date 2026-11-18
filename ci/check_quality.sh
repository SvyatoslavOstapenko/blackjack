#!/usr/bin/env bash
set -euo pipefail

report_dir=${1:?Pass an absolute report directory outside the checkout}
case "$report_dir" in
    /*) ;;
    *) printf 'Report directory must be absolute.\n' >&2; exit 2 ;;
esac
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
ruff=/data/teamcity_agent/conf/lab6-tools/ruff
[[ $("$ruff" --version) == 'ruff 0.17.5' ]]
mkdir -p -- "$report_dir"
report=$report_dir/ruff.json
if "$ruff" check --no-cache --config ruff.toml \
    --output-format json app tests > "$report"; then
    result=0
else
    result=$?
fi
cat -- "$report"
printf '\nRUFF_EXIT=%s\n' "$result"
exit "$result"
