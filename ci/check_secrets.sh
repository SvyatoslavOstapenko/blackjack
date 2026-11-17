#!/usr/bin/env bash
set -euo pipefail

report_dir=${1:?Pass an absolute report directory outside the checkout}
case "$report_dir" in
    /*) ;;
    *) printf 'Report directory must be absolute.\n' >&2; exit 2 ;;
esac
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
gitleaks=/data/teamcity_agent/conf/lab6-tools/gitleaks
[[ $("$gitleaks" version) == 8.30.1 ]]
mkdir -p -- "$report_dir"
if "$gitleaks" dir . --config .gitleaks.toml \
    --no-banner --no-color --redact=100 --ignore-gitleaks-allow \
    --report-format json --report-path "$report_dir/gitleaks.json"; then
    result=0
else
    result=$?
fi
printf 'GITLEAKS_EXIT=%s\n' "$result"
exit "$result"
