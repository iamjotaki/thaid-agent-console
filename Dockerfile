FROM python:3.11-slim

WORKDIR /app

# Install system utilities & native docker CLI
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    procps \
    ca-certificates \
    docker.io \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8098

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8098"]
