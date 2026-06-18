"""Start both the FastAPI server and Streamlit dashboard in one command.

Usage:
    python start.py          # Starts server (8000) + dashboard (8501)
    python start.py --server-only
    python start.py --dashboard-only
"""

import subprocess
import sys
import signal
import os

SERVER_CMD = [sys.executable, "-m", "job_agent_server.main"]
DASHBOARD_CMD = [
    sys.executable, "-m", "streamlit", "run",
    "packages/dashboard/src/job_agent_dashboard/app.py",
    "--server.port=8501",
    "--server.headless=true",
]


def main() -> None:
    args = sys.argv[1:]
    server_only = "--server-only" in args
    dashboard_only = "--dashboard-only" in args

    processes: list[subprocess.Popen] = []

    def shutdown(signum=None, frame=None):
        for proc in processes:
            proc.terminate()
        for proc in processes:
            proc.wait(timeout=5)
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("=" * 60)
    print("  Agentic Job Apply - Starting Services")
    print("=" * 60)

    if not dashboard_only:
        print("\n🚀 Starting FastAPI server on http://localhost:8000")
        server = subprocess.Popen(SERVER_CMD, cwd=os.getcwd())
        processes.append(server)

    if not server_only:
        print("📊 Starting Streamlit dashboard on http://localhost:8501")
        dashboard = subprocess.Popen(DASHBOARD_CMD, cwd=os.getcwd())
        processes.append(dashboard)

    print("\n✅ All services running. Press Ctrl+C to stop.\n")

    # Wait for any process to exit
    try:
        for proc in processes:
            proc.wait()
    except KeyboardInterrupt:
        shutdown()


if __name__ == "__main__":
    main()
