.PHONY: test test-node test-python require-python build-appsignals build-otel smoke smoke-appsignals smoke-otel \
	check-adot-layers check-adot-layers-appsignals check-adot-layers-otel \
	update-adot-layers update-adot-layers-appsignals update-adot-layers-otel

APPSIGNALS_TEMPLATE := deployments/appsignals/template.yaml
APPSIGNALS_CONFIG := deployments/appsignals/samconfig.toml
OTEL_TEMPLATE := deployments/otel/template.yaml
OTEL_CONFIG := deployments/otel/samconfig.toml
AWS_REGION ?= us-east-1
STACK_NAME_APPSIGNALS ?= adot-serverless-demo-appsignals
STACK_NAME_OTEL ?= adot-serverless-demo-otel

test: test-node test-python

test-node:
	npm test --prefix src/node-api

require-python:
	@python3 -c 'import sys; version = sys.version_info[:3]; min_version = (3, 12, 0); sys.exit(f"Python 3.12+ is required for local repo commands; found {sys.version.split()[0]}") if version < min_version else None'

test-python: require-python
	python3 -m unittest discover -s tests/python -v

build-appsignals:
	cd deployments/appsignals && sam build -t template.yaml --config-file samconfig.toml

build-otel:
	cd deployments/otel && sam build -t template.yaml --config-file samconfig.toml

smoke:
	@echo "Use 'make smoke-appsignals' or 'make smoke-otel'."

smoke-appsignals: require-python
	./scripts/smoke-test.sh $(STACK_NAME_APPSIGNALS) $(AWS_REGION)

smoke-otel: require-python
	./scripts/smoke-test.sh $(STACK_NAME_OTEL) $(AWS_REGION)

check-adot-layers: check-adot-layers-appsignals check-adot-layers-otel

check-adot-layers-appsignals: require-python
	python3 scripts/check_adot_layers.py --template $(APPSIGNALS_TEMPLATE) --samconfig $(APPSIGNALS_CONFIG) --region $(AWS_REGION)

check-adot-layers-otel: require-python
	python3 scripts/check_adot_layers.py --template $(OTEL_TEMPLATE) --samconfig $(OTEL_CONFIG) --region $(AWS_REGION)

update-adot-layers: update-adot-layers-appsignals update-adot-layers-otel

update-adot-layers-appsignals: require-python
	python3 scripts/check_adot_layers.py --template $(APPSIGNALS_TEMPLATE) --samconfig $(APPSIGNALS_CONFIG) --region $(AWS_REGION) --write-files

update-adot-layers-otel: require-python
	python3 scripts/check_adot_layers.py --template $(OTEL_TEMPLATE) --samconfig $(OTEL_CONFIG) --region $(AWS_REGION) --write-files
