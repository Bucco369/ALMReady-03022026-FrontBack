# ALMReady

Asset-Liability Management (ALM) risk tool for banking institutions. Computes **EVE** (Economic Value of Equity) and **NII** (Net Interest Income) under base and regulatory stress scenarios.

## Architecture

| Layer | Stack | Location |
|-------|-------|----------|
| Frontend | React + TypeScript, Vite, shadcn-ui, Tailwind | `src/` |
| API | FastAPI (Python) | `backend/app/` |
| Calculation Engine | pandas, numpy | `backend/engine/` |

## Prerequisites

- **Node.js** >= 18 (for the frontend)
- **Python** >= 3.10 (for the backend)
- pip (or your preferred Python package manager)

## Quick Start

```sh
# 1. Frontend
npm install
npm run dev          # → http://localhost:8080

# 2. Backend (in a separate terminal)
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload   # → http://localhost:8000
```

## Workflow

1. Start both frontend and backend.
2. Create or restore a session (the frontend does this automatically).
3. Upload a balance file (Excel `.xlsx` or CSV `.zip`).
4. Upload a forward curves Excel file.
5. Run the calculation — the engine computes EVE and NII under base + regulatory scenarios.
6. View results: summary metrics, scenario deltas, time-bucket breakdowns, and monthly NII profiles.

## Local Backend Curves Flow (Session-Scoped)

1. Start backend on `http://localhost:8000`.
2. Start frontend with `npm run dev`.
3. Create/restore session (frontend does this automatically).
4. Upload curves Excel (`.xlsx`) from the Curves card or call:

```sh
curl -X POST \
  -F "file=@/path/to/Curve tenors_input.xlsx" \
  http://localhost:8000/api/sessions/<session_id>/curves
```

5. Check curves summary:

```sh
curl http://localhost:8000/api/sessions/<session_id>/curves/summary
```

6. Fetch points for one curve:

```sh
curl http://localhost:8000/api/sessions/<session_id>/curves/EUR_ESTR_OIS
```
