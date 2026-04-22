set shell := ["bash", "-cu"]

appsignals_template := "deployments/appsignals/template.yaml"
appsignals_config := "deployments/appsignals/samconfig.toml"
otel_template := "deployments/otel/template.yaml"
otel_config := "deployments/otel/samconfig.toml"
aws_region := env_var_or_default("AWS_REGION", "us-east-1")
stack_name_appsignals := env_var_or_default("STACK_NAME_APPSIGNALS", "adot-serverless-demo-appsignals")
stack_name_otel := env_var_or_default("STACK_NAME_OTEL", "adot-serverless-demo-otel")

default:
    @just --list

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
    @echo "Use 'just smoke-appsignals' or 'just smoke-otel'."

smoke-appsignals stack_name=stack_name_appsignals region=aws_region:
    ./scripts/smoke-test.sh {{stack_name}} {{region}}

smoke-otel stack_name=stack_name_otel region=aws_region:
    ./scripts/smoke-test.sh {{stack_name}} {{region}}

check-adot-layers: check-adot-layers-appsignals check-adot-layers-otel

check-adot-layers-appsignals region=aws_region:
    python3 scripts/check_adot_layers.py --template {{appsignals_template}} --samconfig {{appsignals_config}} --region {{region}}

check-adot-layers-otel region=aws_region:
    python3 scripts/check_adot_layers.py --template {{otel_template}} --samconfig {{otel_config}} --region {{region}}

update-adot-layers: update-adot-layers-appsignals update-adot-layers-otel

update-adot-layers-appsignals region=aws_region:
    python3 scripts/check_adot_layers.py --template {{appsignals_template}} --samconfig {{appsignals_config}} --region {{region}} --write-files

update-adot-layers-otel region=aws_region:
    python3 scripts/check_adot_layers.py --template {{otel_template}} --samconfig {{otel_config}} --region {{region}} --write-files
