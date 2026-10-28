"""Two Unreal tests at once must not overlap: they import into one shared harness project, and
an overlap overwrites the other run's assets without any error."""
import threading

from app.config import Settings
from app.main import make_unreal_runner

FAKE = """#!/bin/bash
echo "start $1" >> "$TRACE"
sleep 0.4
echo "end $1" >> "$TRACE"
echo '{"ok": true, "checks": []}' > "$1/unreal_import_report.json"
"""


def test_unreal_runs_never_overlap(tmp_path, monkeypatch):
    (tmp_path / "unreal").mkdir()
    (tmp_path / "unreal" / "run_import_test.sh").write_text(FAKE)
    trace = tmp_path / "trace.txt"
    monkeypatch.setenv("TRACE", str(trace))
    run = make_unreal_runner(Settings(repo_root=tmp_path, data_dir=tmp_path / "data"))

    pkgs = [tmp_path / f"pkg{i}" for i in range(2)]
    for p in pkgs:
        p.mkdir()
    threads = [threading.Thread(target=run, args=(p, lambda _l: None)) for p in pkgs]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    events = [line.split()[0] for line in trace.read_text().splitlines()]
    assert events == ["start", "end", "start", "end"], events
