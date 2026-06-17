import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://aiops:5002',
        changeOrigin: true,
      },
      '/generator': {
        target: 'http://generator:5001',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/generator/, ''),
      }
    }
  }
})
