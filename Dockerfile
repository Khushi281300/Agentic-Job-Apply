FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy all packages
COPY pyproject.toml .
COPY packages/ packages/
COPY cli/ cli/
COPY config/ config/

# Install workspace
RUN pip install --no-cache-dir -e packages/contracts \
    && pip install --no-cache-dir -e packages/services \
    && pip install --no-cache-dir -e packages/agents \
    && pip install --no-cache-dir -e packages/server \
    && pip install --no-cache-dir -e packages/dashboard \
    && pip install --no-cache-dir -e cli

# Install Playwright browsers
RUN playwright install chromium --with-deps

COPY .env.example .env.example

# Create data directories
RUN mkdir -p data/cover_letters data/screenshots data/vectordb logs

EXPOSE 8000

CMD ["job-agent", "serve", "--port", "8000"]
