.PHONY: dev prod down logs build

dev:
	mkdir -p data
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up

prod:
	mkdir -p data
	docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose -f docker-compose.yml -f docker-compose.dev.yml build
