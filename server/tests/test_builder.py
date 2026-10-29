"""The real BlenderRunner, against a fake 'Blender' executable, so the command line and the
report-over-exit-code rule are checked without running Blender."""
import json
import stat
import sys
from pathlib import Path

from app.builder import BlenderRunner, build_command
from app.config import Settings

FAKE_BLENDER = """import os, sys
args = sys.argv[1:]
open(os.environ["ARGS_FILE"], "w").write(" ".join(args))
out = args[args.index("--out") + 1] if "--out" in args else ""
print("Blender 5.2 (fake)", flush=True)
mode = os.environ["MODE"]
if mode == "ok_report_exit1":
    open(os.path.join(out, "build_report.json"), "w").write('{"ok": true, "errors": [], "warnings": []}')
    open(os.path.join(out, "model.glb"), "w").write("glTF")
    sys.exit(1)
if mode == "bad_report_exit0":
    open(os.path.join(out, "build_report.json"), "w").write(
        '{"ok": false, "errors": ["custom op op_1: NameError"], "warnings": []}')
if mode == "no_report_exit0":
    print("Traceback: boom")
"""


def fake_executable(tmp_path, name, code):
    """A program that runs `code` with this Python: a shebang script, or a .cmd wrapper on Windows."""
    if sys.platform == "win32":
        script = tmp_path / f"{name}.py"
        script.write_text(code)
        exe = tmp_path / f"{name}.cmd"
        exe.write_text(f'@"{sys.executable}" "{script}" %*\n')
        return exe
    exe = tmp_path / name
    exe.write_text(f"#!{sys.executable}\n" + code)
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    return exe


def make(tmp_path, monkeypatch, mode):
    blender = fake_executable(tmp_path, "Blender", FAKE_BLENDER)
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
    p = lambda s: str(Path(s))  # noqa: E731  (native separators: \ on Windows)
    assert ship == [p("/B"), "-b", "--factory-startup", "--python", p("/r/blender/build_ship.py"), "--",
                    "--spec", p("/s.json"), "--out", p("/o")]
    assert crew == [p("/B"), "-b", "--python", p("/r/blender/build_crew.py"), "--", "--spec", p("/s.json"),
                    "--out", p("/o")]
    r, _ = make(tmp_path, monkeypatch, "bad_report_exit0")
    run(r, tmp_path, "crew")
    assert "--factory-startup" not in (tmp_path / "args.txt").read_text()
