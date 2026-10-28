"""Pure helpers shared by the Unreal import script and its tests. No `unreal` import here.

Frames (docs/CONTRACT.md section 1):

- Blender source frame: metres, +X bow, +Y port, +Z up, right-handed.
- Unreal world frame: centimetres, +X forward (bow), +Y right (starboard), +Z up, left-handed.

So a point maps (x, y, z) m  ->  (100x, -100y, 100z) cm: only Y flips.

Rotations. Blender's XYZ Euler applies X, then Y, then Z about the fixed world axes
(R = Rz @ Ry @ Rx). Unreal's FRotator applies Roll (about X), then Pitch (about Y), then
Yaw (about Z), in the same order, but with Unreal's own sign conventions:
  +Yaw   turns +X toward +Y (starboard)  - Blender +rz turns +X toward port, so yaw   = -rz
  +Pitch turns +X toward +Z (nose up)    - Blender +ry turns +X toward -Z, so    pitch = -ry
  +Roll  turns +Y toward -Z              - Blender +rx lifts port (-Y in UE), so roll  = +rx
`tests/unreal/test_frames.py` proves this with rotation matrices rather than by assertion.
"""
import json
import math
import struct

CM_PER_M = 100.0


def blender_to_ue_location_cm(location_m):
    x, y, z = location_m
    return (x * CM_PER_M, -y * CM_PER_M, z * CM_PER_M)


def blender_to_ue_rotator(rotation_deg):
    """Blender XYZ Euler degrees -> Unreal (roll, pitch, yaw) degrees."""
    rx, ry, rz = rotation_deg
    return (rx, -ry, -rz)


# ---- matrices, used by the tests and by the harness to compare rotations without Euler ambiguity
def _rx(a):
    c, s = math.cos(a), math.sin(a)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def _ry(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def _rz(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def matmul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def blender_euler_matrix(rotation_deg):
    """Rotation matrix (columns = rotated axes) of a Blender XYZ Euler, in the Blender frame."""
    rx, ry, rz = (math.radians(v) for v in rotation_deg)
    return matmul(_rz(rz), matmul(_ry(ry), _rx(rx)))


def ue_rotator_axes(roll, pitch, yaw):
    """Unreal's FRotationMatrix axes (X, Y, Z) in the Unreal frame, as written in
    Engine/Source/Runtime/Core/Public/Math/RotationTranslationMatrix.h."""
    sp, cp = math.sin(math.radians(pitch)), math.cos(math.radians(pitch))
    sy, cy = math.sin(math.radians(yaw)), math.cos(math.radians(yaw))
    sr, cr = math.sin(math.radians(roll)), math.cos(math.radians(roll))
    x = (cp * cy, cp * sy, sp)
    y = (sr * sp * cy - cr * sy, sr * sp * sy + cr * cy, -sr * cp)
    z = (-(cr * sp * cy + sr * sy), cy * sr - cr * sp * sy, cr * cp)
    return x, y, z


def blender_vector_to_ue(v):
    return (v[0], -v[1], v[2])


# ---- GLB reading (no pygltflib inside Unreal's Python)
def read_glb_json(path):
    with open(path, "rb") as f:
        data = f.read()
    magic, _version, _length = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"{path} is not a GLB")
    chunk_len, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A:
        raise ValueError(f"{path}: first chunk is not JSON")
    return json.loads(data[20:20 + chunk_len].decode("utf-8"))


def glb_mesh_nodes(gltf):
    """{node name: parent node name or None} for every node that carries a mesh."""
    nodes = gltf.get("nodes", [])
    parent = {}
    for i, n in enumerate(nodes):
        for c in n.get("children", []):
            parent[c] = i
    out = {}
    for i, n in enumerate(nodes):
        if "mesh" in n:
            p = parent.get(i)
            out[n.get("name", f"node_{i}")] = nodes[p].get("name", f"node_{p}") if p is not None else None
    return out


def glb_animation_names(gltf):
    return [a.get("name", f"anim_{i}") for i, a in enumerate(gltf.get("animations", []))]


def distance(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
