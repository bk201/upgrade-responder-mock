#!/usr/bin/env bash
# Trigger a Harvester version sync, wait for its upgrade check to reach the
# mock, then show the request and the Versions. Each command is printed
# before it runs.
set -euo pipefail

TIMEOUT=${TIMEOUT:-300}

run() {
    echo "+ $*" >&2
    "$@"
}

# Only log lines after the restart count, so an earlier sync doesn't match.
START=$(date -u +%Y-%m-%dT%H:%M:%SZ)

run kubectl -n harvester-system rollout restart deploy/harvester
run kubectl -n harvester-system rollout status deploy/harvester

echo "+ until kubectl -n upgrade-mock logs deploy/upgrade-mock --since-time=$START | grep -q 'upgrade check'; do sleep 5; done" >&2
deadline=$((SECONDS + TIMEOUT))
until kubectl -n upgrade-mock logs deploy/upgrade-mock --since-time="$START" | grep -q 'upgrade check'; do
    if ((SECONDS >= deadline)); then
        echo "no upgrade check reached the mock within ${TIMEOUT}s; check upgrade-checker-enabled and upgrade-checker-url" >&2
        exit 1
    fi
    sleep 5
done

echo "+ kubectl -n upgrade-mock logs deploy/upgrade-mock --since-time=$START | grep 'upgrade check'" >&2
kubectl -n upgrade-mock logs deploy/upgrade-mock --since-time="$START" | grep 'upgrade check'
run kubectl -n harvester-system get versions.harvesterhci.io --show-labels
