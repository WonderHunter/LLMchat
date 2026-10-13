import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const apiPort = process.env.API_PORT ?? '8642'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: Number(process.env.PORT ?? 5180),
    strictPort: true,
    // Même origine que l'API en dev : le cookie de session passe sans CORS.
    proxy: {
      '/api': `http://127.0.0.1:${apiPort}`,
    },
  },
})
