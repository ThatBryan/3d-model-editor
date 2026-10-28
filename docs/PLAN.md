# Plan: AI-driven 3D model editor — ships, humans, and crew on ships

## Context

Today a ship model reaches the sim only after three handoffs: PM (requirements from web photos) → 3D modellers → IG, CGF and IOS developers. Each group is slow compared with AI, and **nobody owns putting humans on ships**, which simulation needs. You have the domain knowledge but are blocked by others' availability.

Goal: a desktop-style GUI where you do everything you can do with Claude Code today (research, build, edit, iterate), aimed at 3D: **ships, humans, and humans placed on ships**. It exports a package that drops into Unreal now and MAK later.

`/Users/wyxlester/dev/3d_model_editor` is empty (not a git repo). StraitsSim (`/Users/wyxlester/dev/straitssim-w1`) has already proven each hard piece once, by hand. Reuse the approach; do not edit StraitsSim, which belongs to another session.

| Piece | Proven in StraitsSim |
|---|---|
| AI drives Blender | `tools/blender_exec.py`: socket to the MCP add-on on port 9876 |
| Ship builders as code | `models/shipkit/` (`shipkit.py`, `drive.py`, `export.py`) and `models/ships/<id>/` |
| Research before building | per-ship `ASSUMPTIONS.md` and `*_spec.py`, e.g. `models/ships/pcg_pc303/` |
| Ship hand-over contract | `docs/model-export-contract.md` (metres, axes, waterline origin, 9 sockets, JSON), checked by `strait ships validate` |
| Crew on a ship | `docs/ship-crew.md`: shared skeleton, stations, walk routes, outfits, deck-clearance check (70 × 185 cm), crew moving with the hull |

## Decisions

**Made by you:**
- **Blender is the engine.** The editor drives Blender and never re-implements geometry.
- **Ships and humans are separate paths**, each created and edited on its own.
- **Customers review in a meeting on your laptop** (29 Oct). The editor's "Present to customer" mode shows the scene full screen and logs feedback against the version. Nothing is hosted, so v1 has no sharing links, sign-ins or customer accounts.
- **Humans: pickers plus prompts.** A starter set of pickers ships with v1. When you prompt for something new (a beard, hat or shirt), the editor asks **"Add as a picker?"** and, on yes, saves it to the catalogue for reuse.

**Made by me (say if wrong):**
- **Three paths, not two.** Alongside the ship workshop and the crew workshop, an **Assembly** screen puts crew on a ship. This is the step you said nobody can do today, so it gets its own screen.
- **Ships declare interaction points, The Sims' "smart objects".** Each ship part says where a person goes and what they do there: helm ("stand, steer"), gun mount ("gunner, rotates with the turret"), ladder ("climb"), lookout ("binoculars"). Crewing a ship is then dragging a person onto a point, and that works on every ship class.
- **Ship parts get the same promote-to-picker step.** A gun mount, davit or radar made by prompt can be saved to a ship-parts catalogue and reused on the next ship.
- **The AI is a cloud LLM call through the Claude Agent SDK.** That is the Claude Code harness as a library, so the GUI gets the same tools and agent loop. It is limited to the project folder and the Blender bridge; it cannot run arbitrary commands on your Mac. Read the `claude-api` skill before writing that code.
- **Humans come from MPFB2 (MakeHuman for Blender).** It has sliders for gender, height, weight and build, clothing that reshapes with the body, and a game-engine skeleton, inside the same Blender. MetaHuman is rejected because its licence ties output to Unreal, which rules out MAK. Quaternius, which StraitsSim used, has no body controls. **To verify first:** that MPFB2 output is CC0 and safe to ship in a commercial product.
- **One shared skeleton for every human**, so every animation works on every person.
- **The GUI is a local web app**: browser front end plus a small local server that runs the agent and talks to Blender. The 3D viewer is a three.js glTF viewer (orbit, play animations, toggle crew). It runs on your Mac, so it needs no hosting.

## The three paths

**Research lives inside the ship workshop (Lester, 29 Oct).** The ship workshop has two modes, named **Research** and **Build** (Lester renamed "Dossier" to "Research" because it is easier to understand; use "research" in all UI copy). Research comes first and full screen; Build follows, with the research as an evidence panel per part ("Challenge this", "Open in Research"). New crew items get their own research too. There is no project-level Research tab: the research belongs to one hull.

**A chat panel is on every screen (Lester, 29 Oct).** Every screen, including Research, Assembly and Review, keeps a chat with the AI.

