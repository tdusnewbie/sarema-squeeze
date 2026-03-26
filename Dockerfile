# --- Stage 1: Build C dependencies ---
FROM python:3.12-slim AS builder

# Install build tools
RUN apt-get update && apt-get install -y \
    build-essential \
    wget \
    make \
    && rm -rf /var/lib/apt/lists/*

# Download and compile TA-Lib C library
RUN wget http://prdownloads.sourceforge.net/ta-lib/ta-lib-0.4.0-src.tar.gz && \
    tar -xvzf ta-lib-0.4.0-src.tar.gz && \
    cd ta-lib/ && \
    ./configure --prefix=/usr CFLAGS="-O2 -march=x86-64 -mtune=generic" && \
    make && \
    make install

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install python dependencies
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --no-cache

# --- Stage 2: Final Runner ---
FROM python:3.12-slim

WORKDIR /app

# Copy TA-Lib shared libraries from builder
COPY --from=builder /usr/lib/libta_lib* /usr/lib/
# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY src/ /app/src/

# Set environment variables
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1
ENV POLARS_SKIP_CPU_CHECK=1

# Default command to run the bot
ENTRYPOINT ["python", "-m", "src.bot"]
CMD ["run"]
