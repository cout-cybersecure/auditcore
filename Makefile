.DEFAULT_GOAL := help

COMPOSE := docker compose -f deploy/docker-compose/docker-compose.yml
INGESTION_DIR := services/ingestion-api

.PHONY: help
help: ## list targets
	@awk 'BEGIN{FS=":.*##"} /^[a-zA-Z_-]+:.*##/ {printf "  %-22s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---------------------------------------------------------------------------
# Dev infrastructure
# ---------------------------------------------------------------------------

.PHONY: infra-up
infra-up: ## start Postgres + MinIO
	$(COMPOSE) up -d

.PHONY: infra-down
infra-down: ## stop dev infrastructure (keeps volumes)
	$(COMPOSE) down

.PHONY: infra-nuke
infra-nuke: ## stop and delete all dev data
	$(COMPOSE) down -v

.PHONY: infra-logs
infra-logs: ## tail dev infrastructure logs
	$(COMPOSE) logs -f

.PHONY: psql
psql: ## open psql against the dev DB
	$(COMPOSE) exec postgres psql -U auditcore -d auditcore

# ---------------------------------------------------------------------------
# Ingestion API
# ---------------------------------------------------------------------------

.PHONY: api-install
api-install: ## install ingestion-api deps (uses uv if present, falls back to pip)
	@cd $(INGESTION_DIR) && ( \
		command -v uv >/dev/null && uv sync --extra dev \
		|| ( python3 -m venv .venv && .venv/bin/pip install -e '.[dev]' \
		     -e ../../packages/models-py ) \
	)

.PHONY: api-run
api-run: ## run ingestion-api on :8000
	@cd $(INGESTION_DIR) && ( \
		[ -d .venv ] && .venv/bin/uvicorn auditcore_ingestion.main:app --reload --port 8000 \
		|| uv run uvicorn auditcore_ingestion.main:app --reload --port 8000 \
	)

.PHONY: api-test
api-test: ## run ingestion-api tests
	@cd $(INGESTION_DIR) && ( \
		[ -d .venv ] && .venv/bin/pytest -v \
		|| uv run pytest -v \
	)

# ---------------------------------------------------------------------------
# Collector
# ---------------------------------------------------------------------------

.PHONY: collector-build
collector-build: ## build the Go collector binary
	cd collector && go build -o ../bin/auditor-collect ./cmd/auditor-collect

.PHONY: collector-test
collector-test: ## run Go tests
	cd collector && go test ./...

.PHONY: collector-list
collector-list: collector-build ## list allowlisted tools
	./bin/auditor-collect list-tools

# ---------------------------------------------------------------------------
# C++ hwprobe (collector-side native probe)
# ---------------------------------------------------------------------------

HWPROBE_BUILD := collector/hwprobe/build

.PHONY: hwprobe-build
hwprobe-build: ## build the C++ hwprobe binary
	cmake -S collector/hwprobe -B $(HWPROBE_BUILD) -DCMAKE_BUILD_TYPE=Release
	cmake --build $(HWPROBE_BUILD) -j
	mkdir -p bin && cp $(HWPROBE_BUILD)/hwprobe bin/hwprobe

.PHONY: hwprobe-run
hwprobe-run: hwprobe-build ## emit a hwprobe JSON document
	./bin/hwprobe

# ---------------------------------------------------------------------------
# Rust normalizer-worker
# ---------------------------------------------------------------------------

NORMALIZER_DIR := services/normalizer-worker

.PHONY: normalizer-build
normalizer-build: ## build the Rust normalizer-worker (debug)
	cd $(NORMALIZER_DIR) && cargo build

.PHONY: normalizer-release
normalizer-release: ## build the Rust normalizer-worker (release)
	cd $(NORMALIZER_DIR) && cargo build --release

.PHONY: normalizer-test
normalizer-test: ## run normalizer-worker unit tests (no DB needed)
	cd $(NORMALIZER_DIR) && cargo test

.PHONY: normalizer-run
normalizer-run: ## run the normalizer-worker against local infra
	cd $(NORMALIZER_DIR) && cargo run

# ---------------------------------------------------------------------------
# End-to-end smoke
# ---------------------------------------------------------------------------

.PHONY: e2e-smoke
e2e-smoke: collector-build hwprobe-build ## run collector against local ingestion-api
	./bin/auditor-collect run --upload http://localhost:8000
