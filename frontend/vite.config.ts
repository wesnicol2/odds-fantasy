import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

const backend = 'http://127.0.0.1:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    proxy: {
      '/best-lineup': backend,
      '/defenses': backend,
      '/health': backend,
      '/league': backend,
      '/player': backend,
      '/projections': backend,
      '/quota': backend,
      '/user': backend,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: true,
  },
});
