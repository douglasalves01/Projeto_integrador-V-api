.PHONY: help install api.run ai.run ai.train analytics.run \
        test test.api test.ai lint format db.migrate db.revision \
        compose.up compose.down compose.logs compose.analytics

help:           ## Lista os targets
	@grep -E '^[a-zA-Z_.-]+:.*?## ' $(MAKEFILE_LIST) | awk -F':.*?## ' '{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

# -------- bootstrap --------
install:        ## Instala deps de todos os apps em modo dev
	pip install -e packages/shared
	cd apps/api && pip install -r requirements.txt
	cd apps/ai && pip install -r requirements.txt
	pip install -e apps/analytics

# -------- run local --------
api.run:        ## Sobe a API (porta 8001 local)
	cd apps/api && uvicorn app.main:app --reload --port 8001

ai.run:         ## Sobe a IA (porta 8002 local)
	cd apps/ai && uvicorn app.main:app --reload --port 8002

ai.train:       ## Treina VodRec-Transformer (com dataset em apps/ai/data)
	cd apps/ai && python scripts/train_and_evaluate.py \
		--interactions data/interactions.parquet \
		--epochs 20 --version vodrec-v1.0.0

ai.validate:    ## Valida RFIA01-04 do modelo treinado
	cd apps/ai && python scripts/validate_requirements.py

ai.dataset:     ## Gera dataset sintetico de exemplo
	cd apps/ai && python scripts/generate_dataset.py \
		--n-users 1500 --n-contents 400 --avg-interactions 50 \
		--fav-bias 0.85 --out-dir data

analytics.run:  ## Roda todos os jobs de analytics
	cd apps/analytics && python -m analytics export_all

# -------- testes --------
test: test.api test.ai  ## Roda toda a suite

test.api:
	cd apps/api && pytest -q

test.ai:
	cd apps/ai && pytest -q

# -------- qualidade --------
lint:           ## Roda ruff em todos os apps
	ruff check apps/ packages/

format:         ## Formata
	ruff format apps/ packages/

# -------- banco --------
db.migrate:     ## Aplica migrations
	cd apps/api && alembic upgrade head

db.revision:    ## Cria nova migration (NAME="texto")
	cd apps/api && alembic revision --autogenerate -m "$(NAME)"

# -------- compose --------
compose.up:     ## Sobe a stack (db + api + ai)
	docker compose -f infra/docker-compose.yml up --build -d

compose.down:   ## Derruba tudo
	docker compose -f infra/docker-compose.yml down

compose.logs:   ## Tails dos logs
	docker compose -f infra/docker-compose.yml logs -f

compose.analytics:  ## Roda jobs de analytics (oneshot)
	docker compose -f infra/docker-compose.yml --profile analytics run --rm analytics
