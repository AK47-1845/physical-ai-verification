import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react()],
  server: {
    host: '127.0.0.1', port: 5180, strictPort: true,
    proxy: {
      '/api': { target: 'http://127.0.0.1:8180', changeOrigin: false },
      '/healthz': { target: 'http://127.0.0.1:8180', changeOrigin: false },
    },
    watch: { ignored: ['**/test-results/**', '**/playwright-report/**', '**/dist/**'] },
  },
  build: { chunkSizeWarningLimit: 700 },
})
