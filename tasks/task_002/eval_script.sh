#!/bin/bash
set -e

# Set PYTHONPATH to include src directory
export PYTHONPATH=src:$PYTHONPATH

# Install pytest if not available
pip install pytest 2>/dev/null || true

# Run the specific test that was modified in the patch
pytest tests/test_validate.py::test_url_accepts_valid_file_urls -xvs