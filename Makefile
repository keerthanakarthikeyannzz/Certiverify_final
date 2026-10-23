# ==============================================================================
# CertiVerify Enterprise - Dev Automation Makefile
# ==============================================================================

.PHONY: help dev backend frontend test-backend

help:
	@echo "Available commands:"
	@echo "  make dev         - Launch backend, wait for /health, then launch frontend"
	@echo "  make backend     - Run backend standalone"
	@echo "  make frontend    - Run frontend standalone"
	@echo "  make test-backend- Run backend test suite"

dev:
	@bash scripts/dev.sh

backend:
	@cd backend && .venv/bin/uvicorn app.main:app --host $${HOST:-127.0.0.1} --port $${PORT:-8000} --reload --reload-dir app --reload-exclude "uploads/*" --reload-exclude "data/*" --reload-exclude "*.log" --reload-exclude "*.db*" --reload-exclude "scripts/*"

frontend:
	@cd frontend && npm run dev

test-backend:
	@cd backend && .venv/bin/pytest
