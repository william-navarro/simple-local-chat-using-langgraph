# Project Overview
**LangGraph Chat** is a high-performance, full-stack chat application that integrates local LLMs (via LM Studio) and cloud-based providers (OpenAI, Anthropic, Google). It utilizes **LangGraph** for robust conversation state management and **FastAPI** for a real-time streaming backend (SSE). The frontend is built with **React 19**, **Vite**, and **Tailwind CSS 4**.

## Core Technologies
- **Backend:** Python 3.11+, FastAPI, LangGraph, LangChain, Pydantic, DuckDuckGo Search.
- **Frontend:** TypeScript, React 19, Vite, Tailwind CSS 4, Zustand (State Management), Lucide React.
- **LLM Integration:** Support for LM Studio (Local), OpenAI, Anthropic, and Google Gemini.

## Architecture & Workflow
The application follows a **Research -> Strategy -> Execution** lifecycle for its internal tool-calling logic:
1. **Pre-processing:** Identifies message types (summary request, system instruction, etc.).
2. **History Management:** Automatically compresses or truncates conversation history when token limits are reached.
3. **ReAct Loop (LangGraph):**
   - **call_model:** Invokes the LLM with optional tool binding.
   - **tool_node:** Executes tools like `web_search` or prepares `terminal_execute` for user approval.
4. **Streaming (SSE):** Delivers tokens, thinking states, and tool results in real-time to the frontend.

---

# Development & Operations

## Building and Running

### Prerequisites
- **LM Studio:** Running on `http://localhost:1234`.
- **Python:** 3.11+ (Conda/venv recommended).
- **Node.js:** 18+.

### Setup & Run (Windows Automated)
- **First time:** Run `start.bat` to create environments, install dependencies, and start servers.
- **Subsequent runs:** Run `run.bat` to start the backend and frontend.

### Manual Setup

#### Backend
```bash
cd backend
# Create and activate environment (venv or conda)
pip install -r requirements.txt
cp .env.example .env  # Configure your API keys
uvicorn main:app --reload --port 8000
```

#### Frontend
```bash
cd frontend
npm install
cp .env.example .env  # Ensure VITE_API_URL=http://localhost:8000
npm run dev
```

## Configuration
- **Backend (.env):** `LM_STUDIO_URL`, `LM_STUDIO_MODEL`, `MAX_HISTORY_TOKENS`, `OPENAI_API_KEY`, etc.
- **Frontend (.env):** `VITE_API_URL`.

---

# Project Structure

- `backend/`:
    - `main.py`: FastAPI entry point and endpoint definitions.
    - `graph.py`: LangGraph workflow definition (nodes, edges, routing).
    - `tools.py`: Tool definitions (web search, terminal execution).
    - `providers.py`: LLM provider abstractions.
    - `schemas.py`: Pydantic models for API communication.
    - `settings_store.py`: Persistent configuration management.
- `frontend/`:
    - `src/App.tsx`: Main application entry and layout.
    - `src/components/chat/`: Chat UI components (Window, List, Input, Terminal Dialog).
    - `src/store/useChatStore.ts`: Centralized Zustand state for conversations and settings.
    - `src/hooks/useStream.ts`: Core logic for handling SSE from the backend.
    - `src/lib/api.ts`: API client for backend communication.

---

# Development Conventions

- **State Management:** Use Zustand for global frontend state.
- **Styling:** Follow Tailwind CSS 4 patterns; prefer utility classes.
- **API Communication:** All chat interactions must use the `/chat/stream` endpoint with SSE.
- **Tool Safety:** `terminal_execute` requires explicit user confirmation via the frontend `TerminalConfirmDialog`.
- **Type Safety:** Maintain strict TypeScript definitions in `frontend/src/types/index.ts`.
- **Backend Consistency:** Use Pydantic models for all request/response bodies to ensure validation.
