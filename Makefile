.PHONY: test test-node test-python build-appsignals build-otel smoke smoke-appsignals smoke-otel \
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

test-python:
	python3 -m unittest discover -s tests/python -v

build-appsignals:
	cd deployments/appsignals && sam build -t template.yaml --config-file samconfig.toml

build-otel:
	cd deployments/otel && sam build -t template.yaml --config-file samconfig.toml

smoke:
	@echo "Use 'make smoke-appsignals' or 'make smoke-otel'."

smoke-appsignals:
	./scripts/smoke-test.sh $(STACK_NAME_APPSIGNALS) $(AWS_REGION)

smoke-otel:
	./scripts/smoke-test.sh $(STACK_NAME_OTEL) $(AWS_REGION)

check-adot-layers: check-adot-layers-appsignals check-adot-layers-otel

check-adot-layers-appsignals:
	python3 scripts/check_adot_layers.py --template $(APPSIGNALS_TEMPLATE) --samconfig $(APPSIGNALS_CONFIG) --region $(AWS_REGION)

check-adot-layers-otel:
	python3 scripts/check_adot_layers.py --template $(OTEL_TEMPLATE) --samconfig $(OTEL_CONFIG) --region $(AWS_REGION)

update-adot-layers: update-adot-layers-appsignals update-adot-layers-otel

update-adot-layers-appsignals:
	python3 scripts/check_adot_layers.py --template $(APPSIGNALS_TEMPLATE) --samconfig $(APPSIGNALS_CONFIG) --region $(AWS_REGION) --write-files

update-adot-layers-otel:
	python3 scripts/check_adot_layers.py --template $(OTEL_TEMPLATE) --samconfig $(OTEL_CONFIG) --region $(AWS_REGION) --write-files
