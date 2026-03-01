# LangGraph Chat

Chat application powered by **LangGraph** with **multi-provider LLM support**. Features real-time streaming, conversation management, thinking mode, automatic web search via tool calling, and terminal access.

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
- **Multi-provider** — LM Studio, Ollama, CLI Proxy, OpenAI, Anthropic, Google
- **Terminal access** — run commands directly from the chat
- **Settings modal** — temperature, top_p, max tokens, system prompt per conversation
- **Dark theme** UI

## Architecture

```
                                                                ┌──────────────┐
                                                          :1234 │  LM Studio   │
                                                       ┌───────►│  (local)     │
Frontend (React + Vite)          Backend (FastAPI)     │        └──────────────┘
┌─────────────────────┐         ┌──────────────────┐   │        ┌──────────────┐
│  React 19           │  SSE    │  FastAPI          │   │  :8090 │  CLI Proxy   │
│  Zustand Store      │◄───────►│  LangGraph        │◄──┼───────►│  (Gemini)    │
│  Tailwind CSS 4     │  :8000  │  LangChain        │   │        └──────────────┘
│  Vite :5173         │         │  Multi-provider   │   │        ┌──────────────┐
└─────────────────────┘         └──────────────────┘   └───────►│  Ollama /    │
                                                                │  Cloud APIs  │
                                                                └──────────────┘
```

### LangGraph Workflow

```
pre_process → check_history → [compress_history] → call_model ⇄ tool_node → END
                                                        │                     ▲
                                                        └─────────────────────┘
                                                         (if no tool calls)
```

## Supported Providers

