import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// The API runs as a separate process in development; proxying keeps the
// frontend on a single origin so uploads and range requests behave the same
// way they will in production.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: process.env.VITE_API_TARGET ?? 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
    // Network and FUSE filesystems — an Unraid user share reached over SMB,
    // say — do not deliver inotify events reliably, so hot reload silently
    // stops working there. Polling is slower but actually notices saves.
    watch: {
      usePolling: process.env.VITE_USE_POLLING === 'true',
      interval: 400,
    },
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
  },
})
