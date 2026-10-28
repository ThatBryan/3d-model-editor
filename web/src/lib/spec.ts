// Spec patch helpers. Pure, unit tested.
// The server deep-merges `patch` into the spec (CONTRACT §10). Arrays are not merged by a
// deep merge in any useful way, so the UI always sends whole arrays (e.g. `animations`).

export type Json = null | boolean | number | string | Json[] | { [k: string]: Json };

function isObj(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

/** Deep-merge b into a (b wins; arrays replaced). Used to coalesce patches while a build runs. */
export function mergePatch<T extends Record<string, unknown>>(a: T, b: Record<string, unknown>): T {
  const out: Record<string, unknown> = { ...a };
  for (const [k, v] of Object.entries(b)) {
    out[k] = isObj(v) && isObj(out[k]) ? mergePatch(out[k] as Record<string, unknown>, v) : v;
  }
  return out as T;
}

/** Toggle membership of `item` in a list, keeping order. */
export function toggleIn(list: string[], item: string): string[] {
  return list.includes(item) ? list.filter((x) => x !== item) : [...list, item];
}

export type ClothesSlot = 'suit' | 'shoes' | 'hat';

/**
 * The catalogue lists clothes as bare asset names (CONTRACT §10 `clothes: [str]`), while the crew
 * spec has suit / shoes / hat slots. Until the catalogue says which slot an item fills, guess it
 * from the name. Flagged to the contract owner.
 */
export function clothesSlot(name: string): ClothesSlot {
  const n = name.toLowerCase();
  if (/(shoe|boot|sneaker|sandal|footwear)/.test(n)) return 'shoes';
  if (/(hat|cap|helmet|beret|hood|beanie|fedora|turban)/.test(n)) return 'hat';
  return 'suit';
}

export function groupClothes(items: string[]): Record<ClothesSlot, string[]> {
  const out: Record<ClothesSlot, string[]> = { suit: [], shoes: [], hat: [] };
  for (const i of items) out[clothesSlot(i)].push(i);
  return out;
}

/** "male_worksuit01" → "Male worksuit 01". */
export function assetLabel(name: string): string {
  const s = name.replace(/_/g, ' ').replace(/([a-z])(\d)/gi, '$1 $2').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
