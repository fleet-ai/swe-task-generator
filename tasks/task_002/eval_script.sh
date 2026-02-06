#!/bin/bash
set -e

# Set PYTHONPATH to include src directory
export PYTHONPATH=src:$PYTHONPATH

# Install project with test dependencies
pip install -e ".[tests]" 2>/dev/null || pip install -e ".[dev]" 2>/dev/null || pip install -e . 2>/dev/null || true
pip install pytest simplejson 2>/dev/null || true

# Run the specific test that was modified in the patch
pytest tests/test_validate.py::test_url_accepts_valid_file_urls -xvs