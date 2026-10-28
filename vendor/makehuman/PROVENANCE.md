# MakeHuman system assets — provenance and licence

| | |
|---|---|
| What | MakeHuman system asset pack (clothes, shoes, hats, hair, eyebrows, eyelashes, eyes, teeth, tongue, skins, proxy meshes) |
| Source | https://files.makehumancommunity.org/asset_packs/makehuman_system_assets/makehuman_system_assets_cc0.zip (mirror: files2.makehumancommunity.org) |
| Downloaded | 2026-10-29 |
| File | `vendor/downloads/makehuman_system_assets_cc0.zip` (git-ignored), 280,737,770 bytes |
| sha256 | `b542127a8e25547c7c29c19f2d1d2adb9a664c80396ecd694095dbc8028a0107` |
| Licence | **CC0 1.0 Universal** (public domain dedication), https://creativecommons.org/publicdomain/zero/1.0/legalcode |
| Evidence | Every asset's `packs/makehuman_system_assets.json` entry has `"license": "CC0"`; every `.mhclo`, `.proxy` and `.mhmat` header reads "This asset was explicitly released as CC0 in september 2020", copyright holders at release: Data Collection AB, Joel Palmius, Jonas Hauquier. |
| Installed by | `tools/install_mpfb_assets.sh` into MPFB2's user data folder (`~/Library/Application Support/Blender/5.2/extensions/.user/blender_org/mpfb/data`), the same way MPFB's own `mpfb.load_pack` operator does. Nothing from the pack is committed to this repo. |

The base mesh, targets and rigs used by the crew builder come from the MPFB2 extension itself
(GPL-3.0-or-later code; its bundled data — base mesh, targets, rigs, weights — is CC0 per the
MakeHuman project). Our exported characters contain only CC0 data plus our own procedural
equipment meshes and animations.
