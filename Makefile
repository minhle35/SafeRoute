.PHONY: ports up down restart logs

# Find free host ports (within 50 of each default) and write them into .env
ports:
	./scripts/find_ports.sh

# Stop first so this stack's own containers don't get mistaken for a port
# conflict by find_ports.sh, then assign free ports and start fresh
up:
	docker compose down
	$(MAKE) ports
	docker compose up -d --build

down:
	docker compose down

# Re-resolve ports and recreate containers — use after editing .env or code
restart: up

logs:
	docker compose logs -f
