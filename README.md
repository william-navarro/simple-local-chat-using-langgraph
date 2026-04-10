# LangGraph Chat

Chat application powered by **LangGraph** with **multi-provider LLM support**. Features real-time streaming, persistent conversation storage, thinking mode, automatic web search, terminal access, and file management tools.

![React](https://img.shields.io/badge/React-19-blue?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green?logo=fastapi)
![LangGraph](https://img.shields.io/badge/LangGraph-1.0-purple)
![TypeScript](https://img.shields.io/badge/TypeScript-5.7-blue?logo=typescript)
![Tailwind](https://img.shields.io/badge/Tailwind_CSS-4.0-38bdf8?logo=tailwindcss)

## Features

- **Real-time streaming** responses via Server-Sent Events (SSE)
- **LangGraph workflow** — multi-round tool calling with state management
- **Thinking mode** for models that support extended thinking (`<think>` tags)
- **Web search** — the model decides when to search using DuckDuckGo
- **File tools** — read, write, and find files without running shell commands
- **Terminal access** — run read-only shell commands with per-command user approval
- **Image support** — send images in the chat (for multimodal models) and display local images via tool
- **Persistent conversations** — stored in SQLite on the backend, not localStorage
- **History compression** — automatic summarization when context gets too long
- **Multi-provider** — LM Studio, Ollama, CLI Proxy, OpenAI, Anthropic, Google
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
│  Vite :5173         │         │  SQLite (aiosqlite│   │        ┌──────────────┐
└─────────────────────┘         └──────────────────┘   └───────►│  Ollama /    │
                                                                 │  Cloud APIs  │
                                                                 └──────────────┘
```

### LangGraph Workflow

```
pre_process → check_history → [compress_history] → call_model ⇄ tool_node → final_response → END
                                                        │                                      ▲
                                                        └──────────────────────────────────────┘
                                                              (no tool calls on first round)
```

The graph supports **multi-round tool calling**: `call_model` and `tool_node` loop until the model stops requesting tools or the iteration limit is reached, then `final_response` generates a clean text reply.

## Tool Registry

Tools are enabled per-request based on the active mode (web search / terminal access). Each tool has a risk classification and a consistent `Tool` suffix in its name.

| Tool | Risk | Requires approval | Description |
|------|------|:-----------------:|-------------|
| `WebSearchTool` | low | No | Search the web via DuckDuckGo |
| `ReadFileTool` | low | No | Read a local text file with line numbers |
| `GlobTool` | low | No | Find files by glob pattern (e.g. `**/*.py`) |
| `SendImageTool` | low | No | Display a local image in the chat |
| `TerminalTool` | high | **Yes** | Run read-only shell commands (CMD / PowerShell) |
| `WriteFileTool` | high | **Yes** | Create or overwrite a text file |

Tools marked **high risk** pause execution and show a confirmation dialog with the command explanation before running. All tool executions are logged to the `tool_executions` audit table in SQLite.

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

> **Tip:** For tool calling (web search, terminal, file tools), use a model that supports function/tool calling, such as Qwen 2.5, Llama 3.1+, or Gemini models. Models without tool calling support will still work normally for plain chat.

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

On first start, the backend automatically creates the SQLite databases at `backend/data/`:
- `conversations.db` — conversation history and tool execution audit log
- `checkpoints.db` — LangGraph interrupt state (for terminal approval resume)

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
│   ├── main.py                 # FastAPI endpoints (chat, conversations, settings)
│   ├── graph.py                # LangGraph workflow (nodes, edges, streaming)
│   ├── tools.py                # Tool registry (6 tools with risk classification)
│   ├── conversation_store.py   # SQLite persistence (conversations, messages, audit log)
│   ├── providers.py            # Multi-provider LLM factory
│   ├── schemas.py              # Pydantic request/response models
│   ├── config.py               # Settings (env vars)
│   ├── settings_store.py       # Runtime settings persistence
│   ├── requirements.txt        # Python dependencies
│   ├── data/                   # SQLite databases (git-ignored)
│   │   ├── conversations.db    # Conversation history + tool audit log
│   │   └── checkpoints.db      # LangGraph interrupt checkpoints
│   └── .env                    # Environment variables
│
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── chat/           # ChatWindow, MessageList, MessageItem, InputBar, TerminalConfirmDialog
│   │   │   ├── sidebar/        # Sidebar, ConversationItem, DeleteDialog
│   │   │   ├── settings/       # Settings modal, API keys
│   │   │   └── ui/             # Reusable UI components
│   │   ├── hooks/              # useStream, useHealth, useSettings
│   │   ├── store/              # Zustand state (UI state only — conversations in backend)
│   │   ├── lib/                # API client (chat, conversations, settings)
│   │   ├── types/              # TypeScript type definitions
│   │   ├── App.tsx             # Root component
│   │   └── main.tsx            # Entry point
│   ├── package.json
│   ├── vite.config.ts
│   └── .env                    # Frontend environment variables
│
├── bin/
│   └── config.yaml             # CLI Proxy configuration (binary downloaded separately)
│
├── start.bat                   # Windows: full setup + start
├── run.bat                     # Windows: quick start
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

### Conversations

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/conversations` | List all conversations (metadata only) |
| `POST` | `/conversations` | Create a new conversation |
| `GET` | `/conversations/{id}` | Get a conversation with all messages |
| `DELETE` | `/conversations/{id}` | Delete a conversation and its messages |
| `PUT` | `/conversations/{id}/title` | Update a conversation title |

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/chat/stream` | Stream chat response (SSE) — loads history from DB |
| `POST` | `/chat/resume` | Resume after terminal command approval |
| `POST` | `/chat/title` | Generate a conversation title |
| `POST` | `/chat/terminal/execute` | Execute an approved terminal command |

### Providers & Settings

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/providers` | List all providers with availability status |
| `GET` | `/providers/{id}/status` | Check if a provider is online |
| `GET` | `/providers/{id}/models` | List available models for a provider |
| `POST` | `/providers/refresh-models` | Force refresh cloud model lists |
| `GET` | `/settings` | Get global settings |
| `PUT` | `/settings` | Update global settings |
| `GET` | `/settings/keys` | Get masked API keys |
| `PUT` | `/settings/keys` | Update API keys |
| `GET` | `/settings/urls` | Get provider URLs |
| `PUT` | `/settings/urls` | Update provider URLs |
| `POST` | `/cli-proxy/login` | Trigger CLI Proxy OAuth login |

Full API documentation available at `http://localhost:8000/docs` when the backend is running.

## Usage Tips

- **Select a provider and model** in the sidebar — local providers show only loaded/running models
- **Thinking mode** (brain icon) — enables extended reasoning for compatible models
- **Web search** (globe icon) — the model searches automatically when it needs up-to-date information. Requires a model with tool calling support
- **Terminal** (terminal icon) — enables `TerminalTool`, `ReadFileTool`, `WriteFileTool`, and `GlobTool`. Each high-risk action (terminal commands, file writes) shows a confirmation dialog with an explanation before executing
- **Image upload** — click the image icon or paste an image from clipboard
- **Settings** (gear icon) — configure temperature, top_p, max tokens, system prompt, API keys, and provider URLs
- **Markdown** — the assistant renders responses with full markdown support including code blocks with syntax highlighting

## Tech Stack

**Frontend:**
- React 19, TypeScript, Vite
- Tailwind CSS 4
- Zustand (UI state — conversations fetched from backend API)
- react-markdown, react-syntax-highlighter, lucide-react

**Backend:**
- FastAPI, Uvicorn
- LangChain + LangGraph 1.0
- aiosqlite (async SQLite for conversations and audit log)
- DuckDuckGo Search
- Pydantic

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Provider shows "offline" | Make sure the provider is running (LM Studio on :1234, Ollama on :11434, CLI Proxy on :8090) |
| No models in dropdown | Load a model in LM Studio/Ollama — only loaded/active models are listed |
| CLI Proxy 404 on all routes | Port 8080 may be taken by Docker. The default was changed to 8090 in `bin/config.yaml` |
| CLI Proxy auth expired | Re-login via **Settings > API Keys > Login with Google**, or run `cli-proxy-api -login` in terminal |
| Tool calling not working | Use a model that supports function/tool calling (Qwen 2.5, Llama 3.1+, Mistral, Gemini, etc.) |
| Conversations not loading | Make sure the backend is running — conversations are stored in `backend/data/conversations.db` |
| CORS errors in browser console | Make sure the backend is running on port 8000 and `VITE_API_URL` is correct |
| `pip install` fails | Make sure you're using Python 3.11+. Try upgrading pip: `pip install --upgrade pip` |
| Port already in use | Kill the process using the port or change the port in the respective config |
