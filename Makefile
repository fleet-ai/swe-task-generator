.PHONY: install test lint clean help

help:
	@echo "SWE-Universe Task Generator"
	@echo ""
	@echo "  install     Install dependencies"
	@echo "  test        Run tests"
	@echo "  lint        Run linters"
	@echo "  clean       Remove generated files"

install:
	pip install -r requirements.txt

test:
	pytest tests/ -v

lint:
	flake8 src/ tests/ --max-line-length=100
	black --check src/ tests/

format:
	black src/ tests/

clean:
	rm -rf tasks/
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .coverage htmlcov/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -f task_generation.log
