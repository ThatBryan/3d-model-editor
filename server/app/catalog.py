"""Reads catalog/ships/<type>.json and catalog/crew/<id>.json.

A catalog file is a default spec plus documentation (description, param_docs, options). The
builders own those files and may add doc keys; the spec is whatever the contract's spec schema
names, so we keep exactly those keys and treat everything else as documentation.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

# "meta" is not in contract §5 but the ship catalog carries it: the strait.ship_model/1 fields
# (speeds, propulsion, notes) that the package's ship/<id>.json needs and params do not hold.
SHIP_SPEC_KEYS = ("schema", "type", "id", "name", "params", "meta", "overrides", "joint_limits", "custom_ops")
CREW_SPEC_KEYS = ("schema", "id", "name", "body", "clothes", "equipment", "animations")
SAFE_NAME = __import__("re").compile(r"^[A-Za-z0-9_]+$")


class CatalogError(Exception):
    pass


class Catalog:
    def __init__(self, root: Path):
        self.root = root

    def _read(self, kind: str, base: str) -> dict:
        if not SAFE_NAME.match(base or ""):
            raise CatalogError(f"Bad catalog name: {base!r}")
        folder = "ships" if kind == "ship" else "crew"
        path = self.root / folder / f"{base}.json"
        if not path.exists():
            raise CatalogError(f"No {kind} called {base!r} in the catalog ({path}).")
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as e:
            raise CatalogError(f"{path} is not valid JSON: {e}") from e
        if not isinstance(data, dict):
            raise CatalogError(f"{path} is not a JSON object")
        return data

    def entry(self, kind: str, base: str) -> dict:
        return self._read(kind, base)

    def default_spec(self, kind: str, base: str) -> dict:
        data = self._read(kind, base)
        src = data["spec"] if isinstance(data.get("spec"), dict) else data
        keys = SHIP_SPEC_KEYS if kind == "ship" else CREW_SPEC_KEYS
        spec = {k: copy.deepcopy(src[k]) for k in keys if k in src}
        if kind == "ship":
            spec.setdefault("schema", "me3d.ship_spec/1")
            spec.setdefault("type", base)
            spec.setdefault("id", base)
            spec.setdefault("name", base.replace("_", " ").capitalize())
            for k, empty in (("params", {}), ("overrides", {}), ("joint_limits", {}), ("custom_ops", [])):
                spec.setdefault(k, empty)
        else:
            spec.setdefault("schema", "me3d.crew_spec/1")
            spec.setdefault("id", f"crew_{base}")
            spec.setdefault("name", base.replace("_", " ").capitalize())
            for k, empty in (("body", {}), ("clothes", {}), ("equipment", []), ("animations", [])):
                spec.setdefault(k, empty)
        return spec

    def _list(self, folder: str) -> list[tuple[str, dict]]:
        out = []
        d = self.root / folder
        if not d.is_dir():
            return out
        for p in sorted(d.glob("*.json")):
            try:
                data = json.loads(p.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                out.append((p.stem, data))
        return out

    @staticmethod
    def _options(data: dict) -> dict:
        opts = data.get("options")
        return opts if isinstance(opts, dict) else {}

    def summary(self) -> dict:
        ships = []
        for stem, data in self._list("ships"):
            spec = data.get("spec", data)
            ships.append({"type": spec.get("type", stem), "name": spec.get("name", stem),
                          "description": data.get("description", "")})
        crew, clothes, equipment, animations = [], [], [], []

        def add(target: list, values):
            if isinstance(values, dict):
                values = list(values.keys())
            if isinstance(values, list):
                for v in values:
                    name = v.get("id") or v.get("name") if isinstance(v, dict) else v
                    if isinstance(name, str) and name not in target:
                        target.append(name)

        for stem, data in self._list("crew"):
            spec = data.get("spec", data)
            crew.append({"id": stem, "name": spec.get("name", stem)})
            opts = self._options(data)
            cl = opts.get("clothes")
            if isinstance(cl, dict):
                for v in cl.values():
                    add(clothes, v)
            else:
                add(clothes, cl)
            for slot in ("suit", "shoes", "hat"):
                add(clothes, opts.get(slot))
            add(equipment, opts.get("equipment"))
            add(animations, opts.get("animations"))
        return {"ships": ships, "crew": crew, "clothes": clothes, "equipment": equipment,
                "animations": animations}
