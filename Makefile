# DocuFlow Makefile
# Simplifies common Docker operations

.PHONY: help build up down restart logs shell test clean backup

help: ## Show this help message
	@echo "DocuFlow Docker Commands:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Build all Docker images
	docker-compose build

up: ## Start all services in detached mode
	docker-compose up -d
	@echo "✅ Services started. Access at http://localhost"
	@echo "   Frontend: http://localhost"
	@echo "   API Docs: http://localhost/docs"
	@echo "   Logs: make logs"

down: ## Stop all services
	docker-compose down

restart: ## Restart all services
	docker-compose restart

logs: ## View logs from all services
	docker-compose logs -f

logs-backend: ## View backend logs only
	docker-compose logs -f backend

logs-db: ## View database logs only
	docker-compose logs -f db

shell: ## Open shell in backend container
	docker-compose exec backend /bin/sh

shell-db: ## Open PostgreSQL shell
	docker-compose exec db psql -U docuflow docuflow

test: ## Run tests in backend container
	docker-compose exec backend pytest

test-coverage: ## Run tests with coverage report
	docker-compose exec backend pytest --cov=backend --cov-report=html

ps: ## Show running containers
	docker-compose ps

stats: ## Show resource usage
	docker stats --no-stream

clean: ## Remove all containers and volumes (CAUTION: deletes data)
	docker-compose down -v
	docker system prune -f

backup: ## Backup database to ./backups/
	@mkdir -p backups
	docker-compose exec -T db pg_dump -U docuflow docuflow > backups/backup_$$(date +%Y%m%d_%H%M%S).sql
	@echo "✅ Backup created in ./backups/"

restore: ## Restore database from backup (usage: make restore FILE=backups/backup_20250119.sql)
	@if [ -z "$(FILE)" ]; then \
		echo "❌ Please specify backup file: make restore FILE=backups/backup_20250119.sql"; \
		exit 1; \
	fi
	docker-compose exec -T db psql -U docuflow docuflow < $(FILE)
	@echo "✅ Database restored from $(FILE)"

prod-up: ## Start with production configuration
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

prod-down: ## Stop production configuration
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml down

scale: ## Scale backend (usage: make scale N=3)
	@if [ -z "$(N)" ]; then \
		echo "❌ Please specify number of instances: make scale N=3"; \
		exit 1; \
	fi
	docker-compose up -d --scale backend=$(N)

health: ## Check health of all services
	@echo "Checking backend health..."
	@curl -f http://localhost/health && echo "✅ Backend healthy" || echo "❌ Backend unhealthy"
	@echo ""
	@echo "Checking database health..."
	@docker-compose exec db pg_isready -U docuflow && echo "✅ Database healthy" || echo "❌ Database unhealthy"
	@echo ""
	@echo "Checking Redis health..."
	@docker-compose exec redis redis-cli ping && echo "✅ Redis healthy" || echo "❌ Redis unhealthy"

migrate: ## Run database migrations
	docker-compose exec backend python -c "from backend.database import init_db; init_db()"

seed: ## Seed database with test data
	docker-compose exec backend python backend/migrations/seed_test_data.py

env: ## Generate encryption key and show in .env format
	@echo "# Add this to your .env file:"
	@echo "ENCRYPTION_KEY=$$(openssl rand -base64 32)"

install: ## First-time setup (build, start, migrate)
	@echo "🚀 Setting up DocuFlow..."
	@make build
	@make up
	@sleep 5
	@make migrate
	@echo "✅ DocuFlow is ready! Access at http://localhost"

update: ## Update to latest version (pull, rebuild, restart)
	@echo "📦 Updating DocuFlow..."
	git pull origin main
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
	@echo "✅ Update complete!"
