FROM python:3.11-slim

# System-Dependencies
RUN apt-get update && apt-get install -y curl bash && rm -rf /var/lib/apt/lists/*

# App rein
WORKDIR /app
COPY . /app

# Python-Dependencies (richtiger Pfad!)
RUN pip install --no-cache-dir -r /app/resources/requirements.txt
RUN pip install deepeval

# Optional: Fallback-ENV
ENV PYTHONPATH=/app

# Port (falls später Webserver)
EXPOSE 8000

# WICHTIG: Im resources-Ordner starten, damit relative data/-Pfade stimmen
WORKDIR /app/resources
