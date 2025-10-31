FROM python:3.11-slim

# Faster, cleaner logs
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (minimal, wheels should cover most)
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

# Install Python deps first for better layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy app source (accounts.txt is intentionally .dockerignored)
COPY . .

# Expose default port
EXPOSE 8000

# Persist blacklist to a mounted volume by default (set via env in compose)
ENV BLACKLIST_FILE=/data/blacklist.pkl

# Start via the provided launcher (no reload in container)
CMD ["python", "main.py", "--host", "0.0.0.0", "--port", "8000"]