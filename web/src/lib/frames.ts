// Frames and camera views (CONTRACT §1). Pure, unit tested.
// Blender: +X bow, +Y port, +Z up. glTF/three: Y up; Blender's exporter maps
// (x, y, z)_blender → (x, z, −y)_gltf, so bow = +X, port = −Z, up = +Y.
import type { Vec3 } from '../types';

export function blenderToGltf([x, y, z]: Vec3): Vec3 {
  return [x, z, -y];
}

export function gltfToBlender([x, y, z]: Vec3): Vec3 {
  return [x, -z, y];
}

/** A joint axis in the part's local Blender frame, expressed in its local glTF frame. */
export function jointAxisGltf(axis: 'x' | 'y' | 'z' | string): Vec3 {
  switch (axis) {
    case 'x':
      return [1, 0, 0];
    case 'y':
      return [0, 0, -1];
    case 'z':
      return [0, 1, 0];
    default:
      return [0, 1, 0];
  }
}

export type ViewName = 'port' | 'starboard' | 'top' | 'bow' | 'stern' | 'orbit';

export interface Bounds {
  min: Vec3;
  max: Vec3;
}

/**
 * Camera position and target that frame `b` (glTF coords) from a named side.
 * Distance fits the bounding sphere into a vertical field of view `fovDeg`.
 */
export function cameraFor(view: ViewName, b: Bounds, fovDeg = 40, aspect = 16 / 9): { position: Vec3; target: Vec3 } {
  const c: Vec3 = [(b.min[0] + b.max[0]) / 2, (b.min[1] + b.max[1]) / 2, (b.min[2] + b.max[2]) / 2];
  const size: Vec3 = [b.max[0] - b.min[0], b.max[1] - b.min[1], b.max[2] - b.min[2]];
  const radius = Math.max(0.5, Math.hypot(size[0], size[1], size[2]) / 2);
  const vfov = (fovDeg * Math.PI) / 180;
  const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect);
  const d = (radius / Math.sin(Math.min(vfov, hfov) / 2)) * 1.05;
  const dir: Record<ViewName, Vec3> = {
    port: [0, 0.12, -1],
    starboard: [0, 0.12, 1],
    bow: [1, 0.15, 0],
    stern: [-1, 0.15, 0],
    top: [0, 1, -0.02], // a hair to port so "up" on screen is well defined: bow points left, as in Port view
    orbit: [0.75, 0.45, -0.75],
  };
  const v = dir[view];
  const len = Math.hypot(v[0], v[1], v[2]);
  return { position: [c[0] + (v[0] / len) * d, c[1] + (v[1] / len) * d, c[2] + (v[2] / len) * d], target: c };
}
