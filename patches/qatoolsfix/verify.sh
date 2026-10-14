#!/usr/bin/env bash
# Runs inside the patched image after build. Non-zero exit fails the build.
#
# Regression test: with a recon-all.log that has none of the expected lines,
# the unpatched function raises UnboundLocalError; the patched one returns NaNs.
set -euo pipefail

TARGET=/usr/local/tools/freesurfer/python/packages/qatoolspython/checkTopology.py
FSPYTHON=/usr/local/tools/freesurfer/python/bin/python3

test -f "$TARGET.orig"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/subj/scripts"
: > "$tmp/subj/scripts/recon-all.log"

"$FSPYTHON" - "$TARGET" "$tmp" <<'EOF'
import importlib.util, math, sys
target, subjects_dir = sys.argv[1], sys.argv[2]
spec = importlib.util.spec_from_file_location("checkTopology", target)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
result = mod.checkTopology(subjects_dir, "subj")
assert len(result) == 6 and all(math.isnan(float(x)) for x in result), result
print("checkTopology on empty log returned NaNs as expected")
EOF
