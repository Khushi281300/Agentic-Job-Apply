# Agentic Job Apply 🤖

An **agentic AI system** that automatically searches for remote jobs, evaluates fit, tailors your resume, and applies — powered by **local Ollama LLM** with **RAG**, **MCP**, and **A2A** protocol support.

---

## ✨ Features

- **Multi-agent pipeline** — Search → Match → Tailor Resume → Apply (fully automated)
- **100% local AI** via Ollama (llama3.1 + nomic-embed-text) — data never leaves your machine
- **RAG-augmented decisions** — learns from past applications via ChromaDB
- **MCP server** — use from Claude, VS Code Copilot, or any MCP client
- **A2A protocol** — discoverable by other AI agents (Google's Agent-to-Agent)
- **Real-time dashboard** — Streamlit UI with WebSocket live updates
- **Per-source rate limiting** with health monitoring
- **Success rate tracking** — analytics by source, score range, outcomes
- **High-match instant alerts** — Telegram/Slack notifications for 90%+ matches
- **Interview prep generator** — AI-generated Q&A for applied jobs
- **CSV/JSON export** of all application data
- **Browser automation** — Playwright fills forms with AI-guided field mapping
- **Safety first** — `auto_submit=false` by default, screenshots for review

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          PROTOCOL LAYER                                  │
│   MCP Server (tools)  │  A2A Server (tasks)  │  WebSocket (live updates)│
│   FastAPI HTTP :8000   │  /.well-known/agent.json                       │
├─────────────────────────────────────────────────────────────────────────┤
│                         ORCHESTRATOR (LangGraph)                         │
│   Event Bus  │  Pipeline Coordination  │  Rate Limiting  │  Caching    │
├──────────┬──────────────┬───────────────┬───────────────────────────────┤
│  Search  │   Matcher    │    Resume     │    Application                │
│  Agent   │   Agent      │    Agent      │    Agent                      │
│          │              │               │                               │
│ Sources: │ AI scoring   │ AI generation │ Browser automation            │
│ • RemoteOK│ + RAG context│ + cover letter│ + AI form mapping            │
│ • Remotive│ + alerts    │ + RAG context │ + email applications          │
│ • Rocketship│           │               │ + follow-up scheduling        │
├──────────┴──────────────┴───────────────┴───────────────────────────────┤
│                         SERVICES LAYER                                   │
│  LLM (Ollama) │ RAG (ChromaDB) │ SQLite │ Browser │ Notifications      │
├─────────────────────────────────────────────────────────────────────────┤
│                          CONTRACTS LAYER                                 │
│  Interfaces │ Models │ Events │ Plugin Registry │ Error Handling        │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Project Structure (uv Monorepo)

```
job-apply-agent/
├── packages/
│   ├── contracts/          # Abstract interfaces, models, events
│   ├── services/           # Infrastructure (LLM, DB, scrapers, notifications)
│   ├── agents/             # AI agents + LangGraph workflow
│   ├── server/             # FastAPI server (MCP + A2A + REST API)
│   └── dashboard/          # Streamlit real-time UI
├── cli/                    # CLI commands
├── config/                 # Job source configuration
├── tests/                  # Unit + integration tests (40 passing)
├── data/vectordb/          # ChromaDB persistence
├── pyproject.toml          # Workspace root
└── docker-compose.yml      # Containerized deployment
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Ollama** ([ollama.com](https://ollama.com))
- **uv** (recommended) or pip

```bash
# Pull required models
ollama pull llama3.1
ollama pull nomic-embed-text
```

### Installation

```bash
cd job-apply-agent

# Install with uv (recommended)
uv sync

# Or with pip
pip install -e .

# Install browser for automation
playwright install chromium
```

### Run the Server

```bash
# Start FastAPI server (port 8000)
python -m job_agent_server.main

# Start Streamlit dashboard (port 8501)
streamlit run packages/dashboard/src/job_agent_dashboard/app.py
```

### Docker

```bash
docker-compose up
```

---

## 🖥️ Dashboard Pages

| Page | Description |
|------|-------------|
| 🔍 **Search Jobs** | Trigger job searches across all sources |
| 🚀 **Run Pipeline** | Start full end-to-end pipeline with live status |
| 📋 **Pipeline Results** | View matched jobs, scores, cover letters |
| 🎯 **Interview Prep** | AI-generated questions for applied jobs |
| 📈 **Analytics** | Success rates by source, score range, outcomes |
| 🏥 **Source Health** | Rate limit usage, latency, errors per source |

---

## 🔌 API Endpoints

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/ready` | Readiness with dependency checks |
| `GET` | `/status` | Full pipeline status |
| `WS` | `/ws` | WebSocket live updates |

### Jobs & Analytics

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/jobs` | List all jobs (optional `?status=` filter) |
| `GET` | `/jobs/{id}` | Job detail with match data |
| `POST` | `/jobs/{id}/outcome` | Record outcome (interview/offer/rejected) |
| `GET` | `/analytics` | Success rate analytics |
| `GET` | `/follow-ups` | Applications due for follow-up |
| `POST` | `/interview-prep/{id}` | Generate interview questions |

### Export & Monitoring

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/export/csv` | Download all data as CSV |
| `GET` | `/export/json` | Download all data as JSON |
| `GET` | `/sources/health` | All sources rate limit status |
| `GET` | `/sources/health/{name}` | Specific source health |

### Protocols

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/.well-known/agent.json` | A2A agent card |
| `POST` | `/a2a/tasks/send` | Send task to agent |
| `POST` | `/mcp/tools/list` | List MCP tools |
| `POST` | `/mcp/tools/call` | Call MCP tool |

---

## 🔧 MCP Integration

Add to your MCP client config:

```json
{
  "mcpServers": {
    "job-agent": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

**Available tools:** `search_jobs`, `match_job`, `generate_cover_letter`, `apply_to_job`, `get_application_stats`

---

## 🧩 Key Design Patterns

| Pattern | Implementation |
|---------|---------------|
| **Dependency Inversion** | Agents depend on interfaces, not concrete classes |
| **Plugin System** | Job sources are registered plugins — add new ones without modifying code |
| **Event Bus** | Decoupled pub/sub communication between agents |
| **RAG** | ChromaDB-powered context for AI decisions |
| **Rate Limiting** | Per-source token bucket with health tracking |
| **DI Container** | Single composition root wires all dependencies |
| **Template Engine** | Jinja2 prompt templates separated from logic |

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# Current: 40 tests passing
```

---

## 📄 License

MIT
