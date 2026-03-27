# --- Stage 1: Build C dependencies ---
FROM public.ecr.aws/docker/library/python:3.12-slim AS builder

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    ca-certificates \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Download and compile TA-Lib C library
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr CFLAGS="-O2" && \
    make && \
    make install && \
    cd / && \
    rm -rf ta-lib ta-lib-0.4.0-src.tar.gz

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install python dependencies
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project --no-cache

# --- Stage 2: Final Runner ---
FROM public.ecr.aws/docker/library/python:3.12-slim

WORKDIR /app

# Install tini for proper signal handling in containers
RUN apt-get update && apt-get install -y --no-install-recommends \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Copy TA-Lib shared libraries from builder
COPY --from=builder /usr/lib/libta_lib* /usr/lib/
RUN ldconfig

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY src/ /app/src/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONHASHSEED=random \
    DUCKDB_PATH="/app/data/trading.db"

# Create runtime user and ensure DB directory is writable
RUN useradd --create-home --uid 10001 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

# Default command to run the bot
ENTRYPOINT ["tini", "--", "python", "-m", "src.bot"]
CMD ["run"]
