import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './theme.css';

async function start() {
  // Mock mode is for development only; the default build talks to the real /api.
  if (import.meta.env.VITE_MOCK === '1') (await import('./mock/install')).install();
  const { App } = await import('./App');
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
void start();
