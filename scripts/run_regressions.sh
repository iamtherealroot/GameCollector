#!/usr/bin/env bash
set -Eeuo pipefail
cd "$(dirname "$0")/.."
for test in scripts/test_*.py; do
    python3 "$test"
done
python3 scripts/release_smoke.py
python3 scripts/integration_smoke.py
python3 -m compileall -q app
echo 'Regressionstests erfolgreich.'
