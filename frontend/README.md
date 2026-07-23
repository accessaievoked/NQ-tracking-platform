# NQ Frontend (React + Vite)

The web app for the NQ Tracking Platform — Brand Library, connections, and
(soon) reports. Talks to the FastAPI backend via `/api/*`, which the Vite dev
server proxies to `http://localhost:8000` (see `vite.config.js`), so no CORS
setup is needed in development.

## Run (development)

Two terminals:

1. Backend (repo root, venv active):

   ```
   uvicorn app.main:app --reload
   ```

2. Frontend (this folder):

   ```
   npm install
   npm run dev
   ```

Then open the URL Vite prints — http://localhost:5173

Sign in with any email (dev mode logs you in directly), pick/create a brand, and
connect your data sources by pasting each provider's token.

## Build (production)

```
npm run build      # outputs static files to dist/
npm run preview    # serve the built app locally
```

For production you can serve `dist/` from FastAPI (e.g. mount it as static
files) and point the app at the same-origin `/api`.

## Structure

```
src/
  main.jsx          React entry
  App.jsx           auth gate: Login vs Dashboard
  Login.jsx         magic-link sign-in
  Sidebar.jsx       nav rail (collapsible to icons)
  Dashboard.jsx     top bar + Brand Library + integration grid
  ConnectDialog.jsx connect-a-provider modal
  api.js            fetch helper (bearer token)
  providers.js      integration definitions (fields per provider)
  index.css         design system (Figma tokens)
```
