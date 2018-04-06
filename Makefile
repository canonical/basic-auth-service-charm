CHARM_NAME = basic-auth-service
CHARM_SERIES = xenial
CHARM_OUTPUT = build/charm-output
RENDERED_CHARM_DIR = $(CHARM_OUTPUT)/$(CHARM_SERIES)/$(CHARM_NAME)
CHARM_URI = cs:~landscape/$(CHARM_NAME)


.PHONY: help
help: ## Print help about available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.PHONY: build
build: ## Install build dependencies and build the charm
	./dev/ubuntu-deps
	$(MAKE) charm-build

interfaces/interface-pgsql:
	git clone --quiet git://git.launchpad.net/interface-pgsql interfaces/interface-pgsql
	cd interfaces/interface-pgsql && git checkout --quiet --force v1.1.3

.PHONY: charm-build
charm-build: REV_HASH = $(shell git rev-parse HEAD)
charm-build: interfaces/interface-pgsql ## Build the charm
	rm -rf $(CHARM_OUTPUT)
	ls -1	basic-auth-service_*.snap >/dev/null
	INTERFACE_PATH=interfaces charm build -s $(CHARM_SERIES) -o $(CHARM_OUTPUT)
	echo "commit-sha-1: $(REV_HASH)" > $(RENDERED_CHARM_DIR)/repo-info

.PHONY: charm-push
charm-push: charm-build ## Push the charm to the store and release it in the edge channel
	./release-charm $(RENDERED_CHARM_DIR) $(CHARM_URI)

.DEFAULT_GOAL := help
