.PHONY: install-deps lint test clean archive

install-deps:
	poetry install

lint:
	poetry run ruff check src tests
	poetry run ruff format --check src tests

test:
	poetry run pytest

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .venv dist

archive:
	git archive --format=zip --output=../$(notdir $(CURDIR)).zip HEAD
