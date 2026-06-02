import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    chunkSizeWarningLimit: 700,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('recharts')) {
            return 'charts'
          }
          if (id.includes('lucide-react')) {
            return 'icons'
          }
          if (id.includes('react-dom') || id.includes('react')) {
            return 'react'
          }
          return undefined
        },
      },
    },
  },
})
