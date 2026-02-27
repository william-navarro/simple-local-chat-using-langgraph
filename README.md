# LangGraph Chat

Chat application with local LLMs powered by **LangGraph**, **LM Studio**, and **React**. Features real-time streaming, conversation management, thinking mode, and automatic web search via tool calling.

![React](https://img.shields.io/badge/React-19-blue?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![LangGraph](https://img.shields.io/badge/LangGraph-0.2-purple)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue?logo=typescript)
![Tailwind](https://img.shields.io/badge/Tailwind_CSS-4.0-38bdf8?logo=tailwindcss)

## Features

- **Real-time streaming** responses via Server-Sent Events (SSE)
- **LangGraph workflow** for state management with ReAct pattern
- **Thinking mode** for models that support extended thinking (`<think>` tags)
- **Web search** (automatic) — the model decides when to search using DuckDuckGo
- **Image support** — send images in the chat (for multimodal models)
- **Conversation management** — create, switch, delete, auto-title
- **History compression** — automatic summarization when context gets too long
- **Dark theme** UI

## Architecture

```
Frontend (React + Vite)          Backend (FastAPI + LangGraph)         LM Studio
┌─────────────────────┐         ┌───────────────────────────┐       ┌──────────┐
│  React 19           │  SSE    │  FastAPI                  │  API  │          │
│  Zustand Store      │◄───────►│  LangGraph StateGraph     │◄─────►│  Local   │
│  Tailwind CSS 4     │  :8000  │  ChatOpenAI (LangChain)   │ :1234 │  LLMs    │
│  Vite :5173         │         │  DuckDuckGo Search Tool   │       │          │
└─────────────────────┘         └───────────────────────────┘       └──────────┘
```

### LangGraph Workflow

```
pre_process → check_history → [compress_history] → call_model ⇄ tool_node → END
                                                        │                     ▲
                                                        └─────────────────────┘
                                                         (if no tool calls)
```

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **LM Studio** | Latest | Download at [lmstudio.ai](https://lmstudio.ai) |
| **Python** | 3.11+ | Via [Anaconda](https://www.anaconda.com/download) / [Miniconda](https://docs.anaconda.com/miniconda/) or standalone |
| **Node.js** | 18+ | Download at [nodejs.org](https://nodejs.org) |

## Quick Start

### Windows (automated)

The project includes batch scripts for automated setup:

```batch
:: First time — full setup (creates conda env, installs dependencies, starts servers)
start.bat

:: Subsequent runs — just starts the servers
run.bat
```

### All platforms (manual)

#### 1. Clone the repository

```bash
git clone https://github.com/william-navarro/simple-local-chat-using-langgraph.git
cd simple-local-chat-using-langgraph
```

#### 2. Start LM Studio

1. Open LM Studio
2. Download and load a model (e.g., `deepseek/deepseek-r1-0528-qwen3-8b`)
3. Start the local server (default: `http://localhost:1234`)
4. Make sure the server is running before proceeding

> **Tip:** For web search (tool calling), use a model that supports function/tool calling, such as Qwen 2.5, Llama 3.1+, or Mistral models. Models without tool calling support will still work normally, but the web search feature won't be available.

#### 3. Setup the backend

```bash
cd backend
```

**Option A — Using Conda (recommended):**

```bash
conda create -n langgraph-chat python=3.11 -y
conda activate langgraph-chat
pip install -r requirements.txt
```

**Option B — Using venv:**

```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Windows
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create the environment file:

```bash
# Linux / macOS
cp .env.example .env

# Windows
copy .env.example .env
```

If `.env.example` doesn't exist, create `.env` manually:

```env
LM_STUDIO_URL=http://localhost:1234/v1
LM_STUDIO_MODEL=local-model
MAX_HISTORY_TOKENS=2000
```

Start the backend:

```bash
uvicorn main:app --reload --port 8000
```

The API will be available at `http://localhost:8000` and docs at `http://localhost:8000/docs`.

#### 4. Setup the frontend

Open a **new terminal** in the project folder and run:

```bash
cd frontend
npm install
```

Create the environment file:

```bash
# Linux / macOS
cp .env.example .env

# Windows
copy .env.example .env
```

If `.env.example` doesn't exist, create `.env` manually:

```env
VITE_API_URL=http://localhost:8000
```

Start the frontend:

```bash
npm run dev
```

#### 5. Open the app

Navigate to **http://localhost:5173** in your browser.

## Project Structure

```
.
├── backend/
│   ├── main.py             # FastAPI endpoints
│   ├── graph.py            # LangGraph workflow (nodes, edges, streaming)
│   ├── tools.py            # Tool definitions (web_search with DuckDuckGo)
│   ├── schemas.py          # Pydantic request/response models
│   ├── config.py           # Settings (env vars)
│   ├── requirements.txt    # Python dependencies
│   └── .env                # Environment variables
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/       # ChatWindow, MessageList, MessageItem, InputBar
│   │   │   ├── sidebar/    # Sidebar, ConversationItem, DeleteDialog
│   │   │   └── ui/         # Reusable UI components
│   │   ├── hooks/          # useStream, useHealth
│   │   ├── store/          # Zustand state management
│   │   ├── lib/            # API client
│   │   ├── types/          # TypeScript type definitions
│   │   ├── App.tsx         # Root component
│   │   └── main.tsx        # Entry point
│   ├── package.json
│   ├── vite.config.ts
│   └── .env                # Frontend environment variables
│
├── start.bat               # Windows: full setup + start
├── run.bat                 # Windows: quick start
└── README.md
```

## Configuration

### Backend environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LM_STUDIO_URL` | `http://localhost:1234/v1` | LM Studio API base URL |
| `LM_STUDIO_MODEL` | `local-model` | Default model name |
| `MAX_HISTORY_TOKENS` | `2000` | Token threshold for history compression |

### Frontend environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | Backend API URL |

### Ports

| Service | Port |
|---------|------|
| LM Studio | `1234` |
| Backend (FastAPI) | `8000` |
| Frontend (Vite dev) | `5173` |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/lmstudio/status` | Check if LM Studio is online |
| `GET` | `/lmstudio/models` | List loaded models from LM Studio |
| `POST` | `/chat/stream` | Stream chat response (SSE) |
| `POST` | `/chat/title` | Generate conversation title |

Full API documentation available at `http://localhost:8000/docs` when the backend is running.

## Usage Tips

- **Select a model** in the top-right dropdown — only models currently loaded in LM Studio will appear
- **Thinking mode** (brain icon) — enables extended reasoning for compatible models
- **Web search** (globe icon) — enables the model to search the web when it needs up-to-date information. The model decides automatically when to search. Requires a model with tool calling support
- **Image upload** — click the image icon or paste an image from clipboard
- **Markdown** — the assistant renders responses with full markdown support including code blocks with syntax highlighting

## Tech Stack

**Frontend:**
- React 19, TypeScript, Vite
- Tailwind CSS 4
- Zustand (state management)
- react-markdown, react-syntax-highlighter, lucide-react

**Backend:**
- FastAPI, Uvicorn
- LangChain + LangGraph
- langchain-openai (ChatOpenAI)
- DuckDuckGo Search
- Pydantic

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "LM Studio offline" indicator | Make sure LM Studio is running and the local server is started on port 1234 |
| No models in dropdown | Load a model in LM Studio — only loaded/active models are listed |
| Web search not working | Use a model that supports tool calling (Qwen 2.5, Llama 3.1+, Mistral, etc.) |
| CORS errors in browser console | Make sure the backend is running on port 8000 and `VITE_API_URL` is correct |
| `pip install` fails | Make sure you're using Python 3.11+. Try upgrading pip: `pip install --upgrade pip` |
| Port already in use | Kill the process using the port or change the port in the respective config |
