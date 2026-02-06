from setuptools import setup, find_packages

setup(
    name="swe-task-generator",
    version="0.2.0",
    description="Agentic SWE-Universe task generation from GitHub PRs",
    python_requires=">=3.8",
    packages=find_packages(),
    install_requires=[
        "requests>=2.31.0",
        "PyGithub>=2.1.1",
        "docker>=6.1.3",
        "pyyaml>=6.0.1",
        "gitpython>=3.1.40",
        "jinja2>=3.1.2",
        "python-dotenv>=1.0.0",
        "anthropic>=0.40.0",
    ],
    entry_points={
        "console_scripts": [
            "swe-generate-tasks=generate_tasks:main",
        ],
    },
)
