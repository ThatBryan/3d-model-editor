"""Ship builders, end to end through Blender (slow: runs Blender headless).

    server/.venv/bin/python -m pytest tests/blender/test_ships.py -q

Every geometric check is measured on the EXPORTED model.glb re-imported into a fresh Blender,
using each object's matrix_world, never raw glTF node translations: a check that reads only a
node's own translation measures rotated or parented children wrongly (library:
glb-contract-validator-reads-node-translation-only-so-rigs-export-flattened).
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from app.config import DEFAULT_BLENDER  # noqa: E402

import pytest
from pygltflib import GLTF2

ROOT = Path(__file__).resolve().parents[2]
BLENDER = os.environ.get("BLENDER", str(DEFAULT_BLENDER))
BUILD = ROOT / "blender" / "build_ship.py"
TYPES = ("container", "sampan", "tanker")
BUDGET = {"container": 200_000, "tanker": 200_000, "sampan": 50_000}
SOCKETS = ("socket_bridge_eye", "socket_radar", "socket_light_masthead",
           "socket_light_masthead_aft", "socket_light_port", "socket_light_stbd",
           "socket_light_stern", "socket_bow", "socket_prop")
STATIONS = {
    "container": {"station__helm", "station__bridge_wing_port", "station__bridge_wing_stbd",
                  "station__deck_fwd", "station__deck_aft"},
    "tanker": {"station__helm", "station__bridge_wing_port", "station__bridge_wing_stbd",
               "station__deck_fwd", "station__deck_aft"},
    "sampan": {"station__helm", "station__bow", "station__passenger_1"},
}
JOINTS = {  # moving parts each ship must have, with their axis
    "container": {"Mast__Radar_1": "z", "Lifeboat__Davit_Port": "x", "Lifeboat__Davit_Stbd": "x",
                  "Hull__Rudder": "z"},
    "tanker": {"Mast__Radar_1": "z", "Deck__Provision_Crane": "z",
               "Deck__Provision_Crane__Jib": "y", "Lifeboat__Davit_Port": "x",
               "Hull__Rudder": "z"},
    "sampan": {"Transom__Outboard": "z", "Transom__Outboard_Tilt": "y"},
}
STATION_TOL = 0.3   # metres between a station and the deck surface under it

MEASURE = r'''
import bpy, json, sys, math
from mathutils import Vector
glb, out = sys.argv[sys.argv.index("--") + 1:]
for ob in list(bpy.data.objects):
    bpy.data.objects.remove(ob, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=glb)
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
res = {"objects": {}, "tris": 0}
allp = []
for ob in bpy.data.objects:
    d = {"parent": ob.parent.name if ob.parent else None, "type": ob.type,
         "world": list(ob.matrix_world.translation),
         "forward": list(ob.matrix_world.to_3x3() @ Vector((1, 0, 0))),
         "props": {k: ob[k] for k in ob.keys() if k.startswith("me3d")}}
    if ob.type == "MESH":
        me = ob.evaluated_get(dg).to_mesh()
        pts = [ob.matrix_world @ v.co for v in me.vertices]
        d["tris"] = sum(len(p.vertices) - 2 for p in me.polygons)
        res["tris"] += d["tris"]
        ob.evaluated_get(dg).to_mesh_clear()
        if pts:
            d["min"] = [min(p[i] for p in pts) for i in range(3)]
            d["max"] = [max(p[i] for p in pts) for i in range(3)]
            allp += pts
    res["objects"][ob.name] = d
res["min"] = [min(p[i] for p in allp) for i in range(3)]
res["max"] = [max(p[i] for p in allp) for i in range(3)]
# deck under each station: cast down from just above it
res["deck_hits"] = {}
for name, d in res["objects"].items():
    if name.startswith("station__"):
        o = Vector(d["world"]) + Vector((0, 0, 0.29))
        hit, loc, *_ = bpy.context.scene.ray_cast(dg, o, Vector((0, 0, -1)), distance=0.6)
        res["deck_hits"][name] = loc.z if hit else None
json.dump(res, open(out, "w"))
'''


def run_build(spec, out_dir):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    spec_path = out_dir / "spec.json"
    spec_path.write_text(json.dumps(spec))
    proc = subprocess.run(
        [BLENDER, "-b", "--factory-startup", "--python", str(BUILD), "--",
         "--spec", str(spec_path), "--out", str(out_dir)],
        capture_output=True, text=True, timeout=180)
    report = json.loads((out_dir / "build_report.json").read_text(encoding="utf-8"))
    parts_file = out_dir / "parts.json"
    parts = json.loads(parts_file.read_text(encoding="utf-8")) if parts_file.exists() else []
    return proc, report, parts


def measure(glb):
    glb = Path(glb)
    script = glb.parent / "_measure.py"
    script.write_text(MEASURE)
    out = glb.parent / "measure.json"
    proc = subprocess.run([BLENDER, "-b", "--factory-startup", "--python", str(script), "--",
                           str(glb), str(out)], capture_output=True, text=True, timeout=180)
    assert out.exists(), proc.stdout[-3000:] + proc.stderr[-3000:]
    return json.loads(out.read_text(encoding="utf-8"))


def catalog(t):
    return json.loads((ROOT / "catalog" / "ships" / f"{t}.json").read_text(encoding="utf-8"))


def station_offenders(m):
    """Stations with no deck surface within STATION_TOL below/at them."""
    bad = []
    for name, hit in m["deck_hits"].items():
        z = m["objects"][name]["world"][2]
        if hit is None or abs(hit - z) > STATION_TOL:
            bad.append((name, z, hit))
    return bad


def glb_nodes(path):
    g = GLTF2().load(str(path))
    names = {n.name for n in g.nodes}
    parent = {}
    for i, n in enumerate(g.nodes):
        for c in n.children or []:
            parent[g.nodes[c].name] = n.name
    return g, names, parent


_CACHE = {}


@pytest.fixture(scope="module")
def ship(tmp_path_factory):
    def get(t):
        if t not in _CACHE:
            out = tmp_path_factory.mktemp(t)
            proc, report, parts = run_build(catalog(t), out)
            _CACHE[t] = {"proc": proc, "report": report, "parts": parts, "out": out,
                         "m": measure(out / "model.glb") if report["ok"] else None}
        return _CACHE[t]
    return get


@pytest.mark.parametrize("t", TYPES)
def test_build_ok_and_files(ship, t):
    s = ship(t)
    assert s["report"]["ok"], s["report"]["errors"]
    assert s["proc"].returncode == 0
    for f in ("model.glb", "model.blend", "parts.json", "build_report.json"):
        assert (s["out"] / f).stat().st_size > 0, f
    assert set(s["report"]) >= {"ok", "errors", "warnings", "triangles", "bounds_min",
                                "bounds_max", "seconds"}


@pytest.mark.parametrize("t", TYPES)
def test_glb_has_every_part_and_only_legal_names(ship, t):
    s = ship(t)
    _, names, _ = glb_nodes(s["out"] / "model.glb")
    paths = {p["path"] for p in s["parts"]}
    assert paths <= names, sorted(paths - names)
    import re
    seg = r"[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*"
    legal = re.compile(rf"^(?:{seg}__{seg}(?:__{seg})?|station__[a-z0-9_]+|socket_[a-z_]+)$")
    assert all(legal.match(n) for n in names), [n for n in names if not legal.match(n)]
    for p in s["parts"]:
        assert set(p) >= {"path", "label", "parent", "joint", "station", "origin_m",
                          "rotation_deg", "bounds_min", "bounds_max", "triangles"}
        assert p["label"] == p["path"].replace("__", " › ").replace("_", " ")


@pytest.mark.parametrize("t", TYPES)
def test_principal_dimensions(ship, t):
    s, prm = ship(t), catalog(t)["params"]
    m = s["m"]
    loa = m["max"][0] - m["min"][0]
    assert abs(loa - prm["loa_m"]) <= 0.02 * prm["loa_m"], loa
    assert abs(m["min"][2] + prm["draught_m"]) <= 0.05 * prm["draught_m"], m["min"][2]
    assert m["max"][2] > 0.5, "nothing above the waterline"
    beam = m["max"][1] - m["min"][1]
    assert abs(beam - prm["beam_m"]) <= 0.05 * prm["beam_m"], beam
    assert abs((m["max"][0] + m["min"][0]) / 2) < 0.06 * loa, "origin not near amidships"


@pytest.mark.parametrize("t", TYPES)
def test_triangle_budget(ship, t):
    s = ship(t)
    assert s["m"]["tris"] <= BUDGET[t], s["m"]["tris"]
    assert s["report"]["triangles"] <= BUDGET[t]


@pytest.mark.parametrize("t", TYPES)
def test_stations_stand_on_deck(ship, t):
    s = ship(t)
    m = s["m"]
    found = {n for n in m["objects"] if n.startswith("station__")}
    assert STATIONS[t] <= found, STATIONS[t] - found
    assert station_offenders(m) == []
    by_path = {p["path"]: p for p in s["parts"]}
    for name in found:
        p = by_path[name]
        o = m["objects"][name]
        assert p["parent"] and p["parent"] in by_path, name
        assert o["parent"] == p["parent"], name  # hierarchy survived into glTF
        st = p["station"]
        assert st["pose"] in ("stand", "sit") and st["label"] and isinstance(st["activities"], list)
        # parts.json origin is the station's world position, which crew placement relies on
        assert all(abs(a - b) < 0.01 for a, b in zip(p["origin_m"], o["world"])), name
        assert abs(p["origin_m"][2] - m["deck_hits"][name]) <= STATION_TOL, name
        assert len(p["rotation_deg"]) == 3
        assert o["forward"][2] == pytest.approx(0, abs=1e-3), "station tilted"
    assert by_path["station__helm"]["station"]["pose"] == ("sit" if t == "sampan" else "stand")


@pytest.mark.parametrize("t", TYPES)
def test_sockets(ship, t):
    s, prm = ship(t), catalog(t)["params"]
    _, names, _ = glb_nodes(s["out"] / "model.glb")
    need = [x for x in SOCKETS if prm["loa_m"] >= 50 or x != "socket_light_masthead_aft"]
    assert set(need) <= names, set(need) - names
    m = s["m"]
    bow = m["objects"]["socket_bow"]["world"]
    assert abs(bow[2]) < 0.05 and bow[0] > 0.4 * prm["loa_m"] * 0.5
    assert m["objects"]["socket_prop"]["world"][2] < 0
    assert m["objects"]["socket_light_port"]["world"][1] > 0 > m["objects"]["socket_light_stbd"]["world"][1]


@pytest.mark.parametrize("t", TYPES)
def test_joints(ship, t):
    s = ship(t)
    m = s["m"]
    _, names, gparent = glb_nodes(s["out"] / "model.glb")
    joints = {p["path"]: p for p in s["parts"] if p["joint"]}
    for name, axis in JOINTS[t].items():
        assert name in joints, name
        assert joints[name]["joint"]["axis"] == axis
    for name, p in joints.items():
        j = p["joint"]
        assert j["kind"] == "revolute" and j["priority"] in ("P0", "P1", "P2")
        assert j["min_deg"] <= j["max_deg"]
        assert name in names and gparent.get(name), f"{name} has no parent in the GLB"
        assert json.loads(m["objects"][name]["props"]["me3d_joint"]) == j  # survives as extras
        # origin_m is the pivot, and the pivot survived export
        assert all(abs(a - b) < 0.01 for a, b in zip(p["origin_m"], m["objects"][name]["world"]))


# ------------------------------------------------------------------------------------------
# Spec edits: overrides, custom ops, failures
# ------------------------------------------------------------------------------------------

HORN = """
me3d.box("Mast__Horn", center=(0.0, 0.0, 3.0), size=(0.3, 0.2, 0.2), color=(0.9, 0.9, 0.1),
         parent="Hull__Main")
