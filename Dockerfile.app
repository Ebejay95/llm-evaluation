FROM python:3.11-slim

# System-Dependencies
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# App rein
WORKDIR /app
COPY . /app

# Python-Dependencies (richtiger Pfad!)
RUN pip install --no-cache-dir -r /app/resources/requirements.txt

# Optional: Fallback-ENV
ENV PYTHONPATH=/app

# Port (falls später Webserver)
EXPOSE 8000

# WICHTIG: Im resources-Ordner starten, damit relative data/-Pfade stimmen
WORKDIR /app/resources

# Standardkommando – Modell/Provider/URL bei Bedarf per Argument überschreiben
CMD ["python", "week_01_exploration.py", "--ids", "c-001", "--with-llm", "--provider", "ollama", "--ollama-url", "http://ollama:11434"]
