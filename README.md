# Meeting Agent

Meeting Agent is a mobile-first AI meeting-point recommender. The current codebase contains a working Demo v0 that connects voice recording, ASR, location extraction, Amap-based meeting-point recommendation, map rendering, TTS playback, and history review.

The product direction for V1 is a chat-first Agent experience: users describe where each person is and what kind of place they want, then the assistant asks follow-up questions and recommends meeting places inside the conversation.

## Current Version

- `main`: Demo v0 baseline.
- `v0-demo`: tag for the current runnable demo.
- `feat/chat-agent-v1`: active branch for the chat-first Agent redesign.

## Features

- Mobile-first React interface.
- Browser voice recording with upload to the backend.
- Bailian ASR for speech-to-text.
- DeepSeek-based address extraction with local fallback handling.
- Amap MCP / REST geocoding and POI recommendation.
- Amap JS map rendering in the frontend.
- Bailian TTS for voice reply.
- Local history stored under `Storage/`.
- V1 PRD and mobile prototype under `docs/`.

## Project Structure

```text
.
├── backend/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py          # FastAPI app and CORS setup
│   │   ├── routes.py        # API routes and pipeline orchestration
│   │   ├── config.py        # .env parsing and runtime settings
│   │   └── services/        # Bailian, DeepSeek, and Amap clients
│   ├── tests/               # Backend unit tests
│   ├── requirements.txt
│   └── .env.example
├── frontend/                # React + Vite frontend
│   ├── src/
│   │   ├── App.jsx
│   │   ├── AmapPanel.jsx
│   │   ├── api.js
│   │   ├── mobileViewModel.js
│   │   └── styles.css
│   ├── package.json
│   └── .env.example
├── docs/                    # Integration docs, PRD, and prototypes
├── Storage/                 # Runtime audio/log/pipeline artifacts, ignored by Git
└── README.md
```

## Prerequisites

- Python 3.12 recommended.
- Node.js 20+ recommended.
- API credentials for Bailian, DeepSeek, and Amap.
- Optional: Amap MCP server URL if using the MCP path.

## Backend Setup

```bash
cd backend
python3 -m venv .venv-run312
source .venv-run312/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` and fill in the required credentials:

```text
BAILIAN_API_KEY=
DEEPSEEK_API_KEY=
AMAP_MAPS_API_KEY=
AMAP_WEB_SERVICE_KEY=
AMAP_JS_API_KEY=
AMAP_JS_SECURITY_CODE=
```

Start the backend:

```bash
cd backend
source .venv-run312/bin/activate
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8013 --reload
```

Health check:

```bash
curl http://localhost:8013/health
```

Expected response:

```json
{"status":"ok"}
```

## Frontend Setup

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

The frontend runs at:

```text
http://localhost:5177/
```

By default, the frontend calls:

```text
/api/meeting-point/recommend
```

If the frontend is not served through a proxy, set `VITE_RECOMMEND_ENDPOINT` in `frontend/.env.local` to the full backend URL.

## API Overview

Backend base URL:

```text
http://localhost:8013
```

Important endpoints:

- `GET /health`: service health check.
- `GET /api/client-config`: frontend map configuration.
- `POST /api/meeting-point/recommend`: upload audio and run the recommendation pipeline.
- `GET /api/meeting-point/history`: list saved recommendation history.
- `GET /api/meeting-point/history/{request_id}`: load one recommendation result.

## Verification

Run backend tests:

```bash
source backend/.venv-run312/bin/activate
PYTHONPATH=backend python -m unittest backend/tests/test_routes_validation.py backend/tests/test_deepseek_extractor.py
```

Run frontend view-model tests:

```bash
cd frontend
node --test src/mobileViewModel.test.js
```

Build the frontend:

```bash
cd frontend
npm run build
```

## Docs And Prototype

- V1 PRD: `docs/superpowers/specs/2026-07-01-meetpoint-v1-prd.md`
- Mobile prototype: `docs/prototypes/meetpoint-v1-mobile-prototype.html`
- Amap integration notes: `docs/高德MCP_接入说明.md`
- DeepSeek integration notes: `docs/DeepSeek_开发规范.md`

Open the prototype directly in a browser:

```text
docs/prototypes/meetpoint-v1-mobile-prototype.html
```

## Runtime Artifacts

The backend writes runtime files to `Storage/`, including:

- uploaded audio files;
- ASR results;
- DeepSeek extraction results;
- Amap MCP traces;
- TTS results;
- pipeline summaries;
- backend logs.

`Storage/` is ignored by Git and should not be committed.

## Security Notes

- Do not commit `backend/.env` or any real API keys.
- Only `.env.example` files should be tracked.
- Generated audio, logs, local virtual environments, `node_modules`, and build outputs are ignored by Git.

## Development Notes

The current runnable Demo v0 is intentionally preserved. New product work should continue on `feat/chat-agent-v1`, where the UI and backend contract can evolve toward a chat-first Agent assistant.

