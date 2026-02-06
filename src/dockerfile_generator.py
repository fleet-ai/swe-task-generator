"""Dockerfile generator with layered architecture"""

import logging
from typing import Dict, Any, Optional
from pathlib import Path
from jinja2 import Template

from .utils import detect_language, detect_test_framework

logger = logging.getLogger(__name__)


class DockerfileGenerator:
    """Generates Dockerfiles with layered architecture for task instances"""
    
    # Base image templates for different languages
    BASE_IMAGES = {
        'python': 'python:3.11-slim',
        'javascript': 'node:18-slim',
        'java': 'openjdk:17-slim',
        'go': 'golang:1.21-alpine',
        'rust': 'rust:1.75-slim',
    }
    
    def __init__(self):
        """Initialize Dockerfile generator"""
        pass
    
    def generate_dockerfile(
        self,
        pr_data: Dict[str, Any],
        output_dir: Path,
        language: Optional[str] = None
    ) -> str:
        """
        Generate Dockerfile for task instance.
        
        Args:
            pr_data: PR data from GitHub
            output_dir: Output directory for Dockerfile
            language: Programming language (auto-detected if None)
            
        Returns:
            Path to generated Dockerfile
        """
        # Detect language if not provided
        if not language:
            language = self._detect_language_from_files(pr_data['changed_files'])
        
        logger.info(f"Generating Dockerfile for {language} project")
        
        # Get base image
        base_image = self.BASE_IMAGES.get(language, 'ubuntu:22.04')
        
        # Generate Dockerfile content based on language
        if language == 'python':
            dockerfile_content = self._generate_python_dockerfile(pr_data, base_image)
        elif language == 'javascript':
            dockerfile_content = self._generate_javascript_dockerfile(pr_data, base_image)
        elif language == 'java':
            dockerfile_content = self._generate_java_dockerfile(pr_data, base_image)
        elif language == 'go':
            dockerfile_content = self._generate_go_dockerfile(pr_data, base_image)
        else:
            dockerfile_content = self._generate_generic_dockerfile(pr_data, base_image)
        
        # Save Dockerfile
        dockerfile_path = output_dir / "Dockerfile"
        with open(dockerfile_path, 'w') as f:
            f.write(dockerfile_content)
        
        logger.info(f"Generated Dockerfile at {dockerfile_path}")
        return str(dockerfile_path)
    
    def _detect_language_from_files(self, changed_files: list) -> str:
        """
        Detect language from changed files.
        
        Args:
            changed_files: List of file paths
            
        Returns:
            Language name
        """
        extensions = {
            '.py': 'python',
            '.js': 'javascript',
            '.ts': 'javascript',
            '.jsx': 'javascript',
            '.tsx': 'javascript',
            '.java': 'java',
            '.go': 'go',
            '.rs': 'rust',
            '.rst': None,  # ReStructuredText docs - check repo for language
            '.md': None,   # Markdown docs - check repo for language
        }
        
        # Check changed files for language indicators
        for file in changed_files:
            for ext, lang in extensions.items():
                if file.endswith(ext) and lang is not None:
                    return lang
        
        # If only docs were changed, try to detect from repo structure
        # Common indicator files
        if any(f.endswith(('.rst', '.md', 'docs/')) for f in changed_files):
            # This is likely a docs change, return 'unknown' to use generic template
            # The generic template will auto-detect from repo
            logger.info("Documentation-only change detected, will auto-detect language from repository")
        
        return 'unknown'
    
    def _generate_python_dockerfile(self, pr_data: Dict[str, Any], base_image: str) -> str:
        """Generate Dockerfile for Python projects"""
        
        template = Template('''# SWE-Universe Task Instance Dockerfile
# Repository: {{ repo }}
# Base Commit: {{ base_commit }}
# PR: #{{ pr_number }}

# Layer 1: Base Image
FROM {{ base_image }} AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    git \\
    build-essential \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Environment Setup
FROM base AS environment

WORKDIR /workspace

# Clone repository at base commit
RUN git clone https://github.com/{{ repo }}.git . && \\
    git checkout {{ base_commit }}

# Install Python dependencies
RUN if [ -f requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi
RUN if [ -f dev-requirements.txt ]; then pip install --no-cache-dir -r dev-requirements.txt; fi
RUN if [ -f setup.py ]; then pip install --no-cache-dir -e .; fi
RUN if [ -f pyproject.toml ]; then pip install --no-cache-dir -e .; fi

# Install common test dependencies
RUN pip install --no-cache-dir pytest pytest-cov pytest-xdist tox

# Layer 3: Instance Setup
FROM environment AS instance

# Set environment variables
ENV PYTHONPATH=/workspace
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Copy evaluation script
COPY eval_script.sh /eval_script.sh
RUN chmod +x /eval_script.sh

# Default command
CMD ["/bin/bash"]
''')
        
        return template.render(
            repo=pr_data['repo'],
            base_commit=pr_data['base_commit'],
            pr_number=pr_data['pr_number'],
            base_image=base_image,
        )
    
    def _generate_javascript_dockerfile(self, pr_data: Dict[str, Any], base_image: str) -> str:
        """Generate Dockerfile for JavaScript/TypeScript projects"""
        
        template = Template('''# SWE-Universe Task Instance Dockerfile
# Repository: {{ repo }}
# Base Commit: {{ base_commit }}
# PR: #{{ pr_number }}

# Layer 1: Base Image
FROM {{ base_image }} AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    git \\
    curl \\
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Environment Setup
FROM base AS environment

WORKDIR /workspace

# Clone repository at base commit
RUN git clone https://github.com/{{ repo }}.git . && \\
    git checkout {{ base_commit }}

# Install Node dependencies
RUN if [ -f package-lock.json ]; then npm ci; \\
    elif [ -f yarn.lock ]; then yarn install --frozen-lockfile; \\
    elif [ -f package.json ]; then npm install; fi

# Layer 3: Instance Setup
FROM environment AS instance

# Copy evaluation script
COPY eval_script.sh /eval_script.sh
RUN chmod +x /eval_script.sh

# Default command
CMD ["/bin/bash"]
''')
        
        return template.render(
            repo=pr_data['repo'],
            base_commit=pr_data['base_commit'],
            pr_number=pr_data['pr_number'],
            base_image=base_image,
        )
    
    def _generate_java_dockerfile(self, pr_data: Dict[str, Any], base_image: str) -> str:
        """Generate Dockerfile for Java projects"""
        
        template = Template('''# SWE-Universe Task Instance Dockerfile
# Repository: {{ repo }}
# Base Commit: {{ base_commit }}
# PR: #{{ pr_number }}

# Layer 1: Base Image
FROM {{ base_image }} AS base

# Install system dependencies
RUN apt-get update && apt-get install -y \\
    git \\
    maven \\
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Environment Setup
FROM base AS environment

WORKDIR /workspace

# Clone repository at base commit
RUN git clone https://github.com/{{ repo }}.git . && \\
    git checkout {{ base_commit }}

# Build project and download dependencies
RUN if [ -f pom.xml ]; then mvn dependency:go-offline; fi

# Layer 3: Instance Setup
FROM environment AS instance

# Copy evaluation script
COPY eval_script.sh /eval_script.sh
RUN chmod +x /eval_script.sh

# Default command
CMD ["/bin/bash"]
''')
        
        return template.render(
            repo=pr_data['repo'],
            base_commit=pr_data['base_commit'],
            pr_number=pr_data['pr_number'],
            base_image=base_image,
        )
    
    def _generate_go_dockerfile(self, pr_data: Dict[str, Any], base_image: str) -> str:
        """Generate Dockerfile for Go projects"""
        
        template = Template('''# SWE-Universe Task Instance Dockerfile
# Repository: {{ repo }}
# Base Commit: {{ base_commit }}
# PR: #{{ pr_number }}

# Layer 1: Base Image
FROM {{ base_image }} AS base

# Install system dependencies
RUN apk add --no-cache git bash

# Layer 2: Environment Setup
FROM base AS environment

WORKDIR /workspace

# Clone repository at base commit
RUN git clone https://github.com/{{ repo }}.git . && \\
    git checkout {{ base_commit }}

# Download Go dependencies
RUN if [ -f go.mod ]; then go mod download; fi

# Layer 3: Instance Setup
FROM environment AS instance

# Copy evaluation script
COPY eval_script.sh /eval_script.sh
RUN chmod +x /eval_script.sh

# Default command
CMD ["/bin/bash"]
''')
        
        return template.render(
            repo=pr_data['repo'],
            base_commit=pr_data['base_commit'],
            pr_number=pr_data['pr_number'],
            base_image=base_image,
        )
    
    def _generate_generic_dockerfile(self, pr_data: Dict[str, Any], base_image: str) -> str:
        """Generate generic Dockerfile for unknown languages with auto-detection"""
        
        template = Template('''# SWE-Universe Task Instance Dockerfile
# Repository: {{ repo }}
# Base Commit: {{ base_commit }}
# PR: #{{ pr_number }}

# Layer 1: Base Image
FROM {{ base_image }} AS base

# Install system dependencies and common language runtimes
RUN apt-get update && apt-get install -y \\
    git \\
    build-essential \\
    curl \\
    python3 \\
    python3-pip \\
    python3-dev \\
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Environment Setup
FROM base AS environment

WORKDIR /workspace

# Clone repository at base commit
RUN git clone https://github.com/{{ repo }}.git . && \\
    git checkout {{ base_commit }}

# Auto-detect and install dependencies
# Python
RUN if [ -f requirements.txt ] || [ -f setup.py ] || [ -f pyproject.toml ]; then \\
    pip3 install --no-cache-dir tox pytest pytest-cov pytest-xdist; \\
    if [ -f requirements.txt ]; then pip3 install --no-cache-dir -r requirements.txt; fi; \\
    if [ -f dev-requirements.txt ]; then pip3 install --no-cache-dir -r dev-requirements.txt; fi; \\
    if [ -f setup.py ]; then pip3 install --no-cache-dir -e .; fi; \\
    if [ -f pyproject.toml ]; then pip3 install --no-cache-dir -e .; fi; \\
fi

# Layer 3: Instance Setup
FROM environment AS instance

# Copy evaluation script
COPY eval_script.sh /eval_script.sh
RUN chmod +x /eval_script.sh

# Default command
CMD ["/bin/bash"]
''')
        
        return template.render(
            repo=pr_data['repo'],
            base_commit=pr_data['base_commit'],
            pr_number=pr_data['pr_number'],
            base_image=base_image,
        )
