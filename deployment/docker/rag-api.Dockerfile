FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Install the core package and API dependencies
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[api]"

# Create data dirs
RUN mkdir -p /app/data/uploads /app/data/chroma

EXPOSE 8100

ENV RAG_SERVER_HOST=0.0.0.0
ENV RAG_SERVER_PORT=8100

CMD ["sh", "-c", "uvicorn smart_doc_search.api.main:app --host 0.0.0.0 --port 8100 --workers ${RAG_SERVER_WORKERS:-1}"]
