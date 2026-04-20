FROM python:3.11-slim

WORKDIR /app

# Install system deps for playwright + jobspy
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc build-essential curl \
    && rm -rf /var/lib/apt/lists/*

# Install main backend package first (for applypilot.discovery.jobspy etc.)
COPY ../backend/pyproject.toml ../backend/README.md /backend/
COPY ../backend/src /backend/src
RUN pip install --no-cache-dir /backend

# Install discovery-service deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers
RUN playwright install --with-deps chromium

# Copy service files
COPY . .

CMD ["python", "main.py"]
