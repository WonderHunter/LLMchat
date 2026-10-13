import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Même origine que l'API en dev : le cookie de session passe sans CORS.
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
