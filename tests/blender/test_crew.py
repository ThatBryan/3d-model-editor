"""Crew builder proof (blender/build_crew.py, contract sections 1, 2, 4, 6).

    server/.venv/bin/python -m pytest tests/blender/test_crew.py -q

Builds the catalog's default male and a 160 cm variant with every piece of equipment in real
Blender (MPFB2 must be installed; the clothes checks also need the CC0 asset pack, installed by
tools/install_mpfb_assets.sh), then reads the GLB back with pygltflib. Nothing here trusts the
build report alone where the GLB itself can be measured.
"""

import json
import math
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
CATALOG = ROOT / "catalog" / "crew" / "male_default.json"
MPFB_DATA = Path.home() / "Library/Application Support/Blender/5.2/extensions/.user/blender_org/mpfb/data"
ANIMS = ["idle", "walk", "brace", "hands_up", "squat"]
GAME_ENGINE_BONES = sorted(
    ["Root", "pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head"]
    + [f"{b}_{s}" for s in "lr" for b in ("clavicle", "upperarm", "lowerarm", "hand", "thigh", "calf", "foot", "ball")]
    + [f"{f}_0{i}_{s}" for s in "lr" for f in ("thumb", "index", "middle", "ring", "pinky") for i in (1, 2, 3)]
)

sys.path.insert(0, str(ROOT / "blender"))
from crew import animations as crew_anims  # noqa: E402  (pure Python parts only)
from crew import spec as crew_spec  # noqa: E402

pygltflib = pytest.importorskip("pygltflib")
needs_blender = pytest.mark.skipif(not Path(BLENDER).exists(), reason="Blender not installed at " + BLENDER)


# ---------------------------------------------------------------------------------------------
# Pure logic (no Blender)

def test_default_spec_normalises_cleanly():
    spec, errors, warnings = crew_spec.normalize(json.loads(CATALOG.read_text()))
    assert errors == [] and warnings == []
    assert spec["body"]["height_cm"] == 178
    assert spec["equipment"] == [{"name": "life_vest", "color": crew_spec.EQUIPMENT_COLORS["orange"]}]
    assert spec["animations"] == ANIMS


def test_bad_spec_values_are_reported_not_built():
    _, errors, _ = crew_spec.normalize({"body": {"height_cm": 250, "skin": "green"},
                                        "clothes": {"suit": "spacesuit"}, "equipment": ["jetpack"],
                                        "animations": ["moonwalk"]})
    joined = " ".join(errors)
    for word in ("height_cm", "skin", "suit", "equipment", "animations"):
        assert word in joined


def test_age_macro_matches_makehuman_scale():
    assert crew_spec.age_years_to_macro(1) == 0.0
    assert crew_spec.age_years_to_macro(25) == 0.5
    assert crew_spec.age_years_to_macro(90) == 1.0
    assert abs(crew_spec.age_years_to_macro(30) - (0.5 + 0.5 * 5 / 65)) < 1e-9


def test_skin_asset_choice():
    assert crew_spec.skin_asset("dark", "male", 30) == "young_african_male/young_african_male.mhmat"
    assert crew_spec.skin_asset("light", "female", 45) == "middleage_caucasian_female/middleage_caucasian_female.mhmat"
    assert crew_spec.skin_asset("medium", "male", 70) == "old_asian_male/old_asian_male.mhmat"


def test_solver_hits_target_and_clamps():
    x, fx = crew_spec.solve_monotonic(lambda v: 1.2 + v, 1.78)
    assert abs(fx - 1.78) <= 0.0005 and abs(x - 0.58) < 0.001
    assert crew_spec.solve_monotonic(lambda v: 1.2 + v, 3.0) == (1.0, 2.2)


def test_label_rule():
    assert crew_spec.part_label("Equipment__life_vest") == "Equipment › life vest"


@pytest.mark.parametrize("name", ["idle", "walk"])
def test_loops_close(name):
    anim = crew_anims.ANIMATIONS[name]
    a, b = crew_anims.sample(anim, 0.0), crew_anims.sample(anim, anim["duration"])
    for ch in a:
        assert all(abs(x - y) < 1e-6 for x, y in zip(a[ch], b[ch])), ch


