"""Import an `me3d.package/1` into the harness project and prove it works (docs/CONTRACT.md s.9).

Runs INSIDE Unreal 5.8, headless, as a commandlet:

    UnrealEditor-Cmd Harness.uproject -run=pythonscript -script=<this file> -unattended -nullrhi

in two separate processes, chosen by environment variables (set by run_import_test.sh):

    ME3D_PACKAGE=<package dir>  ME3D_PHASE=import   build everything and save it
    ME3D_PACKAGE=<package dir>  ME3D_PHASE=verify   load the saved level from disk, check it,
                                                    write <package>/unreal_import_report.json
    ME3D_IMPORT_LOG=<phase-1 log>                   scanned for Error: lines by the verify phase

The checks run in the second process on purpose: everything they look at has come back from
disk, so "the actors survived the save" is proved rather than assumed (library:
unreal-58-landscape-creation-has-no-python-path - Python-spawned actors may not survive save).

Ship: Interchange *scene* import of the GLB (default glTF scene pipelines). It makes one
StaticMesh asset per glTF mesh and one StaticMeshActor per node, attached in the glTF
hierarchy, with each node's origin as the actor origin - so parts stay separate and pivots
are kept. Crew: Interchange *asset* import (SkeletalMesh + Skeleton + AnimSequences), later
crew reusing the first crew's Skeleton.
"""
import json
import math
import os
import sys
import traceback
from pathlib import Path

import unreal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import me3d_frames as fr  # noqa: E402

PKG_DIR = Path(os.environ["ME3D_PACKAGE"]).resolve()
PHASE = os.environ.get("ME3D_PHASE", "import")
IMPORT_LOG = os.environ.get("ME3D_IMPORT_LOG", "")
STATE_FILE = PKG_DIR / ".unreal_import_state.json"
REPORT_FILE = PKG_DIR / "unreal_import_report.json"
BEGIN, END = "ME3D_IMPORT_BEGIN", "ME3D_IMPORT_END"
TOL_CM = 1.0
TOL_DEG = 0.5

les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
actors_ss = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
assets_lib = unreal.EditorAssetLibrary


class Checks:
    def __init__(self, items=None):
        self.items = list(items or [])

    def add(self, name, ok, detail=""):
        self.items.append({"name": name, "pass": bool(ok), "detail": str(detail)})
        unreal.log(f"ME3D_CHECK {'PASS' if ok else 'FAIL'} {name}: {detail}")
        return ok


# ------------------------------------------------------------------------------------ helpers
def read_manifest():
    return json.loads((PKG_DIR / "manifest.json").read_text())


def paths_for(manifest):
    pid = manifest["id"]
    base = f"/Game/ME3D/{pid}"
    return base, f"{base}/L_{pid}"


def validate_manifest(m):
    problems = []
    if m.get("schema") != "me3d.package/1":
        problems.append(f"schema is {m.get('schema')!r}, expected 'me3d.package/1'")
    pid = m.get("id", "")
    if not pid or not all(c.isalnum() or c == "_" for c in pid):
        problems.append(f"id {pid!r} must be [A-Za-z0-9_]+ (Unreal asset names)")
    ship = m.get("ship") or {}
    for key in ("id", "glb", "articulation"):
        if key not in ship:
            problems.append(f"ship.{key} missing")
    for key in ("glb", "articulation", "meta"):
        if key in ship and not (PKG_DIR / ship[key]).is_file():
            problems.append(f"ship.{key} file not found: {ship[key]}")
    crew = m.get("crew")
    if not isinstance(crew, list):
        problems.append("crew must be a list")
        crew = []
    for i, c in enumerate(crew):
        for key in ("id", "glb", "station", "animation", "location_m", "rotation_deg"):
            if key not in c:
                problems.append(f"crew[{i}].{key} missing")
        if "glb" in c and not (PKG_DIR / c["glb"]).is_file():
            problems.append(f"crew[{i}].glb file not found: {c['glb']}")
        for key in ("location_m", "rotation_deg"):
            if key in c and (not isinstance(c[key], list) or len(c[key]) != 3):
                problems.append(f"crew[{i}].{key} must be [x, y, z]")
    return problems


def ue_vec(t):
    return unreal.Vector(float(t[0]), float(t[1]), float(t[2]))


def ue_rot(rpy):
    roll, pitch, yaw = rpy
    return unreal.Rotator(roll=float(roll), pitch=float(pitch), yaw=float(yaw))


def vtuple(v):
    return (v.x, v.y, v.z)


def all_actors():
    world = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    return list(unreal.GameplayStatics.get_all_actors_of_class(world, unreal.Actor))


