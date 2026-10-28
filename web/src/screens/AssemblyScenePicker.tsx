// Shared by Assembly and Review: with no scene in the URL, open the last (or first) scene,
// or offer to create one from a ship project.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, errorText } from '../api';
import { ErrorNote, Loading, TopBar } from '../components/common';
import { recall, useProjects } from '../hooks';

export function ScenePicker({ to, title }: { to: (sceneId: string) => string; title: string }) {
  const nav = useNavigate();
  const projects = useProjects();
  const [state, setState] = useState<'loading' | 'none' | 'error'>('loading');
  const [err, setErr] = useState<string | null>(null);
  const [ship, setShip] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let alive = true;
    api.scenes().then((ss) => {
      if (!alive) return;
      if (ss.length) {
        const last = recall('scene');
        const pick = ss.find((s) => s.id === last) ?? ss[0];
        nav(to(pick.id), { replace: true });
      } else setState('none');
    }, (e) => { if (alive) { setErr(errorText(e)); setState('error'); } });
    return () => { alive = false; };
  }, [nav, to]);

  const ships = (projects.data ?? []).filter((p) => p.kind === 'ship');
  const create = async () => {
    const p = ships.find((s) => s.id === ship);
    if (!p) return;
    setBusy(true); setErr(null);
    try {
      const full = await api.project(p.id);
      const r = await api.createScene({
        schema: 'me3d.scene_spec/1', name: name.trim() || `${p.name} with crew`,
        ship: { project: p.id, version: full.version }, crew: [],
      });
      nav(to(r.scene.id));
    } catch (e) {
      setErr(errorText(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <TopBar />
      <main className="scroll" style={{ flex: 1, padding: '40px 24px', display: 'flex', justifyContent: 'center', position: 'relative' }}>
        {state === 'loading' && <Loading what="scenes" />}
        {state !== 'loading' && (
          <div style={{ width: '100%', maxWidth: 560, display: 'flex', flexDirection: 'column', gap: 14 }}>
            <h1 className="title">{title}</h1>
            <p className="muted" style={{ margin: 0 }}>There is no scene yet. A scene is one ship with crew placed on it. Pick the ship to start.</p>
            <ErrorNote error={err} />
            <ErrorNote error={projects.error} retry={projects.reload} />
            {!projects.loading && !ships.length && <span className="faint">No ships yet. Build one in the Ship workshop first.</span>}
            {ships.length > 0 && (
              <>
                <label className="faint" htmlFor="scene-ship">Ship</label>
                <select id="scene-ship" className="field" value={ship} onChange={(e) => setShip(e.target.value)}>
                  <option value="">Choose a ship…</option>
                  {ships.map((s) => <option key={s.id} value={s.id}>{s.name}{s.version ? ` · v${s.version}` : ''}</option>)}
                </select>
                <label className="faint" htmlFor="scene-name">Name (optional)</label>
                <input id="scene-name" className="field" value={name} onChange={(e) => setName(e.target.value)} placeholder="PC 303 coming alongside" />
                <button className="btn primary lg" style={{ alignSelf: 'flex-start' }} disabled={!ship || busy} onClick={() => void create()}>
                  {busy ? 'Creating…' : 'New scene'}
                </button>
              </>
            )}
          </div>
        )}
      </main>
    </>
  );
}