@pytest.mark.parametrize("name", ["idle", "brace", "hands_up", "squat"])
def test_planted_clips_never_move_the_feet(name):
    anim = crew_anims.ANIMATIONS[name]
    for f in range(crew_anims.frame_count(anim) + 1):
        pose = crew_anims.sample(anim, f / crew_anims.FPS)
        assert pose["foot_l"] == [0, 0, 0, 0] and pose["foot_r"] == [0, 0, 0, 0]


def test_catalog_options_are_installed():
    """Every clothes option the AI may pick must exist in MPFB's installed pack."""
    if not (MPFB_DATA / "packs" / "makehuman_system_assets.json").exists():
        pytest.skip("MakeHuman system asset pack not installed (run tools/install_mpfb_assets.sh)")
    opts = json.loads(CATALOG.read_text())["options"]
    for slot in ("suit", "shoes", "hat"):
        for name in opts[slot]:
            if name is not None:
                assert (MPFB_DATA / "clothes" / name / f"{name}.mhclo").exists(), name
    assert opts["animations"] == ANIMS
    assert sorted(opts["equipment"]) == sorted(crew_spec.EQUIPMENT)


# ---------------------------------------------------------------------------------------------
# Real builds

def _build(tmp: Path, spec: dict) -> dict:
    spec_path = tmp / "spec.json"
    spec_path.write_text(json.dumps(spec))
    out = tmp / "out"
    proc = subprocess.run([BLENDER, "-b", "--python", str(ROOT / "blender" / "build_crew.py"), "--",
                           "--spec", str(spec_path), "--out", str(out)],
                          capture_output=True, text=True, timeout=900)
    report_path = out / "build_report.json"
    assert report_path.exists(), proc.stdout[-3000:] + proc.stderr[-3000:]
    report = json.loads(report_path.read_text())
    report["_exit"] = proc.returncode
    report["_out"] = out
    return report


@pytest.fixture(scope="module")
def default_build(tmp_path_factory):
    if not Path(BLENDER).exists():
        pytest.skip("Blender not installed")
    return _build(tmp_path_factory.mktemp("crew_default"), json.loads(CATALOG.read_text()))


@pytest.fixture(scope="module")
def short_build(tmp_path_factory):
    if not Path(BLENDER).exists():
        pytest.skip("Blender not installed")
    spec = json.loads(CATALOG.read_text())
    spec["id"] = "crew_short"
    spec["body"]["height_cm"] = 160
    spec["equipment"] = ["life_vest", "helmet", "binoculars", "radio"]
    return _build(tmp_path_factory.mktemp("crew_short"), spec)


def _gltf(report):
    return pygltflib.GLTF2().load(str(report["_out"] / "model.glb"))


def _read_accessor(g, idx):
    acc = g.accessors[idx]
    bv = g.bufferViews[acc.bufferView]
    blob = g.binary_blob()
    n = {"SCALAR": 1, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc.type]
    assert acc.componentType == 5126
    stride = bv.byteStride or 4 * n
    base = (bv.byteOffset or 0) + (acc.byteOffset or 0)
    return [struct.unpack_from("<%df" % n, blob, base + i * stride) for i in range(acc.count)]


def _mat(t=None, r=None, s=None):
    t = t or [0, 0, 0]
    x, y, z, w = r or [0, 0, 0, 1]
    s = s or [1, 1, 1]
    rot = [[1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
           [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
           [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)]]
    return [[rot[i][0] * s[0], rot[i][1] * s[1], rot[i][2] * s[2], t[i]] for i in range(3)] + [[0, 0, 0, 1]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)] for i in range(4)]


def _world_positions(g, overrides=None):
    """World matrix of every node, with optional per-node TRS overrides {node: {path: value}}."""
    overrides = overrides or {}
    parent = {}
    for i, n in enumerate(g.nodes):
        for c in n.children or []:
            parent[c] = i
    cache = {}

    def world(i):
        if i in cache:
            return cache[i]
        n = g.nodes[i]
        o = overrides.get(i, {})
        local = _mat(o.get("translation", n.translation), o.get("rotation", n.rotation), o.get("scale", n.scale))
        m = _mul(world(parent[i]), local) if i in parent else local
        cache[i] = m
        return m

    return {g.nodes[i].name: world(i) for i in range(len(g.nodes))}


