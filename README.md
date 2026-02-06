# SWE-Universe Task Generation Pipeline

Agentic pipeline for converting GitHub PRs into reproducible SWE-bench task instances, based on the [SWE-Universe methodology](https://arxiv.org/abs/2602.02361).

## How It Works

An autonomous Claude agent generates evaluation scripts through iterative self-verification:

1. **Patch Separation** — Split PR diff into test and fix components
2. **Agent Exploration** — Claude explores the repo, installs deps, identifies tests
3. **Script Generation** — Agent writes `evaluation.sh` and submits it
4. **Validation** — Script is tested in both buggy and fixed states
5. **Hacking Detection** — Reject scripts that use `grep` instead of running tests

## Output

```
tasks/
├── task_001/
│   ├── task.json          # metadata
│   ├── Dockerfile         # builds the environment
│   └── eval_script.sh     # returns 0=pass, 1=fail
├── task_002/
│   └── ...
```

### task.json format

```json
{
  "instance_id": "marshmallow-code-marshmallow-2894",
  "repo": "marshmallow-code/marshmallow",
  "base_commit": "ba8b512...",
  "problem_statement": "The issue description...",
  "gold_patch": "diff --git a/...",
  "image_name": "erranli/swe-task-marshmallow-code-marshmallow-2894:latest",
  "eval_script": "#!/bin/bash\npytest tests/test_foo.py -x\nexit $?"
}
```

## Quick Start

```bash
# Install
pip install -r requirements.txt

# Set API keys
export GITHUB_TOKEN=your_github_token
export ANTHROPIC_API_KEY=your_anthropic_key

# Generate tasks from PRs
python generate_tasks.py \
  --repo marshmallow-code/marshmallow \
  --prs 2894 2892 \
  --dockerhub-username your-username

# Build and push Docker images
python generate_tasks.py \
  --repo owner/repo \
  --prs 123 456 \
  --build-images --push-images
```

## Requirements

- Python 3.8+
- Docker (for building images)
- GitHub API token
- Anthropic API key (Claude)

## Installation

```bash
pip install -r requirements.txt
```