| Provider | Type | How to use |
|----------|------|------------|
| **LM Studio** | Local | Download at [lmstudio.ai](https://lmstudio.ai), load a model, start the server |
| **Ollama** | Local | Install from [ollama.com](https://ollama.com), pull a model |
| **CLI Proxy** | Local proxy | Proxies free Gemini API via Google OAuth ([download separately](https://github.com/nicobytes/cli-proxy-api/releases)) |
| **OpenAI** | Cloud | Add your API key in Settings |
| **Anthropic** | Cloud | Add your API key in Settings |
| **Google** | Cloud | Add your API key in Settings |

> You only need **one** provider to get started. LM Studio or Ollama are the easiest for local use.

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.11+ | Via [Anaconda](https://www.anaconda.com/download) / [Miniconda](https://docs.anaconda.com/miniconda/) or standalone |
| **Node.js** | 18+ | Download at [nodejs.org](https://nodejs.org) |
| **LLM Provider** | Any | At least one: LM Studio, Ollama, CLI Proxy, or a cloud API key |

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

#### 2. Setup a provider (pick one)

**Option A — LM Studio (local):**
1. Open LM Studio and load a model (e.g., `qwen3:latest`)
2. Start the local server (default: `http://localhost:1234`)

**Option B — Ollama (local):**
1. Install Ollama and run `ollama pull <model>`
2. Ollama runs automatically on `http://localhost:11434`

**Option C — CLI Proxy (free Gemini via Google OAuth):**
1. Download the binary for your platform from [cli-proxy-api releases](https://github.com/nicobytes/cli-proxy-api/releases)
2. Place the binary in the `bin/` folder (a `config.yaml` template is already there)
3. First-time login — either:
   - From terminal: `./cli-proxy-api -login` (in the `bin/` folder)
   - From the app: go to **Settings > API Keys > Login with Google**
4. Start the proxy manually or via `start.bat` / `run.bat`:
   ```bash
   cd bin
   ./cli-proxy-api -config config.yaml
   ```

**Option D — Cloud API:** Add your OpenAI, Anthropic, or Google API key in the app's Settings modal (gear icon).

> **Tip:** For web search (tool calling), use a model that supports function/tool calling, such as Qwen 2.5, Llama 3.1+, or Gemini models. Models without tool calling support will still work normally, but the web search feature won't be available.

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
OLLAMA_URL=http://localhost:11434/v1
CLI_PROXY_URL=http://localhost:8090/v1
OPENAI_API_KEY=
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
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
│   ├── providers.py        # Multi-provider LLM factory
│   ├── tools.py            # Tool definitions (web_search, terminal)
│   ├── schemas.py          # Pydantic request/response models
│   ├── config.py           # Settings (env vars)
│   ├── settings_store.py   # Runtime settings persistence
│   ├── requirements.txt    # Python dependencies
│   └── .env                # Environment variables
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/       # ChatWindow, MessageList, MessageItem, InputBar
│   │   │   ├── sidebar/    # Sidebar, ConversationItem, DeleteDialog
│   │   │   ├── settings/   # Settings modal, API keys
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
├── bin/
│   └── config.yaml         # CLI Proxy configuration (binary downloaded separately)
│
├── start.bat               # Windows: full setup + start
├── run.bat                 # Windows: quick start
└── README.md
```

## Configuration

### Backend environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LM_STUDIO_URL` | `http://localhost:1234/v1` | LM Studio API URL |
| `OLLAMA_URL` | `http://localhost:11434/v1` | Ollama API URL |
| `CLI_PROXY_URL` | `http://localhost:8090/v1` | CLI Proxy API URL |
| `OPENAI_API_KEY` | *(empty)* | OpenAI API key |
| `ANTHROPIC_API_KEY` | *(empty)* | Anthropic API key |
| `GOOGLE_API_KEY` | *(empty)* | Google AI API key |
| `MAX_HISTORY_TOKENS` | `2000` | Token threshold for history compression |

### Frontend environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_URL` | `http://localhost:8000` | Backend API URL |

### Ports

| Service | Port |
|---------|------|
| LM Studio | `1234` |
| Ollama | `11434` |
| CLI Proxy | `8090` |
| Backend (FastAPI) | `8000` |
| Frontend (Vite dev) | `5173` |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/providers` | List all providers with availability status |
| `GET` | `/providers/{id}/status` | Check if a provider is online |
| `GET` | `/providers/{id}/models` | List available models for a provider |
| `POST` | `/chat/stream` | Stream chat response (SSE) |
| `POST` | `/chat/title` | Generate conversation title |
| `POST` | `/chat/terminal/execute` | Execute a terminal command |
| `GET` | `/settings` | Get global settings |
| `PUT` | `/settings` | Update global settings |
| `GET` | `/settings/keys` | Get masked API keys |
| `PUT` | `/settings/keys` | Update API keys |
| `GET` | `/settings/urls` | Get provider URLs |
| `PUT` | `/settings/urls` | Update provider URLs |
| `POST` | `/providers/refresh-models` | Force refresh cloud model lists |
| `POST` | `/cli-proxy/login` | Trigger CLI Proxy OAuth login |

Full API documentation available at `http://localhost:8000/docs` when the backend is running.

## Usage Tips

- **Select a provider and model** in the top bar — local providers show only loaded/running models
- **Thinking mode** (brain icon) — enables extended reasoning for compatible models
- **Web search** (globe icon) — enables the model to search the web when it needs up-to-date information. The model decides automatically when to search. Requires a model with tool calling support
- **Image upload** — click the image icon or paste an image from clipboard
- **Terminal** (terminal icon) — allows the model to run commands on your machine (with approval)
- **Settings** (gear icon) — configure temperature, top_p, max tokens, system prompt, API keys, and provider URLs
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
| Provider shows "offline" | Make sure the provider is running (LM Studio on :1234, Ollama on :11434, CLI Proxy on :8090) |
| No models in dropdown | Load a model in LM Studio/Ollama — only loaded/active models are listed |
| CLI Proxy 404 on all routes | Port 8080 may be taken by Docker. The default was changed to 8090 in `bin/config.yaml` |
| CLI Proxy auth expired | Re-login via **Settings > API Keys > Login with Google**, or run `cli-proxy-api -login` in terminal |
| Web search not working | Use a model that supports tool calling (Qwen 2.5, Llama 3.1+, Mistral, etc.) |
| CORS errors in browser console | Make sure the backend is running on port 8000 and `VITE_API_URL` is correct |
| `pip install` fails | Make sure you're using Python 3.11+. Try upgrading pip: `pip install --upgrade pip` |
| Port already in use | Kill the process using the port or change the port in the respective config |