**Pin comments on the model (Lester, 29 Oct).**
- In Build, the main way to change one part is a comment pinned on it. A tag confirms the target (e.g. "Roof › Searchlight"), with a level picker to choose the whole roof or just the lens. The AI answers in the thread, makes the change, and offers keep or undo with before and after.
- Pins attach to named Blender objects, so they follow the part through rebuilds; this needs raycast-to-object picking in the viewer.
- Hidden or underwater parts are commented on from a list.
- The old right panel becomes a closed-by-default Inspect drawer: exact values, evidence, open questions.
- The left panel has two tabs: Chat (whole-ship requests) and Comments.
- In Review, customer feedback is pinned on the model during the meeting; the pins are the task list.

**Home is a chat that routes (Lester, 29 Oct).**
- Home opens to a chat box. The AI reads what you ask and offers to open the right workshop: new vessel → Ship Research; a part change → Ship Build with that part selected; a person or what they wear → Crew; a movement → Crew animation; crew acting on a ship → Assembly; a meeting or export → Review.
- When it is unsure, it asks one question with choices rather than guessing.
- The conversation carries into the destination's chat panel.
- Routing must open the screen, not silently act: the user confirms the destination, so a misread costs one click. In the real app, routing is a classification step on the LLM call, not keyword matching (the canvas mock uses keywords). Revisit only if Lester starts researching several candidate classes before choosing one.

**The canvas sample is the real PC 303** (four outboards, searchlight, mast camera, door, wipers; crew: coxswain, navigator, two-person boarding team). It replaced the fictional bow-gun boat, which contradicted the dossier.

**0. Research dossier: the standard is Lester's PCG 3-Series dossier** (`straitssim-w1/docs/reviews/pcg-3series-20260930/`: `index.html` and `references.json`)
- Sections: summary verdict and existing-work check; photo atlas with full provenance (credit, date, hull, resolution, SHA-256, rights, modelling use) and viewpoint coverage; platform evidence table; crop close-ups (nothing generated); articulation proposal including what must not move; build phases with acceptance checks; open questions; sources and what each was allowed to prove.
- Evidence statuses replace quality scores: Official, Photographed, Photo reading, Inference, Comparison only, Secondary lead, Unverified.
- One exact baseline hull. Sister craft are comparison only; other classes are excluded as evidence.
- The dossier format is a schema the AI must fill, checked by the editor, not free prose.

Earlier notes on the research screen (still apply):
- Every source the AI found, with a type, a quality rating and the *reason* for that rating. The rating is the AI's judgement, so it is never shown as verified.
- A spec table tracing every value to its sources: agreed, in conflict, a single source, or an assumption.
- Evidence for each row: reference photos, excerpts, and which model parts it changes.
- A coverage strip showing which parts have weak evidence, since that is where the model is most likely to look wrong.
- Root-cause fixes at the source: exclude a source, pick a value, confirm an assumption, or add your own photo or drawing. Then rebuild only the affected parts.

**1. Ship workshop**
- Builds from the checked research spec. Each part links back to its evidence.
- Chat to build or edit, previewed live and checked against the hand-over contract on every change.
- Parts tree: articulated parts (turret, gun, crane jib, davit, radar, doors), each with a pivot, axis, limits and keyframed motion on a timeline.
- Interaction points placed on parts.
- Ship-parts catalogue: pick an existing part, or prompt a new one and promote it.

**2. Crew workshop (Sims-style)**

| Slot | Picker | Prompt to create new |
|---|---|---|
| Gender, height, build | Sliders | — |
| Skin tone | Swatches | — |
| Hair, facial hair | Catalogue | Yes |
| Top, bottom, footwear | Catalogue | Yes (hardest: must fit every body shape) |
| Hat / helmet | Catalogue | Yes |
| Facial accessories (glasses, ear defenders) | Catalogue | Yes |
| Equipment (binoculars, radio, rifle, life jacket) | Catalogue, attached to hand, back or chest | Yes |
| Animation (walk, run, squat, hands up, cover ears) | Catalogue | Yes (pose and keyframe authoring by prompt) |
| Saved outfits ("No. 4 working dress", "boarding party") | One-click presets | Save the current look |

