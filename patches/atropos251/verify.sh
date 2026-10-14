#!/usr/bin/env bash
# Runs inside the patched image after build. Non-zero exit fails the build.
set -euo pipefail

ATROPOS=/usr/local/tools/ants/install/bin/Atropos

# The binary loads and runs (catches missing shared libraries).
"$ATROPOS" --help > /dev/null

# The original is kept alongside for comparison.
test -x "$ATROPOS.orig"
