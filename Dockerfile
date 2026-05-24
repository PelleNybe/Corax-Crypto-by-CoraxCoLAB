# Stage 1: Build dependencies
FROM python:3.11-slim AS builder

# Install system dependencies required for compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    libffi-dev \
    python3-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python3 -
ENV PATH="/opt/poetry/bin:$PATH"

WORKDIR /app

# Copy dependency definition
COPY pyproject.toml poetry.lock ./

# Install dependencies into a virtual environment in-project (.venv)
RUN poetry config virtualenvs.create true \
    && poetry config virtualenvs.in-project true \
    && poetry install --only main --no-root

# Stage 2: Runtime Image
FROM python:3.11-slim

# Installera Tini för att förhindra zombie-processer
RUN apt-get update && apt-get install -y --no-install-recommends tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Kopiera den virtuella miljön från builder-stadiet
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Kopiera källkoden
COPY . .

# Skapa mappar för mounts
RUN mkdir -p data logs config

# Expose API port
EXPOSE 8000

# Set Python unbuffered mode
ENV PYTHONUNBUFFERED=1

# Använd Tini som entrypoint för stabil signalhantering
ENTRYPOINT ["/usr/bin/tini", "--"]

# Starta motorn
CMD ["python", "main.py"]