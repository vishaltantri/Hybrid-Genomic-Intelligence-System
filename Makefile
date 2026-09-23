# GENOMIND-INDIA monorepo
.PHONY: help venv install docker-up docker-down etl kg-build demo api dashboard tests lint

help:
	@echo "venv        - create .venv and install core deps"
	@echo "install     - pip install -r requirements.txt (into .venv if present)"
	@echo "docker-up   - start Postgres+Redis+Neo4j+MLflow+LabelStudio+API"
	@echo "etl         - run all ETL parsers over data/raw -> data/processed"
	@echo "kg-build    - build the knowledge graph (Neo4j if up, else NetworkX/JSON)"
	@echo "api         - run FastAPI dev server on :8000"
	@echo "demo        - run the end-to-end demo (all 11 modules)"
	@echo "tests       - run the pytest suite"

venv:
	python3 -m venv .venv && .venv/bin/pip install --upgrade pip

install:
	@if [ -x .venv/bin/pip ]; then .venv/bin/pip install -r requirements.txt; else pip3 install -r requirements.txt --break-system-packages; fi

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down

etl:
	.venv/bin/python -m ml_services.etl.run_all

kg-build:
	.venv/bin/python -m ml_services.etl.kg_build

api:
	.venv/bin/uvicorn backend.app.main:app --reload --port 8000

demo:
	.venv/bin/python scripts/run_demo.py

tests:
	.venv/bin/python -m pytest -q

lint:
	.venv/bin/python -m compileall -q backend ml_services scripts
