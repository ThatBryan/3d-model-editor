"""Runs the Blender builders (contract §4).

The one rule that matters: **the result is build_report.json, never the exit code** — Blender
exits 0 when a script raises. A missing or unreadable report is itself a failed build.
"""
from __future__ import annotations

import json
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Protocol

from .config import Settings

Log = Callable[[str], None]
STDOUT_TAIL = 60


class BuilderRunner(Protocol):
    def build(self, kind: str, spec_path: Path, out_dir: Path, log: Log) -> dict: ...


def failed_report(message: str) -> dict:
    return {"ok": False, "errors": [message], "warnings": [], "triangles": 0,
            "bounds_min": [0, 0, 0], "bounds_max": [0, 0, 0], "seconds": 0.0}


def read_report(out_dir: Path, exit_note: str = "") -> dict:
    path = out_dir / "build_report.json"
    if not path.exists():
        return failed_report(f"The builder wrote no build_report.json{exit_note}.")
    try:
        report = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return failed_report(f"build_report.json is unreadable ({e}){exit_note}.")
    if not isinstance(report, dict) or "ok" not in report:
        return failed_report(f"build_report.json has no 'ok' field{exit_note}.")
    report.setdefault("errors", [])
    report.setdefault("warnings", [])
    if report["ok"] and not (out_dir / "model.glb").exists():
        report["ok"] = False
        report["errors"] = list(report["errors"]) + ["Report says ok but model.glb is missing."]
    return report


def build_command(settings: Settings, kind: str, spec_path: Path, out_dir: Path) -> list[str]:
    cmd = [str(settings.blender), "-b"]
    if kind == "ship":
        cmd.append("--factory-startup")  # crew must NOT use it: MPFB2 is a user extension
    cmd += ["--python", str(settings.builder_script(kind)), "--",
            "--spec", str(spec_path), "--out", str(out_dir)]
    return cmd


class BlenderRunner:
    """The real one. A single lock: Blender is heavy, one build at a time."""

    lock = threading.Lock()

    def __init__(self, settings: Settings):
        self.settings = settings

    def build(self, kind: str, spec_path: Path, out_dir: Path, log: Log) -> dict:
        out_dir.mkdir(parents=True, exist_ok=True)
        stale = out_dir / "build_report.json"
        if stale.exists():
            stale.unlink()
        cmd = build_command(self.settings, kind, spec_path, out_dir)
        if not Path(cmd[0]).exists():
            return failed_report(f"Blender not found at {cmd[0]}.")
        if not self.settings.builder_script(kind).exists():
            return failed_report(f"Builder script missing: {self.settings.builder_script(kind)}.")
        if self.lock.locked():
            log("Waiting for another Blender build to finish…")
        with self.lock:
            log("$ " + " ".join(cmd))
            tail: deque[str] = deque(maxlen=STDOUT_TAIL)
            start = time.time()
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, errors="replace", cwd=str(self.settings.repo_root))
            timer = threading.Timer(self.settings.build_timeout_s, proc.kill)
            timer.start()
            try:
                assert proc.stdout is not None
                for line in proc.stdout:
                    tail.append(line.rstrip("\n"))
                code = proc.wait()
            finally:
                timer.cancel()
            took = time.time() - start
        for line in tail:
            log(line)
        timed_out = took >= self.settings.build_timeout_s
        if timed_out:
            return failed_report(f"Blender timed out after {self.settings.build_timeout_s:.0f} s.")
        report = read_report(out_dir, f" (Blender exit code {code})")
        log(f"Build {'ok' if report['ok'] else 'FAILED'} in {took:.1f} s (exit code {code}; "
            f"the report decides, not the exit code).")
        return report
