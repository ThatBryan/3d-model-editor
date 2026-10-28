// Writes the small GLBs and parts lists that mock mode (VITE_MOCK=1) serves from public/mock/.
// Development only: the real app loads models the server built in Blender.
// Run: npm run mock:assets
import { writeFileSync, mkdirSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import * as THREE from 'three';
import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js';

// GLTFExporter uses FileReader to pack the binary; Node has Blob but no FileReader.
globalThis.FileReader = class {
  readAsArrayBuffer(blob) {
    blob.arrayBuffer().then((b) => { this.result = b; this.onloadend?.({ target: this }); this.onload?.({ target: this }); });
  }
  readAsDataURL(blob) {
    blob.arrayBuffer().then((b) => {
      this.result = `data:${blob.type || 'application/octet-stream'};base64,` + Buffer.from(b).toString('base64');
      this.onloadend?.({ target: this }); this.onload?.({ target: this });
    });
  }
};

const out = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'mock');
mkdirSync(out, { recursive: true });

const mat = (hex, extra = {}) => new THREE.MeshStandardMaterial({ color: hex, roughness: 0.7, metalness: 0.1, ...extra });
const box = (name, w, h, d, color, pos = [0, 0, 0]) => {
  const m = new THREE.Mesh(new THREE.BoxGeometry(w, h, d), mat(color));
  m.name = name; m.position.set(...pos); return m;
};
const empty = (name, pos = [0, 0, 0]) => { const g = new THREE.Object3D(); g.name = name; g.position.set(...pos); return g; };

// Joints are recorded here and written to parts.json as the builder would (CONTRACT §3).
// Axis is in the Blender local frame ('z' = up = three's Y).
const joints = {};
const joint = (name, axis, min, max, priority) => { joints[name] = { axis, min_deg: min, max_deg: max, priority, kind: 'revolute' }; };

function makeShip({ lightX }) {
  const root = new THREE.Group(); root.name = 'Scene';
  // Hull: a tapered box. Bow +X, port −Z (glTF frame). Waterline y = 0.
  const hullGeo = new THREE.BoxGeometry(16, 1.6, 4.2, 8, 1, 1);
  const p = hullGeo.attributes.position;
  for (let i = 0; i < p.count; i++) {
    const x = p.getX(i), y = p.getY(i);
    const t = Math.max(0, (x - 3) / 5); // narrow towards the bow
    p.setZ(i, p.getZ(i) * (1 - 0.85 * t) * (y < 0 ? 0.75 : 1));
    if (x > 7.9) p.setY(i, y + 0.35);
  }
  hullGeo.computeVertexNormals();
  const hull = new THREE.Mesh(hullGeo, mat(0x9aa3ad)); hull.name = 'Hull__Hull'; hull.position.set(0, -0.2, 0);
  root.add(hull);
  hull.add(box('Hull__Fender', 15.6, 0.3, 4.5, 0x1b1d21, [-0.2, 0.55, 0]));

  const cabin = box('Cabin__Cabin', 5, 1.8, 3.2, 0xd9dde2, [0.5, 1.5, 0]);
  hull.add(cabin);
  const glass = box('Cabin__Windows', 0.1, 0.7, 2.8, 0x14202c, [2.52, 0.35, 0]);
  glass.material.metalness = 0.6; cabin.add(glass);
  const door = empty('Cabin__Door', [-1.2, -0.1, 1.61]); // hinge
  door.add(box('Cabin__Door_panel', 0.8, 1.4, 0.06, 0x2b3038, [0.4, 0, 0]));
  cabin.add(door); joint('Cabin__Door', 'z', 0, 100, 'P1');
  const wipers = empty('Cabin__Wipers', [2.6, 0.2, 0]);
  wipers.add(box('Cabin__Wipers_blade', 0.05, 0.6, 0.06, 0x111111, [0, 0.3, 0]));
  cabin.add(wipers); joint('Cabin__Wipers', 'x', -60, 60, 'P1');

  const light = empty('Roof__Searchlight', [lightX, 1.15, 0.6]);
  const housing = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 0.45, 16), mat(0x2b3038));
  housing.rotation.z = Math.PI / 2; housing.name = 'Roof__Searchlight_housing'; light.add(housing);
  const lens = new THREE.Mesh(new THREE.CircleGeometry(0.2, 16), mat(0xfff3c4, { emissive: 0x332a00 }));
  lens.name = 'Roof__Searchlight__Lens'; lens.position.set(0.23, 0, 0); lens.rotation.y = Math.PI / 2; light.add(lens);
  cabin.add(light); joint('Roof__Searchlight', 'z', -170, 170, 'P1');

  const radome = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.45, 0.3, 24), mat(0xe4e6e8));
  radome.name = 'Roof__Radome'; radome.position.set(-0.4, 1.05, -0.4); cabin.add(radome);
  const mast = box('Mast__Mast', 0.12, 1.6, 0.12, 0x7d8794, [-1.3, 1.7, 0]);
  cabin.add(mast);
  const cam = empty('Mast__Camera', [0, 0.85, 0]);
  cam.add(box('Mast__Camera_head', 0.25, 0.2, 0.2, 0x2b3038, [0.05, 0, 0]));
  mast.add(cam); joint('Mast__Camera', 'z', -180, 180, 'P1');
  cabin.add(empty('station__helm', [1.2, -0.9, 0.5]));

  // Four outboards on the transom, each steering about its vertical pivot.
  [-1.5, -0.5, 0.5, 1.5].forEach((z, i) => {
    const n = `Transom__Outboard_${i + 1}`;
    const ob = empty(n, [-8.1, 0.5, z]);
    ob.add(box(`${n}_cowl`, 0.6, 0.8, 0.45, 0x1b1d21, [-0.3, 0.2, 0]));
    const leg = box(`${n}_leg`, 0.18, 1.2, 0.12, 0x22262c, [-0.35, -0.6, 0]);
    ob.add(leg);
    const prop = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.08, 12), mat(0x8a8f96));
    prop.name = `${n}__Prop`; prop.rotation.z = Math.PI / 2; prop.position.set(-0.35, -1.05, 0); ob.add(prop);
    hull.add(ob); joint(n, 'z', -30, 30, 'P0');
  });
  hull.add(empty('station__aft_port', [-5.5, 0.7, -1.2]));
  hull.add(empty('station__aft_starboard', [-5.5, 0.7, 1.2]));
  hull.add(empty('station__foredeck', [5, 0.8, 0]));
  return root;
}

