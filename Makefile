.PHONY: test test-node test-python smoke check-adot-layers update-adot-layers

test: test-node test-python

test-node:
	npm test --prefix src/node-api

test-python:
	python3 -m unittest discover -s tests/python -v

smoke:
	./scripts/smoke-test.sh $(STACK_NAME) $(AWS_REGION)

check-adot-layers:
	python3 scripts/check_adot_layers.py

update-adot-layers:
	python3 scripts/check_adot_layers.py --write-files
