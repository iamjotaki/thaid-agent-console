FROM python:3.11-slim

WORKDIR /app

# Install system utilities & native static docker CLI (aarch64)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    procps \
    ca-certificates \
    && curl -fsSL https://download.docker.com/linux/static/stable/aarch64/docker-26.1.4.tgz | tar -xz -C /tmp \
    && mv /tmp/docker/docker /usr/local/bin/ \
    && rm -rf /tmp/docker \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8098

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8098"]