function partsOf(root) {
  root.updateMatrixWorld(true);
  const rows = [];
  const isPart = (n) => /^[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*(?:__[A-Za-z0-9]+(?:_[A-Za-z0-9]+)*)+$/.test(n) && !/_(panel|blade|housing|cowl|leg|head)$/.test(n);
  root.traverse((o) => {
    if (o === root || !isPart(o.name)) return;
    const box3 = new THREE.Box3().setFromObject(o);
    const station = o.name.startsWith('station__');
    if (station) box3.setFromCenterAndSize(o.getWorldPosition(new THREE.Vector3()), new THREE.Vector3(0.01, 0.01, 0.01));
    let tris = 0;
    o.traverse((m) => { if (m.isMesh) tris += (m.geometry.index ? m.geometry.index.count : m.geometry.attributes.position.count) / 3; });
    let parent = o.parent; while (parent && parent !== root && !isPart(parent.name)) parent = parent.parent;
    const wp = o.getWorldPosition(new THREE.Vector3());
    const eul = new THREE.Euler().setFromQuaternion(o.getWorldQuaternion(new THREE.Quaternion()));
    const r = (v) => Math.round(v * 1000) / 1000;
    rows.push({
      path: o.name,
      label: o.name.split('__').map((s) => s.replace(/_/g, ' ')).join(' › '),
      parent: parent && parent !== root ? parent.name : null,
      joint: joints[o.name] ?? null,
      station: station ? { pose: o.name.includes('helm') ? 'seated' : 'standing' } : null,
      origin_m: [r(wp.x), r(-wp.z), r(wp.y)],
      rotation_deg: [r(THREE.MathUtils.radToDeg(eul.x)), r(THREE.MathUtils.radToDeg(-eul.z)), r(THREE.MathUtils.radToDeg(eul.y))],
      bounds_min: [r(box3.min.x), r(-box3.max.z), r(box3.min.y)],
      bounds_max: [r(box3.max.x), r(-box3.min.z), r(box3.max.y)],
      triangles: Math.round(tris),
    });
  });
  return rows;
}

function makeCrew({ suit = 0x2b3e63, skin = 0xd9a97c } = {}) {
  const root = new THREE.Group(); root.name = 'Scene';
  const hips = empty('Body__Hips', [0, 0.95, 0]); root.add(hips);
  hips.add(box('Body__Torso', 0.28, 0.6, 0.42, suit, [0, 0.33, 0]));
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.12, 16, 12), mat(skin)); head.name = 'Body__Head'; head.position.set(0, 0.78, 0); hips.add(head);
  const limb = (name, pos, len, color, w = 0.11) => { const j = empty(name, pos); j.add(box(name + '_mesh', w, len, w, color, [0, -len / 2, 0])); return j; };
  const armL = limb('Body__Arm_L', [0, 0.6, -0.27], 0.62, suit); const armR = limb('Body__Arm_R', [0, 0.6, 0.27], 0.62, suit);
  const legL = limb('Body__Leg_L', [0, 0, -0.11], 0.92, 0x22324f, 0.14); const legR = limb('Body__Leg_R', [0, 0, 0.11], 0.92, 0x22324f, 0.14);
  hips.add(armL, armR, legL, legR);
  // Animations named per the crew spec (CONTRACT §6).
  const q = (x, y, z) => new THREE.Quaternion().setFromEuler(new THREE.Euler(x, y, z)).toArray();
  const qt = (node, times, eulers) => new THREE.QuaternionKeyframeTrack(`${node}.quaternion`, times, eulers.flatMap((e) => q(...e)));
  const pt = (node, times, ps) => new THREE.VectorKeyframeTrack(`${node}.position`, times, ps.flat());
  const swing = (a) => [[0, 0, a], [0, 0, -a], [0, 0, a]];
  const clips = [
    new THREE.AnimationClip('idle', 2, [pt('Body__Hips', [0, 1, 2], [[0, 0.95, 0], [0, 0.94, 0], [0, 0.95, 0]]), qt('Body__Arm_L', [0, 1, 2], [[0.05, 0, 0], [0.08, 0, 0.03], [0.05, 0, 0]])]),
    new THREE.AnimationClip('walk', 1, [
      qt('Body__Leg_L', [0, 0.5, 1], swing(0.45)), qt('Body__Leg_R', [0, 0.5, 1], swing(-0.45)),
      qt('Body__Arm_L', [0, 0.5, 1], swing(-0.35)), qt('Body__Arm_R', [0, 0.5, 1], swing(0.35)),
    ]),
    new THREE.AnimationClip('brace', 2.6, [
      pt('Body__Hips', [0, 0.4, 2.1, 2.6], [[0, 0.95, 0], [0, 0.8, 0], [0, 0.8, 0], [0, 0.95, 0]]),
      qt('Body__Leg_L', [0, 0.4, 2.1, 2.6], [[0, 0, 0], [0, 0, 0.5], [0, 0, 0.5], [0, 0, 0]]),
      qt('Body__Leg_R', [0, 0.4, 2.1, 2.6], [[0, 0, 0], [0, 0, 0.5], [0, 0, 0.5], [0, 0, 0]]),
      qt('Body__Arm_L', [0, 0.4, 2.1, 2.6], [[0, 0, 0], [-0.9, 0, 0.3], [-0.9, 0, 0.3], [0, 0, 0]]),
    ]),
    new THREE.AnimationClip('hands_up', 2, [
      qt('Body__Arm_L', [0, 0.6, 2], [[0, 0, 0], [-2.8, 0, 0], [-2.8, 0, 0]]),
      qt('Body__Arm_R', [0, 0.6, 2], [[0, 0, 0], [2.8, 0, 0], [2.8, 0, 0]]),
    ]),
    new THREE.AnimationClip('squat', 2, [
      pt('Body__Hips', [0, 1, 2], [[0, 0.95, 0], [0, 0.55, 0], [0, 0.95, 0]]),
      qt('Body__Leg_L', [0, 1, 2], [[0, 0, 0], [0, 0, 1.2], [0, 0, 0]]),
      qt('Body__Leg_R', [0, 1, 2], [[0, 0, 0], [0, 0, 1.2], [0, 0, 0]]),
      qt('Body__Arm_L', [0, 1, 2], [[0, 0, 0], [0, 0, 1.2], [0, 0, 0]]),
      qt('Body__Arm_R', [0, 1, 2], [[0, 0, 0], [0, 0, 1.2], [0, 0, 0]]),
    ]),
  ];
  return { root, clips };
}

async function exportGlb(root, file, animations = []) {
  const ab = await new GLTFExporter().parseAsync(root, { binary: true, animations });
  writeFileSync(join(out, file), Buffer.from(ab));
  console.log('wrote', file, ab.byteLength, 'bytes');
}

const v1 = makeShip({ lightX: 1.6 });
const v2 = makeShip({ lightX: 1.2 }); // "moved the searchlight 0.4 m aft"
writeFileSync(join(out, 'ship_parts.json'), JSON.stringify(partsOf(v1), null, 1));
await exportGlb(v1, 'ship_v1.glb');
await exportGlb(v2, 'ship_v2.glb');
const crewA = makeCrew();
await exportGlb(crewA.root, 'crew_a.glb', crewA.clips);
const crewB = makeCrew({ suit: 0x3c5a7a, skin: 0x7e5232 });
await exportGlb(crewB.root, 'crew_b.glb', crewB.clips);
