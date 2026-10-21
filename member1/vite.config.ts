import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxy = {
    '/api': {
      target: process.env.ATLAS_BACKEND_URL || env.ATLAS_BACKEND_URL || 'http://127.0.0.1:8000',
      changeOrigin: true,
    },
  };
  return {
    plugins: [react()],
    build: { outDir: 'dist', emptyOutDir: true },
    server: {
      host: '127.0.0.1',
      port: 3000,
      proxy,
      fs: { strict: false }
    },
    preview: { host: '127.0.0.1', port: 3000, proxy },
  };
});
