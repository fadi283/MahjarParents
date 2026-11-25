import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiProxyTarget =
  process.env.VITE_DEV_API_PROXY_TARGET || 'http://127.0.0.1:5000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    sourcemap: false,
    assetsInlineLimit: 4096,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
        },
      },
    },
  },
});
