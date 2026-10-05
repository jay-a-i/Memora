import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

// Port 3000 matches the backend's default CORS_ORIGINS
// (backend/app/core/config.py: CORS_ORIGINS = ["http://localhost:3000"]).
// Vite's default of 5173 is not on that list, so the dev server would be
// blocked by the preflight on every /api/v1 request.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    strictPort: true,
  },
});
