# Minimal dev Makefile
COMPOSE ?= docker compose
APP     ?= app
OLLAMA  ?= ollama

.PHONY: up down logs rebuild ps sh sh-ollama run clean

up:          ## Stack starten (detached)
	$(COMPOSE) up -d

down:        ## Stoppen & entfernen
	$(COMPOSE) down

logs:        ## App-Logs verfolgen
	$(COMPOSE) logs -f $(APP)

rebuild:     ## Images neu bauen & Container neu erstellen
	$(COMPOSE) up -d --build --force-recreate

ps:          ## Status anzeigen
	$(COMPOSE) ps

shell:          ## Shell in die App
	$(COMPOSE) exec $(APP) bash

shell-ollama:   ## Shell in den Ollama-Container
	$(COMPOSE) exec $(OLLAMA) bash

run:
	$(COMPOSE) run --rm $(APP) bash -lc "$$ARGS"

clean:       ## Aufräumen (Volumes & lokale Images)
	$(COMPOSE) down -v --rmi local

fclean:       ## Aufräumen (Volumes & lokale Images)
	docker system prune -a --volumes

docker-prepare:
	mkdir -p ~/.docker
	echo '{"cliPluginsExtraDirs":["/Users/$(USER)/.brew/lib/docker/cli-plugins"]}' > ~/.docker/config.json
	brew install docker-compose
	brew install colima docker
	colima start --memory 10 --cpu 4

## lama api temparature+

## factual consistency (how factually correct your LLM application is based on the respective context in your evals ## dataset)
## answer relevancy (how relevant your LLM application’s outputs are based on the respective inputs in your evals ## dataset)
## coherence (how logical and consistent your LLM application’s outputs are)
## toxicity (whether your LLM application is outputting harmful content)
## RAGAS (for RAG pipelines)
## bias (pretty self-explanatory)