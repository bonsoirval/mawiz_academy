SHELL := /bin/sh
PYTHON ?= python3
PIP ?= $(PYTHON) -m pip
FLASK_APP ?= run.py

.PHONY: help install dev init-db seed reset-db create-admin run test coverage compile security security-audit intrusion-detection strip-comments docker-up docker-down show-dev-mail clean

help:
	@printf '%s\n' 'Mawiz Academy administration:'
	@printf '%s\n' '  make install       Install Python dependencies'
	@printf '%s\n' '  make dev           Create .env from example if missing'
	@printf '%s\n' '  make init-db       Create database tables'
	@printf '%s\n' '  make seed          Load Mawiz demo data and permissions'
	@printf '%s\n' '  make reset-db      Delete local SQLite database and recreate it'
	@printf '%s\n' '  make run           Start development server'
	@printf '%s\n' '  make test          Run test suite'
	@printf '%s\n' '  make coverage      Run tests with coverage'
	@printf '%s\n' '  make compile       Compile-check Python sources'
	@printf '%s\n' '  make create-admin  Create an administrator account securely (EMAIL optional)' 
	@printf '%s\n' '  make security-audit Run static security and secret-hygiene audit'
	@printf '%s\n' '  make intrusion-detection Inspect recent failed-auth activity'
	@printf '%s\n' '  make security      Compile-check + run security/auth tests'
	@printf '%s\n' '  make strip-comments OUTPUT=/path  Create a deployable copy without Python comments'
	@printf '%s\n' '  make docker-up     Start PostgreSQL + app services'
	@printf '%s\n' '  make docker-down   Stop services'
	@printf '%s\n' '  make show-dev-mail Show local development verification/reset links'

install:
	$(PIP) install -r requirements.txt

dev:
	@test -f .env || cp .env.example .env
	@echo 'Development environment ready. Review .env before running.'

init-db:
	$(PYTHON) run.py --init-db

seed:
	$(PYTHON) run.py --seed

reset-db:
	@mkdir -p instance
	@rm -f instance/mawiz.db
	@$(MAKE) init-db
	@$(MAKE) seed

run:
	$(PYTHON) run.py

test:
	$(PYTHON) -m pytest -q

coverage:
	$(PYTHON) -m pytest --cov=app --cov-report=term-missing

compile:
	$(PYTHON) -m compileall -q app run.py

create-admin:
	PYTHONPATH=. $(PYTHON) scripts/create_admin.py $(if $(EMAIL),--email "$(EMAIL)",) $(if $(FIRST_NAME),--first-name "$(FIRST_NAME)",) $(if $(LAST_NAME),--last-name "$(LAST_NAME)",)

security-audit:
	$(PYTHON) scripts/security_audit.py

intrusion-detection:
	PYTHONPATH=. $(PYTHON) scripts/intrusion_detection.py $(if $(MINUTES),--minutes $(MINUTES),) $(if $(THRESHOLD),--threshold $(THRESHOLD),)

security: compile test security-audit intrusion-detection
	@echo 'Security checks completed.'

strip-comments:
	@test -n "$(OUTPUT)" || (echo 'Set OUTPUT to a new deployment directory.'; exit 2)
	$(PYTHON) scripts/strip_comments.py --source . --output "$(OUTPUT)"

docker-up:
	docker compose up --build -d

docker-down:
	docker compose down

show-dev-mail:
	$(PYTHON) run.py --show-dev-mail

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete
