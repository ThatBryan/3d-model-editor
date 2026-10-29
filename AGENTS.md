# 3D model editor: repository guide

An AI-driven editor for simulator 3D models: ships with moving parts, human crew, and crew placed
on ships, exported as one package that Unreal Engine imports (MAK later). Lester owns the product;
he is not an engineer. The approved design is the canvas linked in `docs/CONTRACT.md`; the plan is
`docs/PLAN.md`. **`docs/CONTRACT.md` is the source of truth for every shape shared between parts.**

## Layout

| Path | What | Run with |
|---|---|---|
| `blender/` | scripts that run **inside** Blender: ship builders, crew builder, shared helpers | Blender 5.2 headless |
| `catalog/` | default specs: `ships/*.json`, `crew/*.json` | |
| `server/` | FastAPI app, project store, job runner, AI agent (Claude Agent SDK), packaging | `server/.venv` (Python 3.11) |
| `web/` | Vite + React + TypeScript + three.js front end | Node 22 (`~/.nvm/versions/node/v22.23.1/bin`) |
| `unreal/` | throwaway UE 5.8 harness project and import test | `unreal/run_import_test.sh` |
| `tests/` | cross-part tests (end to end) | |
| `vendor/` | third-party assets, each with its licence; `vendor/downloads/` is ignored | |

## Tools on this Mac

- Blender: `/Applications/Blender.app/Contents/MacOS/Blender` (5.2.1). MPFB2 is installed as the
  user extension `bl_ext.blender_org.mpfb`.
- Unreal: `/Users/Shared/Epic Games/UE_5.8` (`Engine/Binaries/Mac/UnrealEditor-Cmd`).
- The AI uses the local Claude Code login through `claude-agent-sdk`; no API key is set or needed.

## Windows

Everything except the Unreal harness (macOS-only) runs on Windows. `server/app/config.py` picks
Windows defaults; override any of them with `ME3D_BLENDER`, `ME3D_MPFB_DIR`, `ME3D_UNREAL_DIR`.

- Blender 5.2: `winget install BlenderFoundation.Blender` →
  `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`. MPFB2:
  `blender --online-mode -c extension install -s -e mpfb`. Asset pack: run
  `bash tools/install_mpfb_assets.sh` from Git Bash.
- Python 3.11: `py -3.11 -m venv server\.venv`, then
  `server\.venv\Scripts\python -m pip install -r server\requirements.txt`.
- Node 22. If Node is managed by nvm-windows, use `nvm install 22` / `nvm use 22`; a Node MSI
  installs *through* nvm's symlink into the active version's folder and breaks it.
- Run: `start.cmd` (or double-click it) starts the server and the web app and opens
  http://localhost:5173; Ctrl+C stops both. `start.cmd -Mock` runs the web app alone on canned
  data, `-NoBrowser` skips the browser. By hand: `server\.venv\Scripts\python -m uvicorn
  app.main:app --port 8787 --app-dir server`, and in a second terminal `cd web; npm run dev`.
- In the gates below, use `server\.venv\Scripts\python` for `server/.venv/bin/python`.

## Gates

- Server: `server/.venv/bin/python -m pytest server/tests -q`
- Blender builds: `server/.venv/bin/python -m pytest tests/blender -q` (slow; runs Blender)
- Web: `cd web && npm run typecheck && npm run build`
- Unreal: `unreal/run_import_test.sh <package_dir>`, which reads the report, not Unreal's exit code
- End to end: `server/.venv/bin/python -m pytest tests/e2e -q`

Read a gate's exit code from the command itself, never through a pipe.

## Rules

- Stage explicit paths; never `git add -A` or `git add .`.
- Never edit `/Users/wyxlester/dev/straitssim-w1`: another session owns it. Reading and copying
  ideas from it is fine.
- Every third-party asset records its source and licence beside it. CC0 or our own work only.
- Pure logic (frames, transforms, spec merging, packaging) gets unit tests that have been seen to
  fail. Wiring that fails loudly is checked by running it.
