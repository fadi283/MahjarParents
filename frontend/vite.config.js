import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

const apiProxyTarget =
  process.env.VITE_DEV_API_PROXY_TARGET || 'http://127.0.0.1:5000';

function isLoopbackProxyTarget(targetUrl) {
  try {
    const { hostname } = new URL(targetUrl);
    return (
      hostname === 'localhost' ||
      hostname === '127.0.0.1' ||
      hostname === '::1' ||
      hostname === '[::1]'
    );
  } catch {
    return false;
  }
}

const useChangeOrigin = !isLoopbackProxyTarget(apiProxyTarget);

export default defineConfig({
  plugins: [react()],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: apiProxyTarget,
        changeOrigin: useChangeOrigin,
        configure: useChangeOrigin
          ? (proxy) => {
              const targetOrigin = new URL(apiProxyTarget).origin;
              proxy.on('proxyReq', (proxyReq, req) => {
                if (req.headers.origin) {
                  proxyReq.setHeader('origin', targetOrigin);
                }
              });
            }
          : undefined,
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
