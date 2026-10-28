"""End to end: the path Lester asked to be proven.

Create each default ship and the default male through the real server (real Blender builds),
put crew at stations on the ship, export the package, and import it into Unreal 5.8. The test
passes only if Unreal's own report says every check passed.

Slow: several Blender builds plus an Unreal run. Run with:
    server/.venv/bin/python -m pytest tests/e2e -q -s
"""
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[2]
PORT = 8799
BASE = f"http://127.0.0.1:{PORT}"


def _wait_port(port, timeout=60):
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.5)
    raise RuntimeError("server did not start")


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("data")
    env = dict(os.environ, ME3D_DATA_DIR=str(data_dir))
    proc = subprocess.Popen(
        [str(ROOT / "server/.venv/bin/uvicorn"), "app.main:app", "--port", str(PORT),
         "--app-dir", str(ROOT / "server")],
        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        _wait_port(PORT)
        with httpx.Client(base_url=BASE, timeout=60) as client:
            yield client
    finally:
        proc.terminate()
        proc.wait(timeout=20)


def wait_job(api, job_id, timeout=1800):
    end = time.time() + timeout
    while time.time() < end:
        job = api.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            assert job["status"] == "done", f"job failed: {job.get('error')}\n" + "\n".join(job.get("log", [])[-30:])
            return job["result"]
        time.sleep(2)
    raise TimeoutError(job_id)


def create(api, kind, base):
    r = api.post("/api/projects", json={"kind": kind, "base": base})
    r.raise_for_status()
    body = r.json()
    wait_job(api, body["job_id"])
    project = api.get(f"/api/projects/{body['project']['id']}").json()
    assert project["build_report"]["ok"], project["build_report"]
    return project


@pytest.mark.parametrize("ship_type", ["container", "sampan", "tanker"])
def test_default_ship_builds(api, ship_type):
    ship = create(api, "ship", ship_type)
    stations = [p for p in ship["parts"] if p.get("station")]
    joints = [p for p in ship["parts"] if p.get("joint")]
    assert stations, "every default ship needs crew stations"
    assert joints, "every default ship needs at least one moving part"
    glb = api.get(ship["model_url"])
    assert glb.status_code == 200 and glb.content[:4] == b"glTF"


def test_container_with_crew_imports_into_unreal(api):
    ship = create(api, "ship", "container")
    male = create(api, "crew", "male_default")
    stations = [p["path"] for p in ship["parts"] if p.get("station")]
    wanted = [s for s in ("station__helm", "station__bridge_wing_port", "station__deck_fwd") if s in stations]
    assert len(wanted) == 3, stations

    scene = api.post("/api/scenes", json={
        "schema": "me3d.scene_spec/1", "name": "Container ship with crew",
        "ship": {"project": ship["id"], "version": ship["version"]},
        "crew": [{"project": male["id"], "version": male["version"], "station": s,
                  "animation": a} for s, a in zip(wanted, ["idle", "idle", "walk"])],
    }).json()["scene"]

    export = wait_job(api, api.post(f"/api/scenes/{scene['id']}/export").json()["job_id"])
    pkg = Path(export["package_dir"])
    manifest = json.loads((pkg / "manifest.json").read_text())
    assert manifest["schema"] == "me3d.package/1"
    assert len(manifest["crew"]) == 3
    # crew are placed at their stations, which sit on the ship (not at the origin)
    for c in manifest["crew"]:
        assert any(abs(v) > 0.5 for v in c["location_m"]), c

    report = wait_job(api, api.post(f"/api/scenes/{scene['id']}/unreal-test").json()["job_id"])
    failed = [c for c in report["checks"] if not c["pass"]]
    assert report["ok"] and not failed, json.dumps(failed, indent=1)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-s"]))