**Animation editor (inside the crew workshop).**
- The catalogue is grouped Basic, Duty and Reactions. Basic moves come from a free CC0 motion library.
- Prompted moves are built as key poses on the shared skeleton, then refined in words ("faster on the way up").
- A scrub timeline lets you check each pose.
- Checks: feet planted; no hands through the body on any body size; blends in and out cleanly.
- Previews: "all body sizes" and "rolling deck".
- A trigger sets when a move plays (e.g. when the gun fires), wired up in Assembly.
- Long or travelling moves (line handling, ladder climbing) wait for the text-to-motion spike.

**Promote-to-picker rules.** A prompted item becomes a picker only after the editor checks it:
- Clothing fits the slider extremes without poking through.
- It uses the shared skeleton or a named attachment point.
- It is below the triangle budget.

Each catalogue item stores a thumbnail, the prompt that made it, its source and licence, and a version.

**Starter catalogue (kept small; prompting grows it):** 2 base bodies, 3 skin tones, 3 uniforms, 3 hats/helmets, 2 facial accessories, 3 pieces of equipment, and 6 animations (idle, walk, run, squat, hands up, binocular look).

**3. Assembly**
- Pick a ship, drag crew onto its interaction points, and draw walk routes on deck.
- A deck check confirms floor under every route and head clearance (porting StraitsSim's 70 × 185 cm logic).
- Crew on an articulated part move with it, e.g. a gunner rotates with the turret.
- Play the whole scene on the timeline, then export.

## Export package (engine-neutral)

One folder per assembled scene:
- ship `.glb` and `.json` (StraitsSim's contract, extended with articulated parts and interaction points);
- one `.glb` per human;
- `crew.json` (who stands where, routes, activities, timing).

Unreal reads it now; a MAK adapter reads the same folder later, so nothing is rebuilt.

## Out of v1

Text-to-motion AI models (prompted animation uses pose and keyframe authoring), more than one ship class end to end, MAK, multi-user review, cloth physics, crew decision-making (CGF behaviour).

## Build order

0. **Design canvas first: no code until you say "build".** Using the `ui-design-refinement` method:
   - Publish a private Design canvas with one desktop-size artboard (1440×900) per screen: Home, Ship workshop, Crew workshop (including the "Add as a picker?" dialog), Assembly, and Review/export.
   - Use the PCG patrol boat with four crew (helm, lookout, gunner, lines) as the sample throughout.
   - Use real buttons and inputs, wired so tabs, sliders and pickers respond to clicks.
   - Open questions become switchable options on the canvas: chat panel on the left or right; pickers as a grid or a list.
   - You comment on elements, and I change the canvas and answer in each comment thread. There is no app yet, so there is nothing to change there.
   - A written user journey goes beside the canvas.
   - Phase 1 starts only when you say "build".
1. **Skeleton (serial, one session).** Repo, local server, Blender bridge, Agent SDK chat that runs one Blender command and shows the `.glb` in the viewer. Fixes the package format, catalogue format and tool interface, which everything else depends on.
2. **Fan out four builders in parallel, each owning its own files:**
   - **A. Ship workshop:** builder, contract check, articulated parts and timeline, interaction points, ship-parts catalogue.
   - **B. Crew workshop:** MPFB2 bridge, slots, starter catalogue, promote-to-picker checks.
   - **C. Assembly:** placement on interaction points, routes, deck check, crew riding on articulated parts, `crew.json`.
   - **D. GUI shell:** layout, viewer, the three path screens, version history.
3. **Integrate.** One navy ship and a crew of six, end to end.
4. **Unreal importer.** Reads the package and plants ship plus crew in a new clean UE project, borrowing StraitsSim's crew runtime ideas (`UShipCrewComponent`, deterministic animation).
5. **Later.** Text-to-motion spike, MAK adapter (VR-Vantage visual models and VR-Forces entity mapping, still to research), more ship classes.

## Data rule

- Every prompt goes to a cloud LLM, so **vessel details stay public-source only**. Never put non-public customer or vessel information into prompts, research or this repository.

## Verification

- **Automated (logic that can go wrong without crashing):** ship contract check; deck check; promote-to-picker fit checks; gunner stays on the turret through a full rotation; package export and reload gives the same geometry; one skeleton across all humans.
- **Wiring (fails loudly):** Blender bridge, agent tool calls, viewer loading. Checked by running them.
- **Your review (cannot be tested):** whether ships, uniforms and motion look right in the viewer and in Unreal. **Unverified pending your review.** Before broader testing I'll give you a local URL and a short checklist, with mocked parts named.
- **First real test:** show one crewed ship to an end user or a colleague who briefs modellers today, and time the round trip against the current process.