def _node(g, name):
    return next(i for i, n in enumerate(g.nodes) if n.name == name)


def _top_y(g, node_name):
    """Highest point of a mesh node in glTF space (Y up), via its accessor max and node chain."""
    idx = _node(g, node_name)
    w = _world_positions(g)[node_name]
    tops = []
    for prim in g.meshes[g.nodes[idx].mesh].primitives:
        acc = g.accessors[prim.attributes.POSITION]
        for corner in ((acc.min[0], acc.max[1], acc.min[2]), (acc.max[0], acc.max[1], acc.max[2])):
            tops.append(sum(w[1][k] * corner[k] for k in range(3)) + w[1][3])
    return max(tops)


@needs_blender
def test_default_build_ok(default_build):
    r = default_build
    assert r["ok"] is True, r["errors"]
    assert r["_exit"] == 0
    assert r["errors"] == []
    assert 0 < r["triangles"] <= 40000
    for f in ("model.glb", "model.blend", "parts.json", "build_report.json"):
        assert (r["_out"] / f).exists(), f
    assert r["bones"] == 53
    assert r["animations"] == ANIMS
    assert abs(r["bounds_min"][2]) < 0.002   # soles on the deck


@needs_blender
def test_one_skin_with_game_engine_bones(default_build):
    g = _gltf(default_build)
    assert len(g.skins) == 1
    names = sorted(g.nodes[j].name for j in g.skins[0].joints)
    assert names == GAME_ENGINE_BONES
    skinned = [n for n in g.nodes if n.mesh is not None and n.skin is not None]
    assert skinned and all(n.skin == 0 for n in skinned)


def _is_identity(node):
    t = node.translation or [0, 0, 0]
    r = node.rotation or [0, 0, 0, 1]
    s = node.scale or [1, 1, 1]
    return (all(abs(x) < 1e-6 for x in t) and all(abs(a - b) < 1e-6 for a, b in zip(r, [0, 0, 0, 1]))
            and all(abs(x - 1) < 1e-6 for x in s) and node.matrix is None)


@needs_blender
def test_unreal_identity_armature_and_real_size(default_build):
    """UE 5.8 ignores parent transforms on skinned meshes: the armature node must be an identity
    scene root and every skinned mesh node identity too, with the human at real size in metres."""
    g = _gltf(default_build)
    roots = [g.nodes[i] for i in g.scenes[g.scene or 0].nodes]
    assert [n.name for n in roots] == ["Crew"]
    assert _is_identity(roots[0])
    for n in g.nodes:
        if n.mesh is not None and n.skin is not None:
            assert _is_identity(n), n.name
    ys = []
    for n in g.nodes:
        if n.mesh is not None and n.skin is not None:
            for prim in g.meshes[n.mesh].primitives:
                acc = g.accessors[prim.attributes.POSITION]
                ys += [acc.min[1], acc.max[1]]
    assert abs(min(ys)) < 0.002                       # soles at the origin
    assert 1.76 <= max(ys) <= 1.84, max(ys)           # 1.78 m body, plus hair


@needs_blender
def test_animations_named_exactly(default_build):
    g = _gltf(default_build)
    assert sorted(a.name for a in g.animations) == sorted(ANIMS)
    joints = {g.skins[0].joints[k] for k in range(len(g.skins[0].joints))}
    for a in g.animations:
        targets = {c.target.node for c in a.channels}
        assert targets and targets <= joints, a.name  # only bones are animated


@needs_blender
def test_height_within_2cm(default_build):
    assert abs(default_build["height_m"] - 1.78) <= 0.02
    g = _gltf(default_build)
    top = _top_y(g, "Body__Skin")   # GLB is +Y up; body top = crown of the head, soles at 0
    assert abs(top - 1.78) <= 0.02, top


