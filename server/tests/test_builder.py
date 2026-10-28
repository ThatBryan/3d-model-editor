"""The real BlenderRunner, against a fake 'Blender' executable, so the command line and the
report-over-exit-code rule are checked without running Blender."""
import json
import stat
from pathlib import Path

from app.builder import BlenderRunner, build_command
from app.config import Settings

FAKE_BLENDER = """#!/bin/bash
echo "$@" > "$ARGS_FILE"
out=""
while [ $# -gt 0 ]; do [ "$1" == "--out" ] && out="$2"; shift; done
echo "Blender 5.2 (fake)"
case "$MODE" in
  ok_report_exit1) echo '{"ok": true, "errors": [], "warnings": []}' > "$out/build_report.json"; printf glTF > "$out/model.glb"; exit 1;;
  bad_report_exit0) echo '{"ok": false, "errors": ["custom op op_1: NameError"], "warnings": []}' > "$out/build_report.json"; exit 0;;
  no_report_exit0) echo "Traceback: boom"; exit 0;;
esac
"""


def make(tmp_path, monkeypatch, mode):
    blender = tmp_path / "Blender"
    blender.write_text(FAKE_BLENDER)
    blender.chmod(blender.stat().st_mode | stat.S_IEXEC)
    repo = tmp_path / "repo"
    (repo / "blender").mkdir(parents=True)
    (repo / "blender" / "build_ship.py").write_text("")
    (repo / "blender" / "build_crew.py").write_text("")
    monkeypatch.setenv("MODE", mode)
    monkeypatch.setenv("ARGS_FILE", str(tmp_path / "args.txt"))
    s = Settings(repo_root=repo, data_dir=tmp_path / "d", blender=blender)
    return BlenderRunner(s), s


def run(runner, tmp_path, kind="ship"):
    out = tmp_path / "out"
    spec = tmp_path / "spec.json"
    spec.write_text("{}")
    lines = []
    return runner.build(kind, spec, out, lines.append), lines


def test_exit_code_ignored_report_ok(tmp_path, monkeypatch):
    r, _ = make(tmp_path, monkeypatch, "ok_report_exit1")
    report, lines = run(r, tmp_path)
    assert report["ok"] is True
    assert any("Blender 5.2 (fake)" in l for l in lines)


def test_exit_zero_with_failed_report_is_failure(tmp_path, monkeypatch):
    r, _ = make(tmp_path, monkeypatch, "bad_report_exit0")
    report, _ = run(r, tmp_path)
    assert report["ok"] is False and report["errors"] == ["custom op op_1: NameError"]


def test_exit_zero_without_report_is_failure(tmp_path, monkeypatch):
    r, _ = make(tmp_path, monkeypatch, "no_report_exit0")
    report, lines = run(r, tmp_path)
    assert report["ok"] is False and "no build_report.json" in report["errors"][0]
    assert any("Traceback: boom" in l for l in lines)


def test_ship_uses_factory_startup_crew_does_not(tmp_path, monkeypatch):
    s = Settings(repo_root=Path("/r"), blender=Path("/B"))
    ship = build_command(s, "ship", Path("/s.json"), Path("/o"))
    crew = build_command(s, "crew", Path("/s.json"), Path("/o"))
    assert ship == ["/B", "-b", "--factory-startup", "--python", "/r/blender/build_ship.py", "--",
                    "--spec", "/s.json", "--out", "/o"]
    assert crew == ["/B", "-b", "--python", "/r/blender/build_crew.py", "--", "--spec", "/s.json", "--out", "/o"]
    r, _ = make(tmp_path, monkeypatch, "bad_report_exit0")
    run(r, tmp_path, "crew")
    assert "--factory-startup" not in (tmp_path / "args.txt").read_text()
