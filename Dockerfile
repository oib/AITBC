# Multi-stage build for AITBC CLI
FROM python:3.13-slim as builder

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY cli/requirements.txt .
COPY cli/requirements-dev.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir -r requirements-dev.txt

# Copy CLI source code
COPY cli/ .

# Install CLI in development mode
RUN pip install -e .

# Production stage
FROM python:3.13-slim as production

# Create non-root user
RUN useradd --create-home --shell /bin/bash aitbc

# Set working directory
WORKDIR /app

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy CLI from builder stage
COPY --from=builder /usr/local/lib/python3.13/site-packages /usr/local/lib/python3.13/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Create data directories
RUN mkdir -p /home/aitbc/.aitbc && \
    chown -R aitbc:aitbc /home/aitbc

# Switch to non-root user
USER aitbc

# Set environment variables
ENV PATH=/home/aitbc/.local/bin:$PATH
ENV PYTHONPATH=/app
ENV AITBC_DATA_DIR=/home/aitbc/.aitbc

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -m aitbc_cli.main --version || exit 1

# Default command
CMD ["python", "-m", "aitbc_cli.main", "--help"]
