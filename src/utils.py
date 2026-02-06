"""Utility functions for the task generation pipeline"""

import os
import json
import logging
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def setup_output_directory(output_dir: Path, task_id: str) -> Path:
    """
    Create output directory for a task instance.
    
    Args:
        output_dir: Base output directory
        task_id: Task identifier
        
    Returns:
        Path to the task directory
    """
    task_dir = output_dir / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


def save_json(data: Dict[str, Any], filepath: Path) -> None:
    """
    Save dictionary to JSON file.
    
    Args:
        data: Dictionary to save
        filepath: Path to output file
    """
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved JSON to {filepath}")


def load_json(filepath: Path) -> Dict[str, Any]:
    """
    Load JSON file.
    
    Args:
        filepath: Path to JSON file
        
    Returns:
        Dictionary from JSON
    """
    with open(filepath, 'r') as f:
        return json.load(f)


def run_command(cmd: List[str], cwd: Optional[Path] = None, 
                capture_output: bool = True) -> subprocess.CompletedProcess:
    """
    Run a shell command.
    
    Args:
        cmd: Command and arguments as list
        cwd: Working directory
        capture_output: Whether to capture stdout/stderr
        
    Returns:
        CompletedProcess object
    """
    logger.info(f"Running command: {' '.join(cmd)}")
    result = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=capture_output,
        text=True
    )
    if result.returncode != 0:
        logger.error(f"Command failed with code {result.returncode}")
        if capture_output:
            logger.error(f"stderr: {result.stderr}")
    return result


def get_github_token() -> Optional[str]:
    """
    Get GitHub token from environment.
    
    Returns:
        GitHub token or None
    """
    token = os.environ.get('GITHUB_TOKEN')
    if not token:
        logger.warning("GITHUB_TOKEN not set. API rate limits will be restrictive.")
    return token


def detect_language(repo_path: Path) -> str:
    """
    Detect primary language of repository.
    
    Args:
        repo_path: Path to repository
        
    Returns:
        Language name (python, javascript, java, etc.)
    """
    # Simple heuristic based on common files
    if (repo_path / "setup.py").exists() or (repo_path / "pyproject.toml").exists():
        return "python"
    elif (repo_path / "package.json").exists():
        return "javascript"
    elif (repo_path / "pom.xml").exists():
        return "java"
    elif (repo_path / "go.mod").exists():
        return "go"
    elif (repo_path / "Cargo.toml").exists():
        return "rust"
    else:
        return "unknown"


def detect_test_framework(repo_path: Path, language: str) -> str:
    """
    Detect test framework used in repository.
    
    Args:
        repo_path: Path to repository
        language: Programming language
        
    Returns:
        Test framework name
    """
    if language == "python":
        if (repo_path / "pytest.ini").exists() or (repo_path / "pyproject.toml").exists():
            return "pytest"
        elif (repo_path / "setup.cfg").exists():
            # Check for unittest or nose
            return "unittest"
        else:
            return "pytest"  # Default for Python
    elif language == "javascript":
        package_json = repo_path / "package.json"
        if package_json.exists():
            with open(package_json) as f:
                data = json.load(f)
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if "jest" in deps:
                    return "jest"
                elif "mocha" in deps:
                    return "mocha"
        return "npm test"
    elif language == "java":
        return "maven"
    elif language == "go":
        return "go test"
    else:
        return "unknown"


def extract_test_files(changed_files: List[str]) -> List[str]:
    """
    Extract test files from list of changed files.
    
    Args:
        changed_files: List of file paths
        
    Returns:
        List of test file paths
    """
    test_patterns = [
        'test_', '_test.', '/test/', '/tests/',
        'spec.', '.spec.', '__test__'
    ]
    
    test_files = []
    for file in changed_files:
        if any(pattern in file.lower() for pattern in test_patterns):
            test_files.append(file)
    
    return test_files


def sanitize_instance_id(repo: str, pr_number: int) -> str:
    """
    Create sanitized instance ID from repo and PR number.
    
    Args:
        repo: Repository name (owner/repo)
        pr_number: PR number
        
    Returns:
        Sanitized instance ID
    """
    repo_name = repo.replace('/', '-')
    return f"{repo_name}-{pr_number}"
