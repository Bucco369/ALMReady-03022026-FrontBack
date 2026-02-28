# Future: Multi-User Server Mode

## When to consider this

The current ALMReady desktop app is a single-user installation.  Each analyst
installs it on their workstation and works with their own sessions and data.

Consider switching to server mode when:

- Multiple analysts in the same bank need to **share sessions** (e.g. one person
  uploads the balance sheet, another runs scenarios, a manager reviews results).
- The bank's IT policy makes per-machine installation impractical and they
  prefer running software on a central internal server.
- An external client needs **multi-tenant** access with per-user data isolation.

---

## Architecture

```
Bank internal network
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   Analysts' browsers ──► nginx (port 443)               │
│                              │                          │
│                              ├──► React SPA (static)    │
│                              │                          │
│                              └──► FastAPI backend       │
│                                        │                │
│                                        └──► Sessions FS │
│                                             (or Postgres)│
└─────────────────────────────────────────────────────────┘
```

Deployed via `docker-compose` on a single server the bank controls.  No public
internet exposure required.

---

## What needs to change in the codebase

### 1. Authentication layer (~2 days)

The backend currently has no auth.  Add JWT-based auth using `fastapi-users`
or a custom implementation:

- `POST /api/auth/login` — accepts username + password, returns a JWT
- `GET /api/auth/me` — returns current user info
- All existing `/api/sessions/*` endpoints require a valid JWT in the
  `Authorization: Bearer {token}` header

Library recommendation: `fastapi-users[sqlalchemy]>=13` with SQLite for
simplicity, or PostgreSQL for production.

### 2. User-scoped sessions (~1 day)

Add `user_id: str` to `SessionMeta` (Pydantic model + disk serialisation).

In every session endpoint that lists or creates sessions, filter by the
`user_id` extracted from the JWT.  The session directory structure becomes:

```
sessions/
  {user_id}/
    {session_uuid}/
      meta.json
      balance_positions.parquet
      ...
```

No changes to the calculation engine or balance/curves parsers.

### 3. Frontend auth (~1 day)

- Add a login page (`src/pages/Login.tsx`) with username + password form.
- Store the JWT in `localStorage` (or `sessionStorage` for stricter security).
- Add an auth context / hook that gates access to the main app.
- Add the `Authorization` header to every `http()` / `xhrUpload()` call in
  `src/lib/api.ts`.
- Redirect to `/login` on 401 responses.

### 4. CORS

Change `ALMREADY_CORS_ORIGINS` (or the hardcoded CORS list in `main.py`) to
allow the server's actual domain (e.g. `https://alm.bankname.internal`).
Remove the Tauri-specific origins from server deployments.

### 5. Data directory

`ALMREADY_DATA_DIR` will point to a Docker volume mount, e.g.
`/data/almready/sessions`.  No code changes required — just configure the
environment variable in `docker-compose.yml`.

---

## docker-compose.yml (sketch)

```yaml
version: "3.9"
services:
  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    environment:
      ALMREADY_DATA_DIR: /data/sessions
      SESSION_TTL_DAYS: "30"
    volumes:
      - sessions_data:/data/sessions
    expose:
      - "8000"

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    expose:
      - "80"

  nginx:
    image: nginx:alpine
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/nginx/certs:ro
    depends_on:
      - backend
      - frontend

volumes:
  sessions_data:
```

### Dockerfile (backend)
```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Dockerfile.frontend
```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
```

---

## Estimated effort

| Task | Days |
|------|------|
| Auth backend (JWT + user model) | 2 |
| User-scoped sessions | 1 |
| Frontend login page + JWT handling | 1 |
| Docker + nginx config | 0.5 |
| Testing + QA | 1 |
| **Total** | **~5.5 days** |

This assumes the core calculation engine and API contract are frozen.  No
changes to `engine/` or the balance/curves parsers are needed.

---

## Deployment considerations for bank IT

- The bank provides an internal hostname + TLS certificate.
- Docker Desktop or Docker Engine must be installed on the server machine.
- Sessions volume should be on a network drive if HA/backup is required.
- No outbound internet access is required — all images can be built and
  loaded offline.
- Updates: replace the container images and run `docker-compose up -d`.
