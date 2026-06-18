# Job Apply Agent v0.2 🤖

An **agentic AI system** that automatically searches for jobs, evaluates fit, tailors your resume, and applies — powered by **local Ollama LLM** with **RAG**, **MCP**, and **A2A** protocol support.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PROTOCOL LAYER                              │
│   MCP Server (tools)  │  A2A Server (agent discovery + tasks)       │
│   FastAPI HTTP         │  /.well-known/agent.json                   │
├─────────────────────────────────────────────────────────────────────┤
│                        ORCHESTRATOR                                  │
│   Event Bus  │  Pipeline Coordination  │  Rate Limiting             │
├──────────┬──────────────┬───────────────┬───────────────────────────┤
│  Search  │   Matcher    │    Resume     │    Application            │
│  Agent   │   Agent      │    Agent      │    Agent                  │
│          │              │               │                           │
│ Plugins: │ AI scoring   │ AI generation │ Browser automation        │
│ • Indeed │ + RAG context│ + RAG context │ + AI form mapping         │
│ • LinkedIn│             │               │                           │
│ • (more) │              │               │                           │
├──────────┴──────────────┴───────────────┴───────────────────────────┤
│                        SERVICES LAYER                                │
│  LLM Provider │ RAG (ChromaDB) │ Database │ Browser │ HTTP Client   │
├─────────────────────────────────────────────────────────────────────┤
│                         CORE LAYER                                   │
│  Interfaces │ Models │ Event Bus │ Plugin Registry │ DI Container   │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Design Patterns

| Pattern | Implementation |
|---------|---------------|
| **Dependency Inversion** | All agents depend on interfaces (`LLMProvider`, `VectorStore`, `JobSource`), not concrete classes |
| **Plugin System** | Job sources (Indeed, LinkedIn) are registered plugins — add new ones without modifying existing code |
| **Event Bus** | Decoupled inter-agent communication via publish/subscribe events |
| **RAG** | Past applications, job descriptions, and profile indexed in ChromaDB for context-enriched AI decisions |
| **MCP Protocol** | External AI systems can use our agents as tools via standard Model Context Protocol |
| **A2A Protocol** | Google's Agent-to-Agent protocol for agent discovery and task routing |
| **DI Container** | Single composition root wires all dependencies — easy to test and swap implementations |
| **Template Engine** | Prompts separated from logic via Jinja2 templates |

## Features

- **Multi-agent architecture** with clear separation of concerns
- **100% local AI** via Ollama — data never leaves your machine
- **RAG-augmented decisions** — learns from past applications
- **MCP server** — use from Claude, VS Code Copilot, or any MCP client
- **A2A protocol** — discoverable by other AI agents
- **Pluggable job sources** — add Glassdoor, RemoteOK, etc. easily
- **Browser automation** — Playwright fills forms with AI-guided field mapping
- **Safety first** — `auto_submit=false` by default, screenshots for review
- **Scheduled runs** — automatic periodic searching
- **Rich CLI** — beautiful terminal output

## Quick Start

### Prerequisites

1. **Python 3.11+**
2. **Ollama** ([ollama.com](https://ollama.com))

```bash
ollama pull llama3.1
ollama pull nomic-embed-text  # For RAG embeddings
```

### Installation

```bash
cd job-apply-agent
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # Linux/Mac

pip install -e .
playwright install chromium
```

### Setup

```bash
job-agent init    # Creates dirs + .env template
# Edit .env with your profile and preferences
```

### Usage

```bash
# Search only (safe mode)
job-agent run --search-only

# Full pipeline
job-agent run

# Run on schedule
job-agent schedule

# Start MCP + A2A server
job-agent serve

# Stats
job-agent status
```

## MCP Integration

Start the server and add to your MCP client config:

```json
{
  "mcpServers": {
    "job-agent": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```

Available MCP tools:
- `search_jobs` — Search for matching jobs
- `match_job` — Score job-profile fit
- `generate_cover_letter` — Create tailored cover letter
- `get_application_stats` — Get stats
- `apply_to_job` — Submit application

## A2A Protocol

Agent card available at: `http://localhost:8000/.well-known/agent.json`

Other A2A-compatible agents can discover and send tasks to this agent.

## Project Structure

```
src/job_apply_agent/
├── core/                      # Shared infrastructure
│   ├── interfaces.py          # Abstract interfaces (LLM, VectorStore, JobSource)
│   ├── models.py              # Pydantic data models
│   ├── events.py              # Event bus (pub/sub)
│   └── registry.py            # Plugin registry
├── services/                  # Reusable service implementations
│   ├── llm.py                 # Ollama LLM provider
│   ├── rag.py                 # RAG service (ChromaDB + retrieval)
│   ├── database.py            # SQLite persistence
│   ├── browser.py             # Playwright automation
│   └── http_client.py         # Shared HTTP client
├── agents/                    # Independent agents
│   ├── base.py                # Base agent (A2A-compatible)
│   ├── search_agent.py        # Job discovery + source plugins
│   ├── matcher_agent.py       # Profile matching with RAG
│   ├── resume_agent.py        # Resume/cover letter with RAG
│   ├── apply_agent.py         # Browser form filling
│   └── orchestrator.py        # Pipeline coordinator
├── protocols/                 # External protocol support
│   ├── mcp_server.py          # MCP tool definitions
│   ├── a2a_server.py          # A2A protocol server
│   └── http_server.py         # FastAPI endpoints
├── prompts/                   # Prompt templates (separated from logic)
│   └── templates/
│       ├── match_job.j2
│       ├── tailor_summary.j2
│       ├── cover_letter.j2
│       ├── extract_requirements.j2
│       └── form_mapping.j2
├── config.py                  # Settings management
├── container.py               # Dependency injection
└── cli.py                     # CLI commands
```

## Extending

### Add a new job source

```python
from job_apply_agent.core.interfaces import JobSource
from job_apply_agent.core.registry import registry

class GlassdoorSource(JobSource):
    @property
    def name(self) -> str:
        return "glassdoor"

    async def search(self, title, location, **kwargs):
        # Your implementation
        ...

    async def fetch_details(self, url):
        ...

# Register the plugin
registry.register_job_source(GlassdoorSource())
```

### Swap LLM provider

```python
from job_apply_agent.core.interfaces import LLMProvider

class OpenAIProvider(LLMProvider):
    async def generate(self, prompt, system="", temperature=0.7):
        # OpenAI implementation
        ...
```

### Add event listeners

```python
from job_apply_agent.core.events import event_bus, EventType

async def on_job_applied(event):
    # Send notification, update spreadsheet, etc.
    print(f"Applied to {event.data['job_id']}")

event_bus.subscribe(EventType.JOB_APPLIED, on_job_applied)
```

## RAG: How It Works

The RAG system improves AI decisions by providing relevant context:

1. **Indexing**: Job descriptions, application outcomes, and your profile are embedded and stored in ChromaDB
2. **Retrieval**: Before any AI call, relevant past data is retrieved
3. **Augmentation**: Retrieved context is injected into prompts

Example: When matching a new "Senior Python Engineer" role, RAG retrieves your past applications to similar roles, so the AI knows which approaches worked.

## Similar Projects

| Project | Differentiator |
|---------|---------------|
| [AIHawk](https://github.com/AIHawk-JEYZ/Auto_Jobs_Applier_AIHawk) | Uses OpenAI, LinkedIn-focused |
| [AutoApply](https://github.com/Liam-Frost/AutoApply) | Multi-platform, human gating |
| **This project** | Local AI, RAG, MCP/A2A, plugin architecture |

## License

MIT
#   A g e n t i c - J o b - A p p l y  
 