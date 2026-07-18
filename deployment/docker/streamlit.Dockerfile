FROM python:3.11-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Install the core package and Streamlit dependencies
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir ".[streamlit]"

# Copy the Streamlit application
COPY apps/streamlit ./apps/streamlit

# Create data dirs
RUN mkdir -p /app/data/uploads /app/data/chroma

EXPOSE 8501

ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0

CMD ["streamlit", "run", "apps/streamlit/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
