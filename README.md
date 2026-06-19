# Agentic Job Apply 🤖

An **agentic AI system** that automatically searches for remote jobs, evaluates fit, tailors your resume, and applies — powered by **local Ollama LLM** with **RAG**, **MCP**, and **A2A** protocol support.

---

## ✨ Features

### Core Pipeline
- **Multi-agent pipeline** — Search → Match → Tailor Resume → Apply (fully automated)
- **100% local AI** via Ollama (llama3.1 + nomic-embed-text) — data never leaves your machine
- **RAG-augmented decisions** — learns from past applications via ChromaDB
- **MCP server** — use from Claude, VS Code Copilot, or any MCP client
- **A2A protocol** — discoverable by other AI agents (Google's Agent-to-Agent)
- **Browser automation** — Playwright fills forms with AI-guided field mapping
- **Email applications** — auto-detects email jobs and sends with resume attachment
- **Safety first** — `auto_submit=false` by default, screenshots for review

### Intelligence & Learning
- **Adaptive match thresholds** — learns optimal cutoffs from historical outcomes
- **Outcome feedback loop** — indexes results into RAG for continuous learning
- **Profile strength scoring** — analyzes your skills vs market demand
- **Salary market insights** — aggregated compensation data from listings
- **Semantic job deduplication** — fuzzy title+company matching avoids re-processing

### Reliability & Observability
- **Circuit breaker** — automatic failure detection with CLOSED/OPEN/HALF_OPEN states
- **Retry queue** — persistent SQLite queue with exponential backoff + dead letters
- **Multi-model LLM fallback** — chain multiple providers, auto-fallback on failure
- **Structured logging** — JSON/human-readable formatters with log level control
- **Per-source rate limiting** with health monitoring

### Notifications & Scheduling
- **High-match instant alerts** — Telegram/Slack notifications for 90%+ matches
- **Daily email digests** — summary of pipeline activity
- **Webhook integrations** — POST to any URL on events (applied, matched, etc.)
- **Async scheduler** — cron-free recurring pipeline runs

### Dashboard & Analytics
- **Real-time dashboard** — Streamlit UI with live pipeline logging
- **Live pipeline log** — real-time activity feed showing every agent step (search → match → tailor → apply)
- **DB-persisted pipeline logs** — all pipeline runs saved to SQLite with full IO history
- **Past pipeline runs** — browse logs from previous runs by run ID
- **Application timeline** — visual journey of each job (discovered → applied → outcome)
- **Success rate tracking** — analytics by source, score range, outcomes
- **Interview prep generator** — AI-generated Q&A for applied jobs
- **CSV/JSON export** of all application data

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
│ • Remotive│ + adaptive  │ + RAG context │ + email applications          │
│ • Rocketship│ thresholds │              │ + follow-up scheduling        │
├──────────┴──────────────┴───────────────┴───────────────────────────────┤
│                         SERVICES LAYER                                   │
│  LLM (Ollama)  │ RAG (ChromaDB) │ SQLite │ Browser │ Notifications     │
│  Circuit Breaker│ Rate Limiter   │ Retry Q│ Scheduler│ Webhooks         │
├─────────────────────────────────────────────────────────────────────────┤
│                          CONTRACTS LAYER                                 │
│  Interfaces │ Models │ Events │ Plugin Registry │ Decorators            │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 📦 Project Structure (uv Monorepo)

```
job-apply-agent/
├── packages/
│   ├── contracts/          # Abstract interfaces, models, events, decorators
│   ├── services/           # Infrastructure (LLM, DB, scrapers, resilience)
│   │   ├── sources/        # Job board scrapers (BaseJobSource pattern)
│   │   ├── resilience/     # Circuit breaker, rate limiter, retry policy
│   │   ├── observability/  # Structured logging
│   │   ├── llm/            # LLM providers + fallback chain
│   │   ├── stores/         # SQLite + RAG (ChromaDB)
│   │   └── ...             # Scheduler, webhooks, digest, etc.
│   ├── agents/             # AI agents + LangGraph workflow
│   │   ├── llm_utils.py    # SafeLLMCaller (reusable LLM patterns)
│   │   ├── workflows/      # LangGraph graph + node factory
│   │   └── ...
│   ├── server/             # FastAPI server (MCP + A2A + REST API)
│   └── dashboard/          # Streamlit real-time UI
├── cli/                    # CLI commands
├── config/                 # Job source configuration
├── data/                   # User profile (profile.json), vector DB, screenshots
├── tests/                  # Unit + integration + contract tests (67 passing)
├── start.py                # One command to start everything
├── docker-compose.yml      # Containerized deployment
└── pyproject.toml          # Workspace root
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

### Run Everything (One Command)

```bash
# Start both server + dashboard
python start.py
```

This starts:
- **FastAPI server** → http://localhost:8000
- **Streamlit dashboard** → http://localhost:8501

```bash
# Or start individually
python start.py --server-only
python start.py --dashboard-only
```

### Docker

```bash
docker-compose up
```

---

## 🖥️ Dashboard Pages

| Page | Description |
|------|-------------|
| 📊 **Dashboard** | Overview metrics and status |
| 🚀 **Run Pipeline** | Start/stop pipeline with **live real-time activity log**, progress bar, stats, and past run history |
| 📋 **Pipeline Results** | View matched jobs, scores, cover letters |
| 📋 **Review Queue** | Approve/reject matched jobs |
| 📝 **Cover Letters** | View generated cover letters |
| 🎯 **Interview Prep** | AI-generated questions for applied jobs |
| 📈 **Analytics** | Success rates by source, score range, outcomes |
| 🏥 **Source Health** | Rate limit usage, latency, errors per source |
| 💪 **Profile Strength** | Skills vs market demand analysis |
| 💰 **Salary Insights** | Market compensation ranges |
| 📅 **Timeline** | Application journey visualization |
| 🗺️ **Pipeline Graph** | Visual workflow graph |
| 🔄 **Retry Queue** | Failed jobs retry management |
| 📡 **Webhooks** | Configure webhook integrations |
| ⚙️ **Settings** | Configuration management |

> **Run Pipeline** page features:
> - Pipeline configuration (job titles, locations, auto-apply toggle)
> - Start/Stop controls
> - 6-step progress bar (Idle → Searching → Matching → Tailoring → Applying → Completed)
> - Live stats (searched, matched, applied, emailed, errors)
> - Real-time activity log with human-readable messages for every agent step
> - Error display section
> - Past Pipeline Runs browser with DB-persisted logs

---

## 🔌 API Endpoints

### Core

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `GET` | `/ready` | Readiness with dependency checks |
| `GET` | `/status` | Full pipeline status |
| `WS` | `/ws` | WebSocket live updates |

### Jobs & Pipeline

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/jobs` | List all jobs (optional `?status=` filter) |
| `GET` | `/jobs/{id}` | Job detail with match data |
| `POST` | `/jobs/{id}/outcome` | Record outcome (interview/offer/rejected) |
| `GET` | `/analytics` | Success rate analytics |
| `GET` | `/follow-ups` | Applications due for follow-up |
| `POST` | `/interview-prep/{id}` | Generate interview questions |
| `GET` | `/timeline` | Application journey timeline |

### Pipeline Logs & Matching

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/pipeline/logs` | Get persisted pipeline logs (`?run_id=X&limit=100`) |
| `GET` | `/pipeline/runs` | List recent pipeline runs (`?limit=20`) |
| `POST` | `/match/test/{id}` | Test match scoring on a single job |
| `POST` | `/match/test-batch` | Batch match test on discovered jobs (`?limit=5`) |

### Intelligence

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/adaptive-thresholds` | Current adaptive scoring thresholds |
| `GET` | `/profile/strength` | Profile strength vs market demand |
| `GET` | `/salary-insights` | Market salary ranges |
| `GET` | `/circuit-breakers` | Circuit breaker health status |

### Infrastructure

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/sources/health` | All sources rate limit status |
| `GET` | `/sources/health/{name}` | Specific source health |
| `GET` | `/retry-queue/stats` | Retry queue statistics |
| `GET` | `/retry-queue/dead-letters` | Failed items (dead letter queue) |
| `GET` | `/scheduler/status` | Scheduled task statuses |
| `GET` | `/export/csv` | Download all data as CSV |
| `GET` | `/export/json` | Download all data as JSON |

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
| **Circuit Breaker** | CLOSED/OPEN/HALF_OPEN states to prevent cascade failures |
| **DI Container** | Single composition root wires all dependencies |
| **Template Engine** | Jinja2 prompt templates separated from logic |
| **BaseJobSource** | Shared error handling + item parsing for all scrapers |
| **SafeLLMCaller** | Reusable LLM call wrappers with fallback patterns |
| **@catch_and_log** | Decorator for consistent async error handling |
| **Shared Fixtures** | Reusable test mocks eliminate duplication |

---

## 🧪 Testing

```bash
# Run all tests
python -m pytest tests/ -v

# 67 tests passing (unit + integration + contract + e2e)
```

Test coverage includes:
- **Unit tests** — models, events, registry, tracing
- **Integration tests** — source scrapers, notifications, graph compilation
- **Contract tests** — API response format validation for all 3 job boards
- **E2E tests** — deduplication, circuit breaker, retry policy, adaptive scoring

---

## � User Profile

Create `data/profile.json` with your resume data for accurate job matching:

```json
{
  "name": "Your Name",
  "email": "you@example.com",
  "title": "AI Software Engineer",
  "summary": "Your professional summary...",
  "skills": ["Python", "LangChain", "FastAPI", ...],
  "experience_years": 3,
  "education": ["B.E. in Computer Science - University"],
  "certifications": ["AWS Solutions Architect"],
  "work_history": [
    {
      "title": "AI Engineer",
      "company": "Company",
      "duration": "2024 - Present",
      "description": "Built agentic AI systems..."
    }
  ]
}
```

The matcher uses this profile to score jobs against your skills, experience, and preferences. Without a profile, match scores will be low.

---

## �📄 License

MIT
