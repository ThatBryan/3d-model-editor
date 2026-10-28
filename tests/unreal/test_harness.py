"""The Unreal import harness passes a good package AND fails a broken one.

The second half is the point: Unreal exits 0 on failure, so a harness that has only ever been
seen to pass proves nothing (library: unreal-automation-runner-exits-zero-on-failed-tests).

    server/.venv/bin/python -m pytest tests/unreal/test_harness.py -q
"""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "unreal" / "run_import_test.sh"
UE_CMD = Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor-Cmd")
BLENDER = Path("/Applications/Blender.app/Contents/MacOS/Blender")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_fixture_package  # noqa: E402

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not (UE_CMD.exists() and BLENDER.exists()), reason="needs UE 5.8 and Blender"),
]


@pytest.fixture(scope="module")
def good_package(tmp_path_factory):
    return make_fixture_package.make_package(tmp_path_factory.mktemp("unreal_pkg"))


def run_harness(pkg):
    proc = subprocess.run([str(RUN), str(pkg)], capture_output=True, text=True, timeout=3600)
    report = json.loads((pkg / "unreal_import_report.json").read_text())
    return proc, report, {c["name"]: c for c in report["checks"]}


def test_good_package_imports_and_passes(good_package):
    proc, report, checks = run_harness(good_package)
    assert report["ok"] is True, proc.stdout
    assert proc.returncode == 0, proc.stdout
    assert report["engine"] == "5.8"
    assert report["level"] == "/Game/ME3D/pkg_fixture_boat/L_pkg_fixture_boat"
    for name in ("manifest_valid", "ship_parts_imported", "ship_hierarchy", "level_save_reload",
                 "import_log_clean", "crew_shared_skeleton",
                 "articulated_part:Mast__Radar", "articulated_part:Deck__Crane",
                 "articulated_part:Deck__Crane__Jib",
                 "crew_skeleton:crew_worker", "crew_animation:crew_worker:idle",
                 "crew_animation:crew_worker_b:walk",
                 "crew_actor:0:station__helm", "crew_actor:1:station__crane"):
        assert checks[name]["pass"], (name, checks.get(name))
    assert "6 mesh nodes" in checks["ship_parts_imported"]["detail"]


def test_broken_package_fails_with_the_failing_checks_named(good_package, tmp_path):
    pkg = tmp_path / "pkg_fixture_boat_broken"
    shutil.copytree(good_package, pkg)
    for stale in pkg.glob("unreal_*"):
        stale.unlink()
    manifest = json.loads((pkg / "manifest.json").read_text())
    manifest["id"] = "pkg_fixture_boat_broken"
    manifest["crew"][0]["animation"] = "wave_hello"           # not a clip in the crew GLB
    manifest["crew"][1]["location_m"][1] += 0.05              # 5 cm off its station
    (pkg / "manifest.json").write_text(json.dumps(manifest, indent=1))
    art = json.loads((pkg / "ship" / "articulation.json").read_text())
    art.append({"part": "Deck__Ghost", "parent": "Hull__Main", "axis": "z", "min_deg": -90,
                "max_deg": 90, "priority": "P2", "pivot_m": [0, 0, 1.5]})  # not in the GLB
    (pkg / "ship" / "articulation.json").write_text(json.dumps(art, indent=1))

    proc, report, checks = run_harness(pkg)
    assert report["ok"] is False
    assert proc.returncode == 1, proc.stdout
    failed = {n for n, c in checks.items() if not c["pass"]}
    assert failed == {"crew_animation:crew_worker:wave_hello", "crew_actor:0:station__helm",
                      "articulated_part:Deck__Ghost", "crew_actor:1:station__crane"}, failed
    assert "not in the GLB" in checks["articulated_part:Deck__Ghost"]["detail"]
    assert "5.00 cm" in checks["crew_actor:1:station__crane"]["detail"]
    # the rest of the package still imported: the failure is specific, not a crash
    assert checks["articulated_part:Deck__Crane"]["pass"]
    assert checks["level_save_reload"]["pass"]
