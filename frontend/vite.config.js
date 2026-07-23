import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the FastAPI backend, so the React app and the
// API share an origin in the browser (no CORS setup needed). Start the backend
// with `uvicorn app.main:app --reload` on :8000, then `npm run dev` here.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://localhost:8000',
    },
  },
})
