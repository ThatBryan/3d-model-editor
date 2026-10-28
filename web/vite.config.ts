import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

// The app talks to the FastAPI server on 8787 through /api (docs/CONTRACT.md §10).
// VITE_MOCK=1 swaps that for an in-browser mock backend (src/mock), for development only.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': { target: 'http://localhost:8787', changeOrigin: true } },
  },
  build: { chunkSizeWarningLimit: 2000 },
  test: { environment: 'node', include: ['src/**/*.test.ts'] },
});
