"""Build a small but contract-complete `me3d.package/1` for testing the Unreal harness.

Run on the host (any Python 3.10+):

    server/.venv/bin/python tests/unreal/make_fixture_package.py <out_dir>

It calls Blender headless twice with this same file (the Blender half is selected by `bpy`
being importable), then writes `manifest.json` and the ship metadata. The result is
`<out_dir>/pkg_fixture_boat/`.

The boat is deliberately asymmetric so a frame mistake shows up as a wrong position, not a
coincidence: the cabin is aft, the crane is forward on the starboard side.

    Hull__Main                        fixed, origin at waterline amidships
      Superstructure__Cabin           fixed, aft
        station__helm                 crew station inside the cabin
        Mast__Main                    fixed, on the cabin roof
          Mast__Radar                 moving: z spin, pivot at mast top
          socket_radar
      Deck__Crane                     moving: z slew, pivot on deck, forward starboard
        Deck__Crane__Jib              moving: y luff, pivot at top of crane column
        station__crane                crew station beside the crane, rotated 90 deg (faces port)
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

BLENDER = os.environ.get("BLENDER", "/Applications/Blender.app/Contents/MacOS/Blender")
HERE = Path(__file__).resolve().parent
WORKER_GLB = HERE / "fixtures" / "Worker.glb"
PACKAGE_ID = "pkg_fixture_boat"
SHIP_ID = "fixture_boat"
CREW_ID = "crew_worker"
CREW_ID_B = "crew_worker_b"  # same rig as CREW_ID: proves the second crew reuses the first skeleton

try:
    import bpy  # noqa: F401
    IN_BLENDER = True
except ImportError:
    IN_BLENDER = False


# --------------------------------------------------------------------------- Blender half
def _blender_ship(out_dir: Path):
    import bpy
    from mathutils import Matrix, Vector

    bpy.ops.wm.read_factory_settings(use_empty=True)

    def box(name, size, offset, parent=None, location=(0, 0, 0), joint=None):
        """A box mesh whose origin (pivot) is at `location`, geometry offset by `offset`."""
        sx, sy, sz = size
        ox, oy, oz = offset
        verts = [(ox + dx * sx / 2, oy + dy * sy / 2, oz + dz * sz / 2)
                 for dx in (-1, 1) for dy in (-1, 1) for dz in (-1, 1)]
        faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        mesh = bpy.data.meshes.new(name)
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.scene.collection.objects.link(obj)
        if parent is not None:
            obj.parent = parent
            obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.location = location
        if joint is not None:
            obj["me3d_joint"] = json.dumps(joint)
        return obj

    def empty(name, parent, location, rotation_z_deg=0.0):
        import math
        obj = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(obj)
        obj.parent = parent
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.location = location
        obj.rotation_euler = (0, 0, math.radians(rotation_z_deg))
        return obj

    # Locations below are relative to the parent's origin.
    hull = box("Hull__Main", (12, 4, 2.5), (0, 0, 0.25))  # keel at -1.0, deck at +1.5
    cabin = box("Superstructure__Cabin", (3, 3, 2), (0, 0, 1), hull, (-3.5, 0, 1.5))
    mast = box("Mast__Main", (0.3, 0.3, 3), (0, 0, 1.5), cabin, (0, 0, 2))
    radar = box("Mast__Radar", (1.2, 0.2, 0.15), (0.45, 0, 0.1), mast, (0, 0, 3),
                {"axis": "z", "min_deg": -180, "max_deg": 180, "priority": "P0", "kind": "revolute"})
    crane = box("Deck__Crane", (0.5, 0.5, 2), (0, 0, 1), hull, (3, -1, 1.5),
                {"axis": "z", "min_deg": -170, "max_deg": 170, "priority": "P0", "kind": "revolute"})
    jib = box("Deck__Crane__Jib", (3, 0.3, 0.3), (1.5, 0, 0), crane, (0, 0, 2),
              {"axis": "y", "min_deg": -60, "max_deg": 10, "priority": "P1", "kind": "revolute"})
    empty("station__helm", cabin, (0.5, 0.6, 0), 0)  # on the cabin floor = deck, z 1.5 world
    empty("station__crane", crane, (0, -0.8, 0), 90)
    empty("socket_radar", mast, (0, 0, 3.2))
    empty("socket_bridge_eye", cabin, (1.2, 0, 1.6))
    bpy.context.view_layer.update()

    ship_dir = out_dir / "ship"
    ship_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(ship_dir / f"{SHIP_ID}.glb"), export_format="GLB",
                              export_extras=True, export_yup=True, export_apply=False)

    articulation = []
    stations = {}
    for obj in bpy.data.objects:
        if "me3d_joint" in obj:
            j = json.loads(obj["me3d_joint"])
            articulation.append({"part": obj.name, "parent": obj.parent.name if obj.parent else None,
                                 "axis": j["axis"], "min_deg": j["min_deg"], "max_deg": j["max_deg"],
                                 "priority": j["priority"],
                                 "pivot_m": [round(v, 6) for v in obj.matrix_world.translation]})
        if obj.name.startswith("station__"):
            import math
            eul = obj.matrix_world.to_euler("XYZ")
            stations[obj.name] = {"location_m": [round(v, 6) for v in obj.matrix_world.translation],
                                  "rotation_deg": [round(math.degrees(a), 6) for a in eul]}
    articulation.sort(key=lambda a: a["part"])
    (ship_dir / "articulation.json").write_text(json.dumps(articulation, indent=1))
    (out_dir / "_stations.json").write_text(json.dumps(stations, indent=1))


def _blender_crew(out_dir: Path, worker_glb: Path):
    import math
    import bpy

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(worker_glb))
    keep = {"CharacterArmature|Idle": "idle", "CharacterArmature|Walk": "walk"}
    for action in list(bpy.data.actions):
        if action.name in keep:
            action.name = keep[action.name]
            action.use_fake_user = True
        else:
            bpy.data.actions.remove(action)
    arm = next(o for o in bpy.data.objects if o.type == "ARMATURE")
    # skinned meshes only: the importer also makes a bone-shape "Icosphere" in glTF_not_exported
    meshes = [o for o in bpy.data.objects if o.type == "MESH"
              and any(m.type == "ARMATURE" for m in o.modifiers)]
    for obj in [o for o in bpy.data.objects if o.type == "EMPTY" and o.name.endswith("_end")]:
        bpy.data.objects.remove(obj)  # leaf-bone tip helpers the importer adds
    # The source armature carries scale 100 and a -90 deg X turn (a cm-scale export), under a
    # "RootNode" empty. Unreal ignores parent transforms on skinned meshes, so left as is the
    # crew imports 100x too big. Bake every transform so the GLB is metres with identity
    # nodes, origin between the feet, and turn the figure to face +X (contract section 1).
    root = arm.parent
    for obj in [arm, *meshes]:
        mw = obj.matrix_world.copy()
        if obj is arm:
            obj.parent = None
            obj.matrix_world = mw
    if root is not None and root.type == "EMPTY":
        bpy.data.objects.remove(root)
    arm.rotation_mode = "XYZ"
    arm.rotation_euler.z += math.radians(90)  # glTF figures face +Z (Blender -Y); contract: +X
    every = [arm, *meshes]
    with bpy.context.temp_override(active_object=arm, object=arm, selected_objects=every,
                                   selected_editable_objects=every):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    # One skinned mesh, so Unreal gets one SkeletalMesh rather than four parts.
    names = [m.name for m in meshes]
    with bpy.context.temp_override(active_object=meshes[0], object=meshes[0], selected_objects=meshes,
                                   selected_editable_objects=meshes):
        bpy.ops.object.join()
    body = meshes[0]
    if any(n in bpy.data.objects for n in names[1:]):
        raise RuntimeError("crew meshes did not join")
    body.name = body.data.name = "Crew__Body"
    arm.name = "Armature"
    height = max((body.matrix_world @ v.co).z for v in body.data.vertices)
    if not 1.2 < height < 2.5:
        raise RuntimeError(f"crew height {height:.2f} m after baking transforms; expected metres")
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = bpy.data.actions["idle"]
    crew_dir = out_dir / "crew"
    crew_dir.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(crew_dir / f"{CREW_ID}.glb"), export_format="GLB",
                              export_yup=True, export_animations=True,
                              export_animation_mode="ACTIONS", export_force_sampling=True)


def _blender_main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    mode, out_dir = argv[0], Path(argv[1])
    if mode == "ship":
        _blender_ship(out_dir)
    else:
        _blender_crew(out_dir, Path(argv[2]))
    print("FIXTURE_BLENDER_OK", mode)


# --------------------------------------------------------------------------- host half
def _run_blender(*args):
    cmd = [BLENDER, "-b", "--factory-startup", "--python", str(Path(__file__).resolve()), "--", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if "FIXTURE_BLENDER_OK" not in proc.stdout:
        raise RuntimeError(f"Blender fixture step {args[0]} failed:\n{proc.stdout[-4000:]}\n{proc.stderr[-4000:]}")


def make_package(out_root: Path) -> Path:
    pkg = Path(out_root) / PACKAGE_ID
    if pkg.exists():
        shutil.rmtree(pkg)
    pkg.mkdir(parents=True)
    _run_blender("ship", str(pkg))
    _run_blender("crew", str(pkg), str(WORKER_GLB))
    stations = json.loads((pkg / "_stations.json").read_text())
    (pkg / "_stations.json").unlink()
    (pkg / "ship" / f"{SHIP_ID}.json").write_text(json.dumps({
        "schema": "strait.ship_model/1", "id": SHIP_ID, "name": "Fixture boat", "type": "patrol",
        "length_m": 12.0, "beam_m": 4.0, "draught_m": 1.0, "depth_m": 2.5,
        "notes": "test fixture for the Unreal import harness", "source": "make_fixture_package.py"},
        indent=1))
    shutil.copyfile(pkg / "crew" / f"{CREW_ID}.glb", pkg / "crew" / f"{CREW_ID_B}.glb")
    crew = []
    for crew_id, station, anim in ((CREW_ID, "station__helm", "idle"),
                                   (CREW_ID_B, "station__crane", "walk")):
        crew.append({"id": crew_id, "glb": f"crew/{crew_id}.glb", "station": station,
                     "animation": anim, **stations[station]})
    manifest = {
        "schema": "me3d.package/1", "id": PACKAGE_ID, "name": "Fixture boat with crew",
        "created": "2026-10-29T00:00:00Z", "units": "metres",
        "source_frame": "+X bow, +Y port, +Z up; glTF files are +Y up",
        "ship": {"id": SHIP_ID, "glb": f"ship/{SHIP_ID}.glb", "meta": f"ship/{SHIP_ID}.json",
                 "articulation": "ship/articulation.json"},
        "crew": crew,
        "research": None,
    }
    (pkg / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return pkg


if __name__ == "__main__":
    if IN_BLENDER:
        _blender_main()
    else:
        out = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent.parent / "unreal" / "out"
        print(make_package(out))
