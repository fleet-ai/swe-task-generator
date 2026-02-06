"""
Unit tests for the task generation pipeline.

Run with: pytest tests/test_pipeline.py -v
"""

import pytest
from pathlib import Path
from unittest.mock import Mock, patch

from src.utils import (
    sanitize_instance_id,
    extract_test_files,
    detect_language,
)
from src.task_generator import TaskGenerator
from src.dockerfile_generator import DockerfileGenerator
from src.agentic_builder import AgenticEnvironmentBuilder


class TestUtils:
    """Test utility functions"""

    def test_sanitize_instance_id(self):
        assert sanitize_instance_id("psf/requests", 6234) == "psf-requests-6234"
        assert sanitize_instance_id("django/django", 123) == "django-django-123"

    def test_extract_test_files(self):
        files = [
            "src/main.py",
            "tests/test_main.py",
            "test_utils.py",
            "src/test/test_api.py",
        ]
        test_files = extract_test_files(files)
        assert "tests/test_main.py" in test_files
        assert "test_utils.py" in test_files
        assert "src/test/test_api.py" in test_files
        assert "src/main.py" not in test_files


class TestTaskGenerator:
    """Test task generator"""

    @pytest.fixture
    def task_generator(self):
        return TaskGenerator(dockerhub_username="testuser")

    @pytest.fixture
    def mock_pr_data(self):
        return {
            "repo": "psf/requests",
            "pr_number": 6234,
            "title": "Fix timeout bug",
            "body": "This PR fixes a timeout issue",
            "base_commit": "abc123",
            "head_commit": "def456",
            "changed_files": ["requests/api.py", "tests/test_api.py"],
            "diff": "diff --git a/requests/api.py...",
            "issue": None,
            "merged": True,
            "created_at": "2023-10-15T12:34:56Z",
        }

    def test_create_problem_statement(self, task_generator, mock_pr_data):
        statement = task_generator._create_problem_statement(mock_pr_data)
        assert "Fix timeout bug" in statement
        assert "This PR fixes a timeout issue" in statement
        assert "requests/api.py" in statement

    def test_validate_task_valid(self, task_generator):
        task_data = {
            "instance_id": "test-123",
            "repo": "owner/repo",
            "base_commit": "abc123",
            "problem_statement": "Test problem",
            "gold_patch": "diff...",
            "image_name": "user/image:latest",
            "eval_script": "#!/bin/bash\ntest",
        }
        assert task_generator.validate_task(task_data) is True

    def test_validate_task_invalid(self, task_generator):
        task_data = {"instance_id": "test-123"}
        assert task_generator.validate_task(task_data) is False


class TestDockerfileGenerator:
    """Test Dockerfile generator"""

    @pytest.fixture
    def dockerfile_generator(self):
        return DockerfileGenerator()

    @pytest.fixture
    def mock_pr_data(self):
        return {
            "repo": "psf/requests",
            "pr_number": 6234,
            "base_commit": "abc123",
            "changed_files": ["requests/api.py", "tests/test_api.py"],
        }

    def test_detect_language_python(self, dockerfile_generator):
        assert dockerfile_generator._detect_language_from_files(["main.py"]) == "python"

    def test_detect_language_javascript(self, dockerfile_generator):
        assert dockerfile_generator._detect_language_from_files(["index.js"]) == "javascript"

    def test_generate_python_dockerfile(self, dockerfile_generator, mock_pr_data):
        content = dockerfile_generator._generate_python_dockerfile(
            mock_pr_data, "python:3.11-slim"
        )
        assert "FROM python:3.11-slim" in content
        assert "git clone https://github.com/psf/requests.git" in content
        assert "git checkout abc123" in content
        assert "pip install" in content


class TestAgenticBuilder:
    """Test agentic builder patch separation"""

    def test_separate_patches_basic(self):
        """Test that patch separation splits test and fix files correctly"""
        builder = AgenticEnvironmentBuilder.__new__(AgenticEnvironmentBuilder)

        pr_data = {
            "diff": (
                "diff --git a/src/main.py b/src/main.py\n"
                "--- a/src/main.py\n"
                "+++ b/src/main.py\n"
                "@@ -1,3 +1,4 @@\n"
                " def foo():\n"
                "+    return 42\n"
                "diff --git a/tests/test_main.py b/tests/test_main.py\n"
                "--- a/tests/test_main.py\n"
                "+++ b/tests/test_main.py\n"
                "@@ -1,3 +1,6 @@\n"
                " def test_foo():\n"
                "+    assert foo() == 42\n"
            ),
        }

        test_patch, fix_patch = builder.separate_patches(pr_data)

        assert test_patch is not None
        assert fix_patch is not None
        assert "tests/test_main.py" in test_patch
        assert "src/main.py" in fix_patch

    def test_separate_patches_no_tests(self):
        """Test that PRs without test files return None"""
        builder = AgenticEnvironmentBuilder.__new__(AgenticEnvironmentBuilder)

        pr_data = {
            "diff": (
                "diff --git a/README.md b/README.md\n"
                "--- a/README.md\n"
                "+++ b/README.md\n"
                "@@ -1 +1,2 @@\n"
                "+New line\n"
            ),
        }

        test_patch, fix_patch = builder.separate_patches(pr_data)
        assert test_patch is None

    def test_detect_hacking(self):
        """Test that hacking detection catches grep-only scripts"""
        builder = AgenticEnvironmentBuilder.__new__(AgenticEnvironmentBuilder)

        # Hacking script (no test runner)
        hacking = "#!/bin/bash\nset -e\ngrep 'def foo' src/main.py\nif grep -q 'return 42' src/main.py; then exit 0; else exit 1; fi"
        assert builder._detect_hacking(hacking) is True

        # Legitimate script (has pytest)
        legit = "#!/bin/bash\nset -e\npip install -e .\npytest tests/test_main.py -xvs"
        assert builder._detect_hacking(legit) is False


class TestIntegration:
    """Integration tests with mocked components"""

    def test_task_directory_structure(self, tmp_path):
        """Test that generated task has correct file structure"""
        task_generator = TaskGenerator(dockerhub_username="testuser")
        dockerfile_generator = DockerfileGenerator()

        pr_data = {
            "repo": "test/repo",
            "pr_number": 123,
            "title": "Test PR",
            "body": "Test description",
            "base_commit": "abc123",
            "head_commit": "def456",
            "changed_files": ["src/main.py", "tests/test_main.py"],
            "diff": "diff --git a/src/main.py...",
            "issue": None,
            "merged": True,
            "created_at": "2023-10-15T12:34:56Z",
        }

        task_dir = tmp_path / "task_001"
        task_dir.mkdir()

        # Generate Dockerfile
        dockerfile_generator.generate_dockerfile(pr_data, task_dir)

        # Write eval_script.sh (normally agent-generated)
        eval_content = "#!/bin/bash\nset -e\npytest tests/ -xvs"
        (task_dir / "eval_script.sh").write_text(eval_content)

        # Generate task.json
        task_data = task_generator.generate_task_json(pr_data, task_dir, eval_content)

        # Verify structure
        assert (task_dir / "Dockerfile").exists()
        assert (task_dir / "eval_script.sh").exists()
        assert (task_dir / "task.json").exists()
        assert task_data["instance_id"] == "test-repo-123"
        assert task_data["repo"] == "test/repo"
        assert task_data["eval_script"] == eval_content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
