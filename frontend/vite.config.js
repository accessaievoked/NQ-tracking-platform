import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// The dev server proxies /api to the FastAPI backend, so the React app and the
// API share an origin in the browser (no CORS setup needed).
//
// By default it proxies to the deployed backend, so `npm run dev` works with no
// local setup. To test against a local API instead, put this in frontend/.env.local
// (git-ignored) and restart the dev server:
//
//     VITE_API_TARGET=http://localhost:8000
//
// then run `uvicorn app.main:app --reload` from the repo root.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = env.VITE_API_TARGET || 'https://nq-tracking-platform.fly.dev'
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        '/api': { target, changeOrigin: true },
      },
    },
  }
})
