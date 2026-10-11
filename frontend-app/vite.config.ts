import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    // In Docker on WSL/Windows, file change events from the host don't reach the container, so
    // poll instead. docker-compose.yml sets CHOKIDAR_USEPOLLING; `npm run dev` on the host doesn't.
    watch: { usePolling: Boolean(process.env.CHOKIDAR_USEPOLLING) },
  },
})
