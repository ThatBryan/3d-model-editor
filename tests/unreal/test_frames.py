"""Blender (m, +X bow, +Y port, +Z up) -> Unreal (cm, +X fwd, +Y right, +Z up).

A sign error here puts crew on the wrong side of the ship and still "imports fine", so the
rotation mapping is proved against Unreal's own FRotationMatrix formula, not restated.
"""
import itertools
import random
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "unreal"))
import me3d_frames as f  # noqa: E402


def _close(a, b, tol=1e-9):
    return all(abs(x - y) < tol for x, y in zip(a, b))


def test_location_flips_only_y_and_scales_to_cm():
    assert f.blender_to_ue_location_cm((1.0, 2.0, 3.0)) == (100.0, -200.0, 300.0)
    # port side (+Y Blender) must land on Unreal's left, i.e. negative Y
    assert f.blender_to_ue_location_cm((0, 4.5, 0))[1] < 0


@pytest.mark.parametrize("rot, ue_forward", [
    ((0, 0, 0), (1, 0, 0)),
    ((0, 0, 90), (0, -1, 0)),   # Blender +90 about Z faces port; port is -Y in Unreal
    ((0, 0, -90), (0, 1, 0)),
    ((0, 30, 0), (0.8660254037844387, 0, -0.5)),  # Blender +ry pitches the bow down
])
def test_named_cases_forward_vector(rot, ue_forward):
    x_axis, _, _ = f.ue_rotator_axes(*f.blender_to_ue_rotator(rot))
    assert _close(x_axis, ue_forward)


def test_roll_lifts_port_side():
    # Blender +rx turns +Y (port) toward +Z. In Unreal port is -Y, so -Y must gain +Z.
    _, y_axis, _ = f.ue_rotator_axes(*f.blender_to_ue_rotator((30, 0, 0)))
    port_axis = tuple(-c for c in y_axis)
    assert port_axis[2] > 0.49


def test_any_euler_matches_the_mirrored_matrix():
    rng = random.Random(7)
    cases = [tuple(rng.uniform(-180, 180) for _ in range(3)) for _ in range(200)]
    cases += list(itertools.product((-90, -45, 0, 45, 90, 180), repeat=3))
    for rot in cases:
        rb = f.blender_euler_matrix(rot)
        ue_axes = f.ue_rotator_axes(*f.blender_to_ue_rotator(rot))
        for i, ue_axis in enumerate(ue_axes):
            # image of Blender axis i (column i of rb), mapped into Unreal, is the image of the
            # matching Unreal axis up to the Y flip of the axis itself
            col = [rb[r][i] for r in range(3)]
            expected = f.blender_vector_to_ue(col)
            if i == 1:  # Unreal +Y is Blender -Y
                expected = tuple(-c for c in expected)
            assert _close(ue_axis, expected, 1e-9), (rot, i, ue_axis, expected)


def test_glb_reader_finds_mesh_nodes_and_parents(tmp_path):
    import json
    import struct
    doc = {"asset": {"version": "2.0"}, "nodes": [
        {"name": "Hull__Main", "mesh": 0, "children": [1, 2]},
        {"name": "Deck__Crane", "mesh": 1, "children": [3]},
        {"name": "station__helm"},
        {"name": "Deck__Crane__Jib", "mesh": 2}], "animations": [{"name": "idle"}]}
    js = json.dumps(doc).encode()
    js += b" " * (-len(js) % 4)
    blob = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js)) + struct.pack("<II", len(js), 0x4E4F534A) + js
    p = tmp_path / "x.glb"
    p.write_bytes(blob)
    g = f.read_glb_json(p)
    assert f.glb_mesh_nodes(g) == {"Hull__Main": None, "Deck__Crane": "Hull__Main",
                                   "Deck__Crane__Jib": "Deck__Crane"}
    assert f.glb_animation_names(g) == ["idle"]
