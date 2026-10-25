# Employee Leave Management Q&A Assistant

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