"""


@pytest.fixture(scope="module")
def edited(ship, tmp_path_factory):
    spec = catalog("sampan")
    spec["overrides"] = {"Canopy__Awning": {"offset_m": [0, 0, 0.5]},
                         "Transom__Outboard_Tilt": {"rotate_deg": [0, 60, 0]}}
    spec["joint_limits"] = {"Transom__Outboard": {"min_deg": -20, "max_deg": 20}}
    spec["custom_ops"] = [{"id": "op_1", "description": "add a horn on the mast", "code": HORN}]
    out = tmp_path_factory.mktemp("sampan_edited")
    proc, report, parts = run_build(spec, out)
    return {"proc": proc, "report": report, "parts": parts, "out": out,
            "m": measure(out / "model.glb"), "base": ship("sampan")}


def test_override_moves_part_and_its_socket(edited):
    assert edited["report"]["ok"], edited["report"]["errors"]
    b, e = edited["base"]["m"]["objects"], edited["m"]["objects"]
    assert e["Canopy__Awning"]["max"][2] == pytest.approx(b["Canopy__Awning"]["max"][2] + 0.5,
                                                          abs=0.01)
    assert e["socket_radar"]["world"][2] == pytest.approx(b["socket_radar"]["world"][2] + 0.5,
                                                          abs=0.01)
    pj = {p["path"]: p for p in edited["parts"]}
    pb = {p["path"]: p for p in edited["base"]["parts"]}
    assert pj["Canopy__Awning"]["bounds_max"][2] == pytest.approx(
        pb["Canopy__Awning"]["bounds_max"][2] + 0.5, abs=0.01)
    assert pj["Transom__Outboard"]["joint"]["min_deg"] == -20


def test_tilted_outboard_is_measured_through_the_chain(edited):
    """Tilting the outboard 60 degrees lifts the propeller (a grandchild) out of the water.
    The propeller's own glTF node translation does not change at all, so only a world-space
    measurement sees it; parts.json must report the world position too."""
    b, e = edited["base"]["m"]["objects"], edited["m"]["objects"]
    zb, ze = b["Transom__Outboard__Propeller"]["world"][2], e["Transom__Outboard__Propeller"]["world"][2]
    assert ze > zb + 0.3, (zb, ze)
    g0, _, _ = glb_nodes(edited["base"]["out"] / "model.glb")
    g1, _, _ = glb_nodes(edited["out"] / "model.glb")
    t0 = next(n.translation for n in g0.nodes if n.name == "Transom__Outboard__Propeller")
    t1 = next(n.translation for n in g1.nodes if n.name == "Transom__Outboard__Propeller")
    assert t0 == pytest.approx(t1, abs=1e-5)  # the raw node translation is blind to the tilt
    pj = {p["path"]: p for p in edited["parts"]}
    assert pj["Transom__Outboard__Propeller"]["origin_m"][2] == pytest.approx(ze, abs=0.01)
    assert pj["Transom__Outboard_Tilt"]["rotation_deg"][1] == pytest.approx(60, abs=0.1)
    assert e["socket_prop"]["world"][2] == pytest.approx(ze, abs=0.01)


def test_custom_op_adds_a_part(edited):
    _, names, gparent = glb_nodes(edited["out"] / "model.glb")
    assert "Mast__Horn" in names and gparent["Mast__Horn"] == "Hull__Main"
    horn = next(p for p in edited["parts"] if p["path"] == "Mast__Horn")
    assert horn["label"] == "Mast › Horn" and horn["triangles"] == 12
    assert horn["bounds_max"][2] == pytest.approx(3.1, abs=1e-3)


def test_broken_custom_op_fails_loudly(tmp_path):
    spec = catalog("sampan")
    spec["custom_ops"] = [{"id": "op_bad", "description": "broken", "code":
                           "x = 1\nraise ValueError('boom horn')\n"}]
    proc, report, _ = run_build(spec, tmp_path)
    assert report["ok"] is False
    assert proc.returncode == 1
    assert any("op_bad" in e and "boom horn" in e and "line 2" in e for e in report["errors"]), \
        report["errors"]


def test_custom_op_with_illegal_name_fails(tmp_path):
    spec = catalog("sampan")
    spec["custom_ops"] = [{"id": "op_name", "description": "bad name", "code":
                           "me3d.MeshBuilder().box((0,0,3),(1,1,1),(1,0,0))\n"
                           "import bpy\nob = bpy.data.objects.new('my horn.001', None)\n"
                           "bpy.context.scene.collection.objects.link(ob)\n"}]
    proc, report, _ = run_build(spec, tmp_path)
    assert report["ok"] is False and proc.returncode == 1
    assert any("my horn.001" in e for e in report["errors"]), report["errors"]


def test_station_check_catches_a_floating_station(tmp_path):
    """The on-deck check can fail: lift the bowman's station 1 m off the foredeck."""
    spec = catalog("sampan")
    spec["custom_ops"] = [{"id": "op_lift", "description": "lift the bow station",
                           "code": "bpy.data.objects['station__bow'].location.z += 1.0\n"}]
    proc, report, _ = run_build(spec, tmp_path)
    assert report["ok"], report["errors"]
    bad = station_offenders(measure(tmp_path / "model.glb"))
    assert [b[0] for b in bad] == ["station__bow"], bad


def test_unknown_type_and_bad_param_fail(tmp_path):
    spec = catalog("sampan")
    spec["type"] = "submarine"
    proc, report, _ = run_build(spec, tmp_path / "a")
    assert not report["ok"] and proc.returncode == 1 and "submarine" in report["errors"][0]
    spec = copy.deepcopy(catalog("container"))
    spec["params"]["loa_m"] = 10
    proc, report, _ = run_build(spec, tmp_path / "b")
    assert not report["ok"] and "loa_m" in report["errors"][0]
