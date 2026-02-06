#!/bin/bash
set -e
pip install -e ".[tests]" 2>/dev/null || pip install -e . 2>/dev/null || true
pytest tests/test_deserialization.py::TestFieldDeserialization::test_constant_none_allows_none_value -xvs