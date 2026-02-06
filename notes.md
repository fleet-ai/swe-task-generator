# Notes — SWE Task Generator + SkyRL Integration

## What Was Built

### Part 1: Task Generation (Agentic Pipeline)
- Implemented the SWE-Universe agentic methodology (arXiv:2602.02361)
- Claude agent generates `evaluation.sh` through iterative self-verification
- Patch separation: split PR diff into test and fix components
- In-loop hacking detection (reject `grep`-based scripts)
- Two-state validation: eval_script fails on buggy code, passes on fixed code
- Generated 2 task instances from marshmallow PRs (#2894, #2892)
- Docker images pushed to Docker Hub

### Part 2: SkyRL Integration
- Created full SkyRL integration at `SkyRL/skyrl-train/integrations/swe_tasks/`
- Custom `SWETasksGenerator` extending `SkyRLGymGenerator` (follows mini_swe_agent pattern)
- Dataset preparation: `prepare_dataset.py` converts `tasks/task.json` → parquet
- SkyPilot config: `tasks/swe-tasks-grpo-qwen3-8b.yaml` for cloud GPU deployment
- Training script: `run_swe_tasks_8B.sh` for local 8xH100 clusters
- Agent YAML config: `swe_tasks.yaml` with system prompt, step limits, Docker settings

### Reward Signal Demonstration
Both tasks show correct binary reward:
```
task_001 (marshmallow PR #2894 — Constant(None) bug):
  Buggy state:  reward = 0.0  ← test fails with ValidationError
  Fixed state:  reward = 1.0  ← test passes after moving kwargs before super().__init__()

task_002 (marshmallow PR #2892 — uppercase file:// URLs):
  Buggy state:  reward = 0.0  ← test fails with "Not a valid URL"
  Fixed state:  reward = 1.0  ← test passes after case-insensitive scheme check
```

## What Broke / Lessons Learned

### 1. Eval script dependency completeness
**Problem:** Task 002's eval_script only installed `pytest`, but the test conftest imported `simplejson` (a test dependency not in the base Docker image).
**Fix:** Updated eval_script to install project with `pip install -e ".[tests]"` and explicitly install `simplejson`.
**Lesson:** Eval scripts must install ALL test dependencies, not just pytest. The agentic pipeline should verify this during generation.

### 2. Docker image working directory
**Problem:** SkyRL's mini_swe_agent expects `/testbed` as cwd, but our Dockerfiles use `/workspace`.
**Fix:** Set `cwd: "/workspace"` in `swe_tasks.yaml`.
**Lesson:** This is a config-level difference that's easy to overlook. Standardizing on `/testbed` would reduce friction.

### 3. Parquet schema for nested dicts
**Problem:** PyArrow doesn't handle nested dicts well for the `instance` column (required by mini_swe_agent's data loader).
**Fix:** Flattened instance fields as top-level columns (`instance_id`, `eval_script`, `image_name`, etc.) and reconstructed the instance dict in the generator.
**Lesson:** SkyRL's `PromptDataset` passes extra columns as `env_extras`, making flat schemas simpler.

### 4. GPU requirement for full training
**Problem:** Can't run GRPO training on Mac M4 — requires CUDA GPUs (8xH100 minimum for Qwen3-8B).
**Approach:** Demonstrated reward signal end-to-end without GPU training, created all configs for cloud deployment via SkyPilot.
**To run:** `sky launch tasks/swe-tasks-grpo-qwen3-8b.yaml --env WANDB_API_KEY=<key>`

### 5. Small dataset (2 tasks) for RL training
**Problem:** 2 task instances is far too few for meaningful RL training. GRPO needs diversity.
**Mitigation:** `n_samples_per_prompt=4` generates 4 trajectories per task, but this gives limited advantage signal.
**Revisit:** Scale to 50+ tasks from diverse repos. The agentic pipeline can process many PRs in parallel.

## What I'd Revisit

### Priority 1: Scale task generation
- Run agentic pipeline on 50-100 PRs across popular Python repos
- Filter for tasks where the eval_script reliably differentiates buggy/fixed states
- Add difficulty scoring (lines changed, test complexity) for curriculum learning

### Priority 2: Improve eval_script robustness
- The agentic pipeline should verify that all test dependencies are installed
- Add a "dependency discovery" step: run `pip install -e ".[tests,dev]"` in Docker before generating eval_script
- Consider pre-installing common test frameworks in the base Docker image

### Priority 3: Training configuration tuning
- Batch sizes (currently 2) are small due to only 2 tasks — increase with more tasks
- Context length budget: marshmallow tasks are simple (~4K tokens), but larger repos need ~30K
- Consider step_wise_trajectories for per-turn rewards instead of episode-level

### Priority 4: Podman vs Docker
- SkyRL's mini_swe_agent defaults to Podman (rootless containers, better for shared GPU clusters)
- Our integration uses Docker — add Podman support for production deployments
- Consider using `executable: podman` in swe_tasks.yaml for GPU clusters

### Priority 5: Push SkyRL integration upstream
- Currently lives in the SkyRL checkout as a local integration
- Should be contributed as a PR to fleet-ai/SkyRL with tests
- Follow CLAUDE.md guidelines: branch, black formatting, tests, PR review

## Architecture Overview

```
swe-task-generator/                    SkyRL/skyrl-train/
├── tasks/task_001/                    ├── integrations/swe_tasks/
│   ├── task.json                      │   ├── prepare_dataset.py
│   ├── Dockerfile                     │   ├── env.py
│   └── eval_script.sh                 │   ├── swe_tasks_generator.py
├── prepare_dataset.py                 │   ├── swe_tasks.yaml
├── show_reward.py                     │   ├── run_swe_tasks_8B.sh
└── data/                              │   └── entrypoints/
    ├── train.parquet  ───────────────▶│       └── main_swe_tasks.py
    └── validation.parquet             └── tasks/
                                           └── swe-tasks-grpo-qwen3-8b.yaml

Training flow:
  tasks/task.json → prepare_dataset.py → parquet → SkyRL DataLoader
                                                        │
                Docker Hub ◀── image_name ──────── SWETasksGenerator
                     │                                   │
                     └── Docker container ◀── agent bash commands
                              │                          │
                         eval_script.sh ──── reward ───▶ GRPO loss
```

## Commands Reference

```bash
# Prepare dataset
python prepare_dataset.py --tasks-dir tasks --output-dir data

# Show reward signal (no GPU needed)
python show_reward.py

# Launch training on cloud GPU (requires SkyPilot + cloud credentials)
cd SkyRL/skyrl-train
sky launch tasks/swe-tasks-grpo-qwen3-8b.yaml --env WANDB_API_KEY=<key>

# Launch training locally (requires 8xH100)
cd SkyRL/skyrl-train
bash integrations/swe_tasks/run_swe_tasks_8B.sh
```
