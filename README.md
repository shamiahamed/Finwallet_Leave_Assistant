# Employee Leave Management Q&A Assistant

> Live deployment: [finwallet-frontend.onrender.com](https://finwallet-frontend.onrender.com/)

## About the Project

This project helps users get employee details, leave balances, leave requests, and leave policy information by asking questions in simple English.

It uses React for the frontend, FastAPI for the backend, Groq API to understand questions, and an Excel file to retrieve employee and leave data.

## Features

- Search employee details by ID or name.
- Check employee leave balances.
- Find leave requests by status, type, and date.
- Get leave policy information.
- View department employee counts and leave summaries.
- Display answers through a chat interface.
- Stream answers word by word (SSE) with a blinking cursor.
- Multi-chat sidebar with browser-persisted history.
- Follow-up questions that resolve pronouns ("his", "her") from conversation context.
- Deterministic follow-up suggestion chips based on the verified answer.
- Request correlation IDs in logs and an `X-Request-ID` response header.
- Dependency-aware health check at `GET /api/v1/health`.
- Security monitoring panel with findings, scan history, and events.

## Architecture

### Backend (`backend/`)

Python FastAPI application with the following structure:

- `app/api/v1/endpoints/chat.py` — Main chat endpoint with intent routing, RAG retrieval, and LLM streaming.
- `app/api/v1/endpoints/chat_helpers.py` — Shared regex patterns and helper functions for intent detection.
- `app/api/v1/endpoints/intent_router.py` — Re-export module for backward compatibility.
- `app/services/rag_service.py` — Orchestrates retrieval and answer generation.
- `app/services/rag_extractive.py` — Extractive answer helpers for summary and comparison intents.
- `app/services/rag_comparison.py` — Comparison-specific retrieval and topic detection.
- `app/utils/scope_resolver.py` — Resolves employee scope from conversation context and dataset.
- `app/llm/formatters/` — Response formatter package (re-exports from `response_formatter.py`).

### Frontend (`frontend/`)

React.js + Vite application with the following component structure:

- `components/Avatar.jsx` — Bot and user avatar components.
- `components/ChatInput.jsx` — Message input with attachment support.
- `components/ChatWindow.jsx` — Message list container with scroll behavior.
- `components/MessageItem.jsx` — Individual message row with copy, details, and retry actions.
- `components/WelcomeScreen.jsx` — Empty-state welcome screen with prompt cards.
- `components/Sidebar.jsx` — Conversation history sidebar.
- `components/SecurityPanel.jsx` — Thin container for the security dashboard.
- `components/SecurityDashboard.jsx` — Security dashboard content (overview, findings, history, events).
- `components/SecuritySummary.jsx` — Summary cards and severity badges.
- `components/SecurityFindings.jsx` — Findings list, scan history, and recent events.
- `components/DatasetPanel.jsx` — Dataset selection dropdown.
- `hooks/useChat.js` — Chat state management hook (conversations, streaming, retry).

## Technologies Used

- Frontend: React.js, Vite, JavaScript, CSS
- Backend: Python, FastAPI, Pydantic
- LLM API: Groq
- Dataset: Microsoft Excel
- API Testing: Swagger UI

## How to Run the Project

### Backend

Open a terminal and navigate to the backend folder.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create a `.env` file using `.env.example` and add your Groq API key.

Start the backend:

```powershell
uvicorn app.main:app --reload --port 8000
```

### Frontend

Open another terminal:

```powershell
cd frontend
npm install
npm run dev
```

## Access the Application

- Frontend: http://localhost:5173
- Swagger API Documentation: http://127.0.0.1:8000/docs

## Data Source

The application uses the provided Excel dataset containing employee details, leave requests, leave balances, and leave policies.

## Docker Deployment

The project includes Docker Compose configuration for containerized deployment:

```powershell
docker compose up --build
```

This starts:
- **Backend** (`http://localhost:8000`) — FastAPI with health check at `/api/v1/health`
- **Frontend** (`http://localhost:8080`) — React.js production build

The `docker-compose.yml` defines both services with proper health checks, environment variables, and volume mounts for the data directory.

### Render Deployment

The live deployment at `https://finwallet-frontend.onrender.com/` is configured via `render.yaml`, which builds the frontend from the Dockerfile and serves it on port 8080.

## Verification

```powershell
# Backend
cd backend && python -c "from app.main import create_app"

# Frontend
cd frontend && npm run build

# Regression tests (all intent types and query prompts)
cd backend && $env:PYTHONPATH = "."; pytest tests/test_regression_intents.py -v
```