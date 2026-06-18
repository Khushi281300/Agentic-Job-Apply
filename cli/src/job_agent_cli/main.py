"""CLI interface for the job application agent.

Commands:
- run          : Full pipeline (search → match → tailor → apply)
- search       : Search only mode
- serve        : Start HTTP server with MCP + A2A endpoints
- schedule     : Run on a timer
- status       : Show application statistics
- config       : Display current configuration
- init         : Interactive setup
"""

import asyncio
import logging
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler

app = typer.Typer(
    name="job-agent",
    help="AI-powered personal job application agent (Ollama + RAG + MCP + A2A)",
)
console = Console()


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(rich_tracebacks=True, show_path=False)],
    )


def _get_container():
    from job_agent_agents.container import build_container
    return build_container()


@app.command()
def run(
    search_only: bool = typer.Option(False, "--search-only", "-s", help="Only search and match"),
    no_graph: bool = typer.Option(False, "--no-graph", help="Use direct pipeline (skip LangGraph)"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Debug logging"),
) -> None:
    """Run the job application pipeline."""
    from job_agent_agents.config import load_settings
    settings = load_settings()
    setup_logging("DEBUG" if verbose else settings.log_level)

    console.print("[bold blue]🤖 Job Application Agent v0.4[/bold blue]")
    console.print(f"Model: {settings.ollama.model} | Auto-submit: {settings.application.auto_submit}")
    console.print(f"Email App: {'on' if settings.email_app.smtp_host else 'off'} | "
                  f"LangGraph: {'off' if no_graph else 'on'} | "
                  f"LangSmith: {'on' if settings.langsmith.enabled else 'off'}")
    console.print("─" * 50)

    container = _get_container()

    async def _run():
        await container.startup()
        if search_only:
            return await container.orchestrator.run_search_only()
        return await container.orchestrator.run(use_graph=not no_graph)

    result = asyncio.run(_run())

    if search_only and isinstance(result, list):
        console.print(f"\nFound {len(result)} matching jobs:")
        for job in result:
            console.print(f"  • {job.title} @ {job.company} - {job.url}")


@app.command()
def serve(
    port: int = typer.Option(8000, "--port", "-p", help="Server port"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Start HTTP server with MCP + A2A protocol endpoints."""
    import uvicorn
    from job_agent_server.main import main as server_main

    setup_logging("DEBUG" if verbose else "INFO")
    console.print(f"[bold green]🚀 Starting MCP + A2A server on port {port}[/bold green]")
    console.print(f"  A2A Agent Card: http://localhost:{port}/.well-known/agent.json")
    console.print(f"  MCP Tools:      http://localhost:{port}/mcp/tools/list")
    console.print(f"  Health:         http://localhost:{port}/health")

    server_main(port=port)


@app.command()
def schedule(
    verbose: bool = typer.Option(False, "--verbose", "-v"),
) -> None:
    """Run the agent on a schedule."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from job_agent_agents.config import load_settings

    settings = load_settings()
    setup_logging("DEBUG" if verbose else settings.log_level)
    interval = settings.application.search_interval_minutes

    console.print(f"[bold]⏰ Running every {interval} minutes[/bold] (Ctrl+C to stop)")

    container = _get_container()
    scheduler = BlockingScheduler()
    _initialized = False

    async def _run_pipeline():
        nonlocal _initialized
        if not _initialized:
            await container.startup()
            _initialized = True
        await container.orchestrator.run()

    def job():
        asyncio.run(_run_pipeline())

    scheduler.add_job(job, "interval", minutes=interval, id="pipeline")
    job()  # Run immediately
    scheduler.start()


@app.command()
def status() -> None:
    """Show application statistics."""
    container = _get_container()

    async def _status():
        await container.db.initialize()
        return await container.db.get_stats()

    stats = asyncio.run(_status())
    console.print("\n[bold]📊 Application Statistics[/bold]")
    console.print(f"  Total Discovered: {stats['total_discovered']}")
    console.print(f"  Applied:          {stats['applied']}")
    console.print(f"  Matched Pending:  {stats['matched_pending']}")
    console.print(f"  Rejected:         {stats['rejected']}")


@app.command()
def config() -> None:
    """Display current configuration."""
    from job_agent_agents.config import load_settings
    settings = load_settings()
    console.print("\n[bold]⚙️  Configuration[/bold]")
    console.print(f"  Ollama:        {settings.ollama.base_url} ({settings.ollama.model})")
    console.print(f"  Embed Model:   {settings.ollama.embed_model}")
    console.print(f"  Job Titles:    {', '.join(settings.search.titles)}")
    console.print(f"  Locations:     {', '.join(settings.search.locations)}")
    console.print(f"  Min Salary:    ${settings.search.min_salary:,}")
    console.print(f"  Auto Submit:   {settings.application.auto_submit}")
    console.print(f"  Max/Day:       {settings.application.max_applications_per_day}")
    console.print(f"  Min Score:     {settings.application.min_match_score:.0%}")
    console.print(f"  Email SMTP:    {settings.email_app.smtp_host or 'not configured'}")
    console.print(f"  LangGraph:     enabled")
    console.print(f"  LangSmith:     {'enabled (' + settings.langsmith.project + ')' if settings.langsmith.enabled else 'disabled'}")
    console.print(f"  Server Port:   {settings.server_port}")


@app.command()
def init() -> None:
    """Initialize the agent (create dirs, copy config)."""
    console.print("[bold]🚀 Job Agent Setup[/bold]\n")

    dirs = ["data", "data/cover_letters", "data/screenshots", "data/vectordb", "logs"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)

    env_file = Path(".env")
    env_example = Path(".env.example")
    if not env_file.exists() and env_example.exists():
        env_file.write_text(env_example.read_text())
        console.print("[green]✓[/green] Created .env from template")

    console.print("[green]✓[/green] Directories created")
    console.print("\n[bold]Next steps:[/bold]")
    console.print("  1. Edit .env with job search preferences")
    console.print("  2. Place your resume PDF at data/resume.pdf")
    console.print("  3. Start Ollama: ollama serve")
    console.print("  4. Pull models: ollama pull llama3.1 && ollama pull nomic-embed-text")
    console.print("  5. Run: job-agent run --search-only")