def labelled(actors):
    """{label: actor} for our actors only (skips the level's built-in Brush/volumes/etc.)."""
    out = {}
    for a in actors:
        if isinstance(a, (unreal.StaticMeshActor, unreal.SkeletalMeshActor)) or \
                a.get_class().get_name() == "Actor":
            out[a.get_actor_label()] = a
    return out


def world_aabb(comp):
    lo, hi = comp.get_local_bounds()
    xf = comp.get_world_transform()
    pts = [vtuple(xf.transform_location(unreal.Vector(x, y, z)))
           for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
    return [min(p[i] for p in pts) for i in range(3)], [max(p[i] for p in pts) for i in range(3)]


def assets_of(path, cls):
    out = []
    for p in assets_lib.list_assets(path, recursive=True, include_folder=False):
        a = unreal.load_asset(p)
        if isinstance(a, cls):
            out.append(a)
    return out


def anim_name_matches(asset_name, anim, glb_stem):
    """Interchange names a glTF clip '<file stem><clip>' (seen on 5.8.3); accept the plain and
    separator forms too so a naming change in a later engine does not read as a missing clip."""
    return asset_name in (anim, glb_stem + anim, f"{glb_stem}_{anim}", f"{glb_stem}_Anim_{anim}")


def axes_close(rot_a, rot_b):
    xa = (rot_a.get_forward_vector(), rot_a.get_right_vector(), rot_a.get_up_vector())
    xb = (rot_b.get_forward_vector(), rot_b.get_right_vector(), rot_b.get_up_vector())
    worst = 0.0
    for a, b in zip(xa, xb):
        dot = max(-1.0, min(1.0, a.x * b.x + a.y * b.y + a.z * b.z))
        worst = max(worst, math.degrees(math.acos(dot)))
    return worst


def import_ship_scene(dest, glb):
    """Interchange scene import with the project's default glTF scene stack. Blocks until done
    (wait_until_all_tasks_done); the actors land in the level that is open."""
    mgr = unreal.InterchangeManager.get_interchange_manager_scripted()
    src = unreal.InterchangeManager.create_source_data(str(glb))
    params = unreal.ImportAssetParameters()
    params.is_automated = True
    params.replace_existing = True
    ok = mgr.import_scene(dest, src, params)
    mgr.wait_until_all_tasks_done(True)
    return ok


def import_crew_assets(dest, glb, skeleton=None):
    """AssetImportTask, which is synchronous. InterchangeManager.import_asset is NOT: in a
    commandlet its skeletal-mesh import never finished (5.8.3). To reuse a skeleton the task
    options must be an InterchangePipelineStackOverride; a bare pipeline in task.options is
    silently ignored and a new skeleton is made."""
    task = unreal.AssetImportTask()
    task.filename = str(glb)
    task.destination_path = dest
    task.automated = True
    task.replace_existing = True
    task.save = False
    if skeleton is not None:
        assets = unreal.InterchangeGenericAssetsPipeline()
        skp = assets.get_editor_property("common_skeletal_meshes_and_animations_properties")
        skp.set_editor_property("skeleton", skeleton)
        stack = unreal.InterchangePipelineStackOverride()
        stack.add_pipeline(assets)
        stack.add_pipeline(unreal.InterchangeGLTFPipeline())
        task.options = stack
    unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks([task])
    return [str(p) for p in task.imported_object_paths]


# ------------------------------------------------------------------------------------ phase 1
def phase_import():
    checks = Checks()
    state = {"checks": [], "completed": False}
    m = read_manifest()
    problems = validate_manifest(m)
    checks.add("manifest_valid", not problems, "; ".join(problems) or
               f"me3d.package/1 '{m['id']}', ship '{m['ship']['id']}', {len(m['crew'])} crew")
    if problems:
        state["checks"] = checks.items
        return state
    base, level = paths_for(m)
    state["level"] = level
    if not les.new_level(level):
        checks.add("level_created", False, f"new_level({level}) returned False")
        state["checks"] = checks.items
        return state
    unreal.log(BEGIN)

    # crew: one import per distinct id; later ones reuse the first skeleton
    crew_assets = {}
    shared_skeleton = None
    reuse_notes = []
    for c in m["crew"]:
        cid = c["id"]
        if cid in crew_assets:
            continue
        dest = f"{base}/Crew/{cid}/"
        import_crew_assets(dest, PKG_DIR / c["glb"], skeleton=shared_skeleton)
        meshes = assets_of(dest, unreal.SkeletalMesh)
        if not meshes and shared_skeleton is not None:
            reuse_notes.append(f"{cid}: import onto the shared skeleton produced nothing; "
                               "retried with its own skeleton")
            import_crew_assets(dest, PKG_DIR / c["glb"])
            meshes = assets_of(dest, unreal.SkeletalMesh)
        crew_assets[cid] = [x.get_path_name() for x in meshes]
        if meshes and shared_skeleton is None:
            shared_skeleton = meshes[0].get_editor_property("skeleton")
    state["crew_assets"] = crew_assets
    state["reuse_notes"] = reuse_notes

    # Ship AFTER crew, on purpose: on 5.8.3 an AssetImportTask issued right after an
    # Interchange scene import starts, never finishes, and returns nothing - the first crew
    # simply went missing while the second imported fine.
    ship_glb = PKG_DIR / m["ship"]["glb"]
    if not import_ship_scene(f"{base}/Ship/", ship_glb):
        checks.add("ship_scene_import", False, "InterchangeManager.import_scene returned False")


    # crew actors at their stations
    stations = labelled(all_actors())
    placed = []
    for i, c in enumerate(m["crew"]):
        label = f"Crew__{i}_{c['id']}"
        meshes = crew_assets.get(c["id"]) or []
        loc = fr.blender_to_ue_location_cm(c["location_m"])
        rot = fr.blender_to_ue_rotator(c["rotation_deg"])
        actor = actors_ss.spawn_actor_from_class(unreal.SkeletalMeshActor, ue_vec(loc), ue_rot(rot))
        actor.set_actor_label(label)
        comp = actor.get_editor_property("skeletal_mesh_component")
        anim_path = None
        if meshes:
            mesh = unreal.load_asset(meshes[0])
            comp.set_skeletal_mesh_asset(mesh)
            stem = Path(c["glb"]).stem
            skel = mesh.get_editor_property("skeleton")
            for a in assets_of(f"{base}/Crew/{c['id']}/", unreal.AnimSequence):
                if anim_name_matches(a.get_name(), c["animation"], stem) and \
                        a.get_editor_property("skeleton") == skel:
                    anim_path = a.get_path_name()
            if anim_path:
                comp.set_animation_mode(unreal.AnimationMode.ANIMATION_SINGLE_NODE)
                comp.override_animation_data(unreal.load_asset(anim_path), True, True, 0.0, 1.0)
        station = stations.get(c["station"])
        if station is not None:
            # ride with the part the station is on (a crane operator slews with the crane)
            actor.attach_to_actor(station, "", unreal.AttachmentRule.KEEP_WORLD,
                                  unreal.AttachmentRule.KEEP_WORLD, unreal.AttachmentRule.KEEP_WORLD, False)
        placed.append({"label": label, "station_found": station is not None, "anim": anim_path})
    state["crew_actors"] = placed

    saved_level = les.save_current_level()
    saved_all = unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)
    state["saved"] = {"level": bool(saved_level), "dirty_packages": bool(saved_all)}
    ours = labelled(all_actors())
    state["actors_before_save"] = sorted(ours)
    unreal.log(END)
    state["checks"] = checks.items
    state["completed"] = True
    return state


# ------------------------------------------------------------------------------------ phase 2
def check_log(checks):
    if not IMPORT_LOG or not Path(IMPORT_LOG).is_file():
        return checks.add("import_log_clean", False, f"import log not found: {IMPORT_LOG!r}")
    lines = Path(IMPORT_LOG).read_text(errors="replace").splitlines()
    inside, errors = False, []
    for line in lines:
        if BEGIN in line and "ME3D_CHECK" not in line:
            inside = True
        elif END in line:
            inside = False
        elif inside and "Error:" in line:
            errors.append(line.split("]", 2)[-1].strip())
    seen_end = any(END in ln for ln in lines)
    detail = f"{len(errors)} Error: line(s) during import" + (": " + " | ".join(errors[:5]) if errors else "")
    if not seen_end:
        detail += "; import never reached its end marker"
    return checks.add("import_log_clean", not errors and seen_end, detail)


def phase_verify():
    state = json.loads(STATE_FILE.read_text()) if STATE_FILE.is_file() else {}
    checks = Checks(state.get("checks", []))
    m = read_manifest()
    if not state.get("completed"):
        checks.add("import_phase_completed", False,
                   "the import process did not finish (see unreal_import.log)")
        return checks, state.get("level")
    base, level = paths_for(m)
    check_log(checks)

    if not les.load_level(level):
        checks.add("level_save_reload", False, f"load_level({level}) failed")
        return checks, level
    actors = labelled(all_actors())
    before = state.get("actors_before_save", [])
    missing = sorted(set(before) - set(actors))
    checks.add("level_save_reload", not missing and len(actors) == len(before),
               f"{len(before)} actors before save, {len(actors)} after reload from disk"
               + (f"; missing {missing}" if missing else ""))

    # ---- ship parts: separate meshes, one actor per glTF mesh node
    gltf = fr.read_glb_json(PKG_DIR / m["ship"]["glb"])
    mesh_nodes = fr.glb_mesh_nodes(gltf)
    distinct_meshes = {n["mesh"] for n in gltf.get("nodes", []) if "mesh" in n}
    sm_assets = assets_of(f"{base}/Ship/", unreal.StaticMesh)
    no_actor = [n for n in mesh_nodes if not (isinstance(actors.get(n), unreal.StaticMeshActor)
                and actors[n].static_mesh_component.static_mesh is not None)]
    checks.add("ship_parts_imported", len(sm_assets) == len(distinct_meshes) and not no_actor,
               f"GLB has {len(mesh_nodes)} mesh nodes / {len(distinct_meshes)} meshes; Unreal has "
               f"{len(sm_assets)} StaticMesh assets" + (f"; no mesh actor for {no_actor}" if no_actor else ""))
    wrong_parent = []
    for node, parent in mesh_nodes.items():
        a = actors.get(node)
        if a is None:
            continue
        got = a.get_attach_parent_actor()
        got = got.get_actor_label() if got else None
        if parent is not None and got != parent:
            wrong_parent.append(f"{node}: parent {got}, expected {parent}")
    checks.add("ship_hierarchy", not wrong_parent,
               "; ".join(wrong_parent) or f"all {len(mesh_nodes)} parts attached as in the GLB")

    # ---- articulation: own actor, attached to its parent, pivot, and it moves
    art = json.loads((PKG_DIR / m["ship"]["articulation"]).read_text())
    for j in art:
        name = f"articulated_part:{j['part']}"
        a = actors.get(j["part"])
        if not isinstance(a, unreal.StaticMeshActor):
            checks.add(name, False, f"no actor named {j['part']} in the level (not in the GLB?)")
            continue
        parent = a.get_attach_parent_actor()
        parent = parent.get_actor_label() if parent else None
        want_pivot = fr.blender_to_ue_location_cm(j["pivot_m"])
        got_pivot = vtuple(a.get_actor_location())
        err = fr.distance(want_pivot, got_pivot)
        comp = a.static_mesh_component
        lo0, hi0 = world_aabb(comp)
        start = a.get_actor_rotation()
        moved, used = 0.0, None
        for deg in (90.0, float(j["max_deg"]), float(j["min_deg"])):
            deg = max(float(j["min_deg"]), min(float(j["max_deg"]), deg))
            if abs(deg) < 1e-6:
                continue
            e = {"x": (deg, 0, 0), "y": (0, deg, 0), "z": (0, 0, deg)}[j["axis"]]
            delta = ue_rot(fr.blender_to_ue_rotator(e))
            a.add_actor_local_rotation(delta, False, False)
            lo1, hi1 = world_aabb(comp)
            a.set_actor_rotation(start, False)
            moved = max(fr.distance(lo0, lo1), fr.distance(hi0, hi1))
            used = deg
            if moved > TOL_CM:
                break
        ok = parent == j["parent"] and err <= TOL_CM and moved > TOL_CM
        checks.add(name, ok,
                   f"parent {parent} (expected {j['parent']}); pivot at "
                   f"({got_pivot[0]:.1f}, {got_pivot[1]:.1f}, {got_pivot[2]:.1f}) cm, "
                   f"{err:.2f} cm from pivot_m; rotating {used} deg about {j['axis']} moved its "
                   f"bounds {moved:.1f} cm")

    # ---- crew assets
    skeletons = {}
    for cid, paths in (state.get("crew_assets") or {}).items():
        meshes = [unreal.load_asset(p) for p in paths]
        meshes = [x for x in meshes if x is not None]
        skel = meshes[0].get_editor_property("skeleton") if meshes else None
        skeletons[cid] = skel
        checks.add(f"crew_skeleton:{cid}", bool(meshes) and skel is not None,
                   f"{len(meshes)} SkeletalMesh, skeleton {skel.get_path_name() if skel else None}")
        stem = next(Path(c["glb"]).stem for c in m["crew"] if c["id"] == cid)
        anims = [x for x in assets_of(f"{base}/Crew/{cid}/", unreal.AnimSequence)]
        wanted = sorted({c["animation"] for c in m["crew"] if c["id"] == cid})
        glb_clips = fr.glb_animation_names(fr.read_glb_json(PKG_DIR / next(
            c["glb"] for c in m["crew"] if c["id"] == cid)))
        for anim in wanted:
            hit = [x for x in anims if anim_name_matches(x.get_name(), anim, stem)
                   and x.get_editor_property("skeleton") == skel]
            checks.add(f"crew_animation:{cid}:{anim}", bool(hit),
                       f"AnimSequence {hit[0].get_path_name()} on {skel.get_name() if skel else None}"
                       if hit else f"no AnimSequence for '{anim}' on this skeleton; GLB clips are "
                       f"{glb_clips}; imported {[x.get_name() for x in anims]}")
    distinct = {s.get_path_name() for s in skeletons.values() if s is not None}
    checks.add("crew_shared_skeleton", len(distinct) == 1 if skeletons else True,
               f"{len(skeletons)} crew asset set(s) on {len(distinct)} skeleton(s)"
               + ("; " + "; ".join(state.get("reuse_notes") or []) if state.get("reuse_notes") else ""))

    # ---- crew actors placed and animating
    for i, c in enumerate(m["crew"]):
        label = f"Crew__{i}_{c['id']}"
        name = f"crew_actor:{i}:{c['station']}"
        a = actors.get(label)
        if not isinstance(a, unreal.SkeletalMeshActor):
            checks.add(name, False, f"actor {label} missing after reload")
            continue
        want_loc = fr.blender_to_ue_location_cm(c["location_m"])
        got_loc = vtuple(a.get_actor_location())
        err = fr.distance(want_loc, got_loc)
        ang = axes_close(a.get_actor_rotation(), ue_rot(fr.blender_to_ue_rotator(c["rotation_deg"])))
        comp = a.get_editor_property("skeletal_mesh_component")
        mode = comp.get_editor_property("animation_mode")
        data = comp.get_editor_property("animation_data")
        anim = data.get_editor_property("anim_to_play")
        looping = data.get_editor_property("saved_looping")
        anim_ok = (anim is not None and mode == unreal.AnimationMode.ANIMATION_SINGLE_NODE and looping
                   and anim_name_matches(anim.get_name(), c["animation"], Path(c["glb"]).stem))
        parent = a.get_attach_parent_actor()
        # Independent cross-check: the station empty that Epic's glTF importer placed from the
        # ship GLB. The manifest-vs-actor comparison above uses our own frame conversion both
        # ways, so on its own it could not catch a wrong conversion; this one can.
        st = actors.get(c["station"])
        if st is None:
            st_note, st_ok = f"station {c['station']} not found in the imported ship", False
        else:
            st_err = fr.distance(vtuple(st.get_actor_location()), got_loc)
            st_ang = axes_close(st.get_actor_rotation(), a.get_actor_rotation())
            st_ok = st_err <= TOL_CM and st_ang <= TOL_DEG
            st_note = f"{st_err:.2f} cm and {st_ang:.2f} deg from the ship's own {c['station']}"
        ok = (err <= TOL_CM and ang <= TOL_DEG and st_ok and anim_ok
              and comp.get_skeletal_mesh_asset() is not None)
        checks.add(name, ok,
                   f"{label} at ({got_loc[0]:.1f}, {got_loc[1]:.1f}, {got_loc[2]:.1f}) cm, {err:.2f} cm "
                   f"and {ang:.2f} deg from the manifest, {st_note}; playing "
                   f"{anim.get_name() if anim else None} (looping={looping}, mode={mode.name}); "
                   f"attached to {parent.get_actor_label() if parent else None}")
    return checks, level


def main():
    if PHASE == "import":
        if STATE_FILE.exists():
            STATE_FILE.unlink()
        try:
            state = phase_import()
        except Exception:
            state = {"completed": False, "error": traceback.format_exc()}
            unreal.log_error("ME3D import failed:\n" + state["error"])
        STATE_FILE.write_text(json.dumps(state, indent=1))
        return
    level = None
    try:
        checks, level = phase_verify()
    except Exception:
        tb = traceback.format_exc()
        checks = Checks()
        checks.add("verify_completed", False, tb.strip().splitlines()[-1])
        unreal.log_error("ME3D verify failed:\n" + tb)
    if level is None:
        try:
            level = paths_for(read_manifest())[1]
        except Exception:
            level = None
    ok = bool(checks.items) and all(c["pass"] for c in checks.items)
    report = {"ok": ok, "engine": unreal.SystemLibrary.get_engine_version().split("-")[0][:3],
              "engine_version": unreal.SystemLibrary.get_engine_version(),
              "level": level, "checks": checks.items}
    REPORT_FILE.write_text(json.dumps(report, indent=1))
    unreal.log(f"ME3D_REPORT ok={ok} -> {REPORT_FILE}")


main()
