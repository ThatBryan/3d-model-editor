#!/bin/bash
# Import an me3d.package/1 into the throwaway UE 5.8 harness project and check it.
#
#   unreal/run_import_test.sh <package_dir>
#
# Writes <package_dir>/unreal_import_report.json (docs/CONTRACT.md section 9) plus
# unreal_import.log (the import process) and unreal_verify.log (the reload-and-check process).
#
# Exit code: 0 only when the report says "ok": true. Unreal's own exit code is ignored on
# purpose - UnrealEditor-Cmd exits 0 even when the Python inside it fails
# (library: unreal-automation-runner-exits-zero-on-failed-tests).
#
# Env: UE_ROOT (default /Users/Shared/Epic Games/UE_5.8), ME3D_UE_TIMEOUT seconds per phase (900).
set -u

if [ $# -ne 1 ] || [ ! -f "$1/manifest.json" ]; then
  echo "usage: $0 <package_dir>   (the folder holding manifest.json)" >&2
  exit 2
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
PKG="$(cd "$1" && pwd)"
PROJECT="$HERE/HarnessProject/Harness.uproject"
SCRIPT="$HERE/import_package.py"
UE_ROOT="${UE_ROOT:-/Users/Shared/Epic Games/UE_5.8}"
UE_CMD="$UE_ROOT/Engine/Binaries/Mac/UnrealEditor-Cmd"
TIMEOUT="${ME3D_UE_TIMEOUT:-900}"
REPORT="$PKG/unreal_import_report.json"
PY=/usr/bin/python3

if [ ! -x "$UE_CMD" ]; then
  echo "Unreal not found at $UE_CMD" >&2
  exit 3
fi

# Package id from the manifest; refuse anything that could escape Content/ME3D.
PKG_ID="$("$PY" -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$PKG/manifest.json" 2>/dev/null)"
case "$PKG_ID" in
  ""|*[!A-Za-z0-9_]*) echo "manifest id '$PKG_ID' is not [A-Za-z0-9_]+" >&2; PKG_ID="" ;;
esac

# Start from nothing: a stale report or stale assets must never pass for this run's result.
/bin/rm -f "$REPORT" "$PKG/.unreal_import_state.json" "$PKG/unreal_import.log" "$PKG/unreal_verify.log"
if [ -n "$PKG_ID" ]; then
  /bin/rm -rf "$HERE/HarnessProject/Content/ME3D/$PKG_ID"
fi

run_phase() {  # $1 = import|verify, $2 = log file
  local start=$SECONDS
  # perl alarm = a timeout that needs nothing from Homebrew; arch -arm64 so a Rosetta parent
  # (e.g. an x86 Python) cannot start the x86 slice (library: x86-python-launches-an-x86-unreal...)
  ME3D_PACKAGE="$PKG" ME3D_PHASE="$1" ME3D_IMPORT_LOG="$PKG/unreal_import.log" \
    /usr/bin/perl -e 'alarm shift; exec @ARGV or die "exec failed: $!"' "$TIMEOUT" \
    /usr/bin/arch -arm64 "$UE_CMD" "$PROJECT" -run=pythonscript -script="$SCRIPT" \
      -unattended -nullrhi -nosplash -NoSound -nop4 -SCCProvider=None -abslog="$2" \
      >/dev/null 2>&1
  local rc=$?
  echo "  $1 phase: $((SECONDS - start)) s (Unreal exit $rc, ignored)"
}

echo "Unreal import test: $PKG"
run_phase import "$PKG/unreal_import.log"
run_phase verify "$PKG/unreal_verify.log"
/bin/rm -f "$PKG/.unreal_import_state.json"

if [ ! -f "$REPORT" ]; then
  echo "FAIL: no report written - see $PKG/unreal_verify.log" >&2
  exit 1
fi

"$PY" - "$REPORT" <<'EOF'
import json, sys
r = json.load(open(sys.argv[1]))
checks = r.get("checks", [])
bad = [c for c in checks if not c.get("pass")]
print(f"{'PASS' if r.get('ok') else 'FAIL'}: {len(checks) - len(bad)}/{len(checks)} checks passed, "
      f"level {r.get('level')}, engine {r.get('engine_version', r.get('engine'))}")
for c in checks:
    print(f"  [{'ok' if c.get('pass') else 'XX'}] {c['name']}: {c.get('detail', '')}")
sys.exit(0 if r.get("ok") is True and checks and not bad else 1)
EOF
