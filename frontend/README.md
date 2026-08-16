# FarmOps operator frontend

Responsive React operator console for FarmOps AI. The application talks only to
the FastAPI surface described in `plans/reports/plan.md`; it never connects to
Supabase or MQTT directly.

## Local development

```bash
npm install
npm run dev
```

Vite proxies the FarmOps API routes to `http://127.0.0.1:8000` in development.
Set `VITE_API_BASE_URL` when the API is hosted elsewhere. The operator token is
entered in the app and kept in `sessionStorage`, so it is not bundled or
committed.

## Quality checks

```bash
npm run lint
npm test
npm run build
npm run test:e2e
```

The Playwright suite runs against deterministic API fixtures at the network
boundary and verifies the critical flows at a 390px mobile viewport.