@needs_blender
def test_height_slider_works(default_build, short_build):
    assert short_build["ok"] is True, short_build["errors"]
    assert abs(short_build["height_m"] - 1.60) <= 0.02
    tall = _top_y(_gltf(default_build), "Body__Skin")
    short = _top_y(_gltf(short_build), "Body__Skin")
    assert tall - short > 0.15, (tall, short)


@needs_blender
def test_equipment_parented_under_bones(short_build):
    g = _gltf(short_build)
    joints = {g.nodes[j].name for j in g.skins[0].joints}
    parent = {c: g.nodes[i].name for i, n in enumerate(g.nodes) for c in (n.children or [])}
    expected = {"Equipment__life_vest": "spine_02", "Equipment__helmet": "head",
                "Equipment__binoculars": "spine_03", "Equipment__radio": "pelvis"}
    for name, bone in expected.items():
        idx = _node(g, name)
        assert g.nodes[idx].mesh is not None, name
        assert parent[idx] == bone and bone in joints, (name, parent.get(idx))
    parts = {p["path"]: p for p in json.loads((short_build["_out"] / "parts.json").read_text())}
    for name, bone in expected.items():
        assert parts[name]["bone"] == bone
        assert parts[name]["label"].startswith("Equipment › ")


@needs_blender
def test_parts_json_contract_fields(default_build):
    parts = json.loads((default_build["_out"] / "parts.json").read_text())
    keys = {"path", "label", "parent", "joint", "station", "origin_m", "rotation_deg",
            "bounds_min", "bounds_max", "triangles"}
    assert parts and all(keys <= set(p) for p in parts)
    assert sum(p["triangles"] for p in parts) == default_build["triangles"]
    assert all(p["station"] is None and p["joint"] is None for p in parts)
    assert {"Body__Skin", "Equipment__life_vest"} <= {p["path"] for p in parts}


@needs_blender
def test_feet_on_deck_in_first_idle_frame(default_build):
    """Pose the GLB skeleton at idle's first keyframe and measure the toe (ball) joints."""
    g = _gltf(default_build)
    idle = next(a for a in g.animations if a.name == "idle")
    overrides = {}
    for ch in idle.channels:
        sampler = idle.samplers[ch.sampler]
        first = _read_accessor(g, sampler.output)[0]
        overrides.setdefault(ch.target.node, {})[ch.target.path] = list(first)
    w = _world_positions(g, overrides)
    for s in "lr":
        ball_y = w["ball_" + s][1][3]
        ankle_y = w["foot_" + s][1][3]
        assert 0.0 <= ball_y <= 0.03, ball_y      # toe joint just above the deck
        assert 0.04 <= ankle_y <= 0.12, ankle_y   # ankle at a believable height, not sunk
    # And planted for the whole clip, per the builder's own frame-by-frame check.
    for clip in ("idle", "brace", "squat"):
        for s in "lr":
            assert default_build["feet"][clip]["foot_%s_z_range" % s] < 0.01
            assert default_build["feet"][clip]["foot_%s_x_range" % s] < 0.01


@needs_blender
def test_clothes_present_and_skinned(default_build):
    if not default_build.get("mpfb_pack_installed"):
        pytest.skip("MakeHuman system asset pack not installed (run tools/install_mpfb_assets.sh)")
    g = _gltf(default_build)
    for name in ("Clothes__Suit", "Clothes__Shoes", "Head__Hair", "Head__Eyes", "Head__Eyebrows"):
        n = g.nodes[_node(g, name)]
        assert n.mesh is not None and n.skin == 0, name
    mats = {m.name: m for m in g.materials}
    assert mats["Body__Skin"].alphaMode in (None, "OPAQUE")      # skin is never translucent in Unreal
    assert mats["Clothes__Suit"].alphaMode in (None, "OPAQUE")
    assert mats["Head__Hair"].alphaMode == "MASK"
    assert mats["Body__Skin"].pbrMetallicRoughness.baseColorTexture is not None


@needs_blender
def test_bad_spec_fails_with_report(tmp_path):
    r = _build(tmp_path, {"schema": "me3d.crew_spec/1", "id": "bad", "body": {"skin": "green"}})
    assert r["ok"] is False and r["_exit"] == 1
    assert any("skin" in e for e in r["errors"])
