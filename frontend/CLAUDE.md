# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this directory.

## Purpose

This directory contains the **React frontend** for AI_CBC: a single-page application for managing studies, personas, questionnaires, response simulation, and analysis dashboards.

## Tech Stack

- React 18 + TypeScript
- Vite (build + dev server + Vitest)
- Ant Design 5 (Chinese locale)
- React Router 6
- Zustand (global state)
- ECharts via `echarts-for-react`
- Axios

## Entry Points

- `src/main.tsx` — React root render with Ant Design `ConfigProvider`.
- `src/router.tsx` — browser routes; all pages are lazy-loaded.
- `src/services/api.ts` — Axios client for backend API.
- `src/stores/appStore.ts` — Zustand global store.

## Common Commands

```bash
npm install
npm run dev         # http://localhost:3000, proxies /api to localhost:8000
npm run build       # type-check + production build
npm run preview
npm run lint        # ESLint
npm run test        # Vitest once
npm run test:watch
npm run test:coverage    # runs vitest with 60% coverage thresholds
```

## Project Conventions

- Path alias `@/` resolves to `src/` (configured in `tsconfig.json` and `vite.config.ts`).
- Components/pages use PascalCase; utilities use camelCase.
- Test files: `*.test.tsx` or `*.test.ts` alongside source or under `src/__tests__/`.
- All pages are lazy-loaded with `React.lazy` and wrapped in `Suspense`.
- UI text is in Chinese.

## API Communication

- Base URL `/api/v1` is proxied by Vite dev server to `http://localhost:8000`.
- `src/services/api.ts` sends `Authorization: Bearer <token>` from `localStorage`.
- `src/services/auth.ts` handles login/logout and token persistence.
- `src/pages/Login.tsx` is the unauthenticated entry point.
- `rootApi` instance handles root-level endpoints (`/health`, `/ready`, `/cost-status`, `/metrics`, `/dashboard/summary`).
- Response interceptor maps HTTP status codes to Ant Design `message.error` notifications.

## Testing

- Vitest with `jsdom` environment.
- `src/test/setup.ts` mocks `window.matchMedia` and `echarts-for-react`.
- Coverage thresholds are 60% (statements/branches/functions/lines), configured in `vite.config.ts`.

## Cross-References

- `../src/CLAUDE.md` — backend architecture and API details.
- `../docs/数据字典.md` — API payload schemas.
- `../tests/CLAUDE.md` — test suite overview (mostly backend; frontend tests live here).
- `../CLAUDE.md` — global repository guidance and team roles.
