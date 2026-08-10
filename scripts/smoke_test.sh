#!/usr/bin/env bash
# Smoke test a built pentool wheel before it goes anywhere (TestPyPI or PyPI).
#
# Installs the wheel from dist/ into a throwaway venv and checks that the
# package actually imports and the CLI entry point runs. This is the last
# line of defense against publishing a build that is broken at import time
# (e.g. missing package-data like *.tcss, broken dependency pin, etc.) — see
# memory/pentool-release-checklist.md.
set -euo pipefail

WHEEL="$(ls dist/*.whl | head -1)"
if [ -z "$WHEEL" ]; then
    echo "::error::No wheel found in dist/ — build step must run first."
    exit 1
fi

VENV_DIR="$(mktemp -d)/pentool-smoke-venv"
python -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet "$WHEEL"

echo "--- import check ---"
"$VENV_DIR/bin/python" -c "import pentool; print('pentool version:', pentool.__version__)"

echo "--- CLI check ---"
"$VENV_DIR/bin/pentool" --help > /dev/null

echo "Smoke test passed: $WHEEL imports and CLI runs."
