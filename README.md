# SWE-Universe Task Generation Pipeline

Agentic pipeline for converting GitHub PRs into reproducible SWE-bench task instances, based on the [SWE-Universe methodology](https://arxiv.org/abs/2602.02361).

## How It Works

An autonomous Claude agent generates evaluation scripts through iterative self-verification:

1. **Patch Separation** — Split PR diff into test and fix components
2. **Agent Exploration** — Claude explores the repo, installs deps, identifies tests
3. **Script Generation** — Agent writes `evaluation.sh` and submits it
4. **Validation** — Script is tested in both buggy and fixed states
5. **Hacking Detection** — Reject scripts that use `grep` instead of running tests

### Pipeline Architecture

```
generate_tasks.py                          CLI entry point
        │
        ▼
┌──────────────────────────────────────────────────────────────────┐
│  pipeline.py  ─  TaskGenerationPipeline.generate_task()         │
│                                                                  │
│  Step 1 ── github_fetcher.py ── GitHubPRFetcher.fetch_pr_data() │
│            │  Calls GitHub API for PR metadata, diff, commits    │
│            └► _get_pr_diff()  adds --- a/ +++ b/ headers         │
│                                                                  │
│  Step 2 ── agentic_builder.py ── separate_patches()              │
│            │  Splits unified diff into test_patch + fix_patch    │
│            │  by classifying each file:                          │
│            │    tests/*  ──► test_patch                          │
│            │    src/*    ──► fix_patch                           │
│            └►   docs/*   ──► skip                                │
│                                                                  │
│  Step 3 ── agentic_builder.py ── build_environment()             │
│            │                                                     │
│            │  ┌─────────────────────────────────────────┐        │
│            │  │  _setup_workspace()                     │        │
│            │  │  ├─ git clone repo @ base_commit        │        │
│            │  │  ├─ Save test.patch, fix.patch          │        │
│            │  │  └─ _apply_patch(test.patch)            │        │
│            │  │     Repo is now in BUGGY state          │        │
│            │  │     (new tests exist, but bug unfixed)  │        │
│            │  └─────────────────────────────────────────┘        │
│            │                                                     │
│            │  _create_system_prompt()                            │
│            │    Builds prompt with repo info + test patch diff   │
│            │                                                     │
│            │  ┌─────── AGENTIC LOOP (up to 30 turns) ───────┐   │
│            │  │                                              │   │
│            │  │  _call_claude_with_tools()                   │   │
│            │  │    Anthropic API ─► Claude with 4 tools:     │   │
│            │  │                                              │   │
│            │  │    ┌──────────────────────────────────────┐   │   │
│            │  │    │  TOOL: bash                          │   │   │
│            │  │    │  _execute_tool("bash", {command})    │   │   │
│            │  │    │  └► subprocess.run(cmd, cwd=repo/)   │   │   │
│            │  │    │     Agent explores: ls, cat, pip...  │   │   │
│            │  │    ├──────────────────────────────────────┤   │   │
│            │  │    │  TOOL: switch-to-resolved            │   │   │
│            │  │    │  _execute_tool("switch-to-resolved") │   │   │
│            │  │    │  └► git checkout -- .                │   │   │
│            │  │    │     _apply_patch(test.patch)         │   │   │
│            │  │    │     _apply_patch(fix.patch)          │   │   │
│            │  │    ├──────────────────────────────────────┤   │   │
│            │  │    │  TOOL: switch-to-bug                 │   │   │
│            │  │    │  _execute_tool("switch-to-bug")      │   │   │
│            │  │    │  └► git checkout -- .                │   │   │
│            │  │    │     _apply_patch(test.patch)         │   │   │
│            │  │    ├──────────────────────────────────────┤   │   │
│            │  │    │  TOOL: submit_eval_script            │   │   │
│            │  │    │  Agent submits script_content ──┐    │   │   │
│            │  │    └─────────────────────────────────┼────┘   │   │
│            │  │                                      │        │   │
│            │  │  ┌── VALIDATION (on submit) ─────────▼───┐    │   │
│            │  │  │                                       │    │   │
│            │  │  │  _detect_hacking(script)              │    │   │
│            │  │  │  ├─ Has test runner? (pytest/tox/...) │    │   │
│            │  │  │  └─ Only grep/cat/diff? ──► REJECT    │    │   │
│            │  │  │                                       │    │   │
│            │  │  │  _validate_script(workspace, fix)     │    │   │
│            │  │  │  ├─ BUGGY state:                      │    │   │
│            │  │  │  │  git checkout + apply test.patch   │    │   │
│            │  │  │  │  bash evaluation.sh ──► exit code  │    │   │
│            │  │  │  ├─ FIXED state:                      │    │   │
│            │  │  │  │  git checkout + apply test.patch   │    │   │
│            │  │  │  │  + apply fix.patch                 │    │   │
│            │  │  │  │  bash evaluation.sh ──► exit code  │    │   │
│            │  │  │  │                                    │    │   │
│            │  │  │  │  buggy ≠ 0  AND  fixed = 0 ?      │    │   │
│            │  │  │  │  ├─ YES ──► SUCCESS ✓ return path  │    │   │
│            │  │  │  │  └─ NO  ──► feedback to Claude ◄───┤    │   │
│            │  │  │  │            (continue loop)         │    │   │
│            │  │  └──┴────────────────────────────────────┘    │   │
│            │  └──────────────────────────────────────────────┘   │
│            │                                                     │
│            └► Returns path to validated evaluation.sh            │
│                                                                  │
│  Step 4 ── dockerfile_generator.py ── generate_dockerfile()      │
│            Generates layered Dockerfile (base → env → instance)  │
│                                                                  │
│  Step 5 ── task_generator.py ── generate_task_json()             │
│            Assembles task.json with all metadata                 │
│                                                                  │
│  Step 6 ── docker_builder.py ── build_image() / push_image()    │
│            (optional) Build and push to Docker Hub               │
└──────────────────────────────────────────────────────────────────┘
        │
        ▼
    tasks/task_001/
    ├── task.json
    ├── Dockerfile
    └── eval_script.sh
```

### Key Insight: Two-State Validation

The validation step is what makes this pipeline reliable. A valid `eval_script.sh`
must produce **different exit codes** depending on whether the bug fix is applied:

```
             ┌─────────────┐         ┌─────────────┐
             │ BUGGY state │         │ FIXED state  │
             │             │         │              │
             │ base commit │         │ base commit  │
             │ + test patch│         │ + test patch │
             │ (no fix)    │         │ + fix patch  │
             └──────┬──────┘         └──────┬───────┘
                    │                       │
             eval_script.sh          eval_script.sh
                    │                       │
                    ▼                       ▼
              exit code ≠ 0          exit code = 0
              (tests FAIL) ✓         (tests PASS) ✓
```

If both conditions hold, the script correctly distinguishes buggy from fixed code.

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
