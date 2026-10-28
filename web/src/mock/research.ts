// Mock-mode research fixture, in the CONTRACT §12 shape, with content from the approved canvas (PCG 3-Series PC 303 sample).
// Development only. The real research comes from the server's AI research job.
import type { Research } from '../types';

export const mockResearch: Research = {
  schema: 'me3d.research/1',
  subject: 'PCG 3-Series PC Class, PC 303 as photographed in 2025',
  summary: {
    verdict: 'Coverage is strong above the waterline. Engineering dimensions remain open.',
    existing_work: 'Searched the project library for PCG, PC Class, 3-Series and patrol craft. No existing PC 3-Series model or report.',
  },
  sources: [
    { id: 'S01', title: 'SPF: 3-Series commissioning release', status: 'Official', what_it_proves: 'Class identity, role, outboard propulsion, seats' },
    { id: 'S03', title: 'MINDEF PIONEER article (P01)', status: 'Photographed', what_it_proves: 'Baseline exterior photo of PC 303' },
    { id: 'S05', title: 'Unsplash photo of PC 310 (P04)', status: 'Photo reading', what_it_proves: '"350" cowl reading; door' },
    { id: 'S06', title: 'Launch news coverage', status: 'Secondary lead', what_it_proves: '11.3 t mass, load state unknown' },
    { id: 'S12', title: 'Mercury trim and tilt guidance', status: 'Comparison only', what_it_proves: 'How outboard trim works in general' },
  ],
  claims: [
    { claim: 'Class identity: PC 3-Series patrol craft, commissioned 30 Jun 2022', sources: ['S01'], status: 'Official', consequence_for_model: 'Keep the PC 3xx family separate from PT and PJ vessels.' },
    { claim: 'Low enclosed cabin, pointed foredeck, heavy fender, aft cockpit', sources: ['P01', 'P08'], status: 'Photographed', consequence_for_model: 'Hard-chine V planing form is an inference; underbody unverified.' },
    { claim: 'Four outboards', sources: ['S01', 'P02', 'P04'], status: 'Official + photo', consequence_for_model: 'Model four separate motor assemblies; no waterjets.' },
    { claim: 'Engine rating 350 hp', sources: ['S05'], status: 'Photo reading', consequence_for_model: 'Mercury 350 hp is a candidate only.' },
    { claim: 'Steering by yawing the outboards', sources: ['P19'], status: 'Inference', consequence_for_model: 'Four steering pivots, one helm command. Max angle unknown.' },
    { claim: 'Length, beam, draught', sources: [], status: 'Unverified', consequence_for_model: 'Keep dimensions as labelled provisional parameters.' },
  ],
  open_questions: [
    { question: 'Length overall, beam and draught for the PC 3-Series', meanwhile: 'photo-estimated, labelled provisional' },
    { question: 'Maximum outboard steering angle and linkage', meanwhile: 'illustrative ±30°, not a specification' },
    { question: 'PC 303 cabin door hinge side and sweep', meanwhile: 'door modelled closed' },
  ],
  articulation: [
    { part: 'Transom__Outboard_1', motion: 'steer, tilt, prop spin', priority: 'P0' },
    { part: 'Roof__Searchlight', motion: 'pan, tilt, light on/off', priority: 'P1' },
    { part: 'Cabin__Door', motion: 'hinged opening', priority: 'P1' },
    { part: 'Roof__Radome', motion: 'none: rotation is internal', priority: 'Fixed' },
  ],
  // Canvas-only section (not in CONTRACT §12), kept so mock mode shows how it would render.
  photos: [
    { id: 'P01', title: 'PC 303: bow, cabin and roof fittings', vessel: 'PC 303', views: ['port', 'bow', 'details'], credit: 'PIONEER / MINDEF', date: 'Published 19 Jul 2025; capture date not stated', width: 1920, height: 1280, observation: 'Primary exterior baseline: foredeck hatches, wipers, roof searchlight, horn, radome lettering, mast camera.', parts: 'Cabin, roof fittings, foredeck', rights: 'Owner keeps copyright. Reference only, never a texture.', accessed: '2026-09-30' },
    { id: 'P02', title: 'PC 303: port side and four outboards', vessel: 'PC 303', views: ['port', 'stern', 'details'], credit: 'Naveen Raj / Singapore Police Force', date: 'NDP 2025; article Aug 2025', width: 3286, height: 2629, observation: 'Four separate Mercury cowls; aft cockpit, cabin access, side markings.', parts: 'Outboards, transom, markings' },
    { id: 'P03', title: 'PC 303: starboard side at dusk', vessel: 'PC 303', views: ['starboard', 'bow', 'details'], credit: 'BP Chua / Flickr', date: 'Taken 12 Jul 2025', width: 1024, height: 683, observation: 'Starboard profile; green sidelight position.', parts: 'Hull profile, nav lights' },
    { id: 'P04', title: 'PC 310: elevated port / stern view', vessel: 'PC 310', views: ['port', 'stern', 'top', 'details'], credit: 'Jeyakumaran Mayooresan / Unsplash', date: 'Published 12 Aug 2025', width: 4000, height: 2667, observation: 'Cowls read "350"; open cabin door. Sister craft: comparison only for PC 303.', parts: 'Outboards, cabin door' },
    { id: 'P05', title: 'PC 310: elevated roof and foredeck', vessel: 'PC 310', views: ['starboard', 'bow', 'top', 'details'], credit: 'Eric Chang / MAphotoSG', date: 'NDP 2024', width: 1800, height: 1240, observation: 'Best roof layout available; oblique, not a true top view.', parts: 'Roof equipment layout' },
    { id: 'P06', title: 'Direct bow view', vessel: 'PC 3xx', views: ['bow'], credit: 'Toh Rui Hao / MHA', date: 'Published 8 Aug 2025', width: 1200, height: 778, observation: 'Bow-on silhouette and beam proportion.', parts: 'Bow flare, beam ratio' },
    { id: 'P07', title: 'Stern view underway', vessel: 'PC 3xx', views: ['stern'], credit: 'Jasper Lim / AsiaOne', date: 'Published 6 Aug 2025', width: 2400, height: 1257, observation: 'Transom and engine spacing from astern.', parts: 'Transom, outboard spacing' },
    { id: 'P19', title: 'Helm interior and seat', vessel: 'PC 3xx', views: ['interior', 'details'], credit: 'Toh Rui Hao / MHA', date: 'Published 8 Aug 2025', width: 1200, height: 800, observation: 'Wheel, lever assembly, displays, suspended seat. Does not prove the four-engine control mapping.', parts: 'Helm, seats' },
    { id: 'P21', title: 'PC 303: alongside, starboard cabin', vessel: 'PC 303', views: ['starboard', 'details'], credit: 'Toh Rui Hao / MHA', date: 'Published 8 Aug 2025', width: 1200, height: 800, observation: 'Starboard cabin openings at close range.', parts: 'Cabin windows, door' },
  ],
};
