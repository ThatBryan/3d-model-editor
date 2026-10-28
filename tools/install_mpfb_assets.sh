#!/usr/bin/env bash
# Install the CC0 MakeHuman system asset pack into MPFB2's user data folder, exactly as MPFB's own
# "Load pack from zip file" operator (mpfb.load_pack) does: check the zip with
# AssetService.check_asset_pack_zip, extract it into LocationService.get_user_data(), then refresh
# the asset lists. Idempotent: a stamp file holding the zip's sha256 is written into the user data
# folder, and a second run with the same zip does nothing.
#
# Usage: tools/install_mpfb_assets.sh [zip]          (default: vendor/downloads/makehuman_system_assets_cc0.zip)
# Fetch the zip first if it is missing:
#   curl -L -C - -o vendor/downloads/makehuman_system_assets_cc0.zip \
#     https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="${1:-$ROOT/vendor/downloads/makehuman_system_assets_cc0.zip}"
BLENDER="${BLENDER:-/Applications/Blender.app/Contents/MacOS/Blender}"
URL="https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip"

if [ ! -f "$ZIP" ]; then
  echo "missing $ZIP; downloading from $URL" >&2
  mkdir -p "$(dirname "$ZIP")"
  curl -L --retry 5 -C - -o "$ZIP" "$URL"
fi
unzip -tq "$ZIP" >/dev/null || { echo "zip is incomplete or corrupt: $ZIP (resume with curl -C -)" >&2; exit 1; }

SHA="$(shasum -a 256 "$ZIP" | cut -d' ' -f1)"
PY="$(mktemp -t mpfb_install).py"
trap 'rm -f "$PY"' EXIT
cat > "$PY" <<'EOF'
import bpy, importlib, os, sys, zipfile
argv = sys.argv[sys.argv.index("--") + 1:]
zip_path, sha = argv[0], argv[1]
try:
    importlib.import_module("bl_ext.blender_org.mpfb")
except ImportError:
    bpy.ops.preferences.addon_enable(module="bl_ext.blender_org.mpfb")
from bl_ext.blender_org.mpfb.services import LocationService, AssetService
data_dir = LocationService.get_user_data()
os.makedirs(data_dir, exist_ok=True)
stamp = os.path.join(data_dir, "packs", ".me3d_installed_makehuman_system_assets.sha256")
if os.path.exists(stamp) and open(stamp).read().strip() == sha and AssetService.system_assets_pack_is_installed():
    print("MPFB_INSTALL already installed in", data_dir)
    sys.exit(0)
check = AssetService.check_asset_pack_zip(zip_path)
if check is None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(data_dir)
else:
    err = AssetService.fix_and_extract_asset_pack_zip(zip_path, data_dir)
    if err is not None:
        print("MPFB_INSTALL failed:", check, err)
        sys.exit(1)
AssetService.update_all_asset_lists()
AssetService.invalidate_pack_metadata_cache()
if not AssetService.system_assets_pack_is_installed():
    print("MPFB_INSTALL failed: pack metadata not found after extract")
    sys.exit(1)
with open(stamp, "w") as f:
    f.write(sha + "\n")
print("MPFB_INSTALL installed into", data_dir)
EOF

RC=0
OUT="$("$BLENDER" -b --python "$PY" -- "$ZIP" "$SHA" 2>&1)" || RC=$?
echo "$OUT" | grep "MPFB_INSTALL" || true
if [ $RC -ne 0 ] || ! echo "$OUT" | grep -q "MPFB_INSTALL \(installed\|already\)"; then
  echo "$OUT" | tail -20 >&2
  exit 1
fi
