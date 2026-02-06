"""
Demonstrate reward signal from our task instances.

This script shows the end-to-end reward pipeline that SkyRL uses during training:
1. Pull Docker image from Docker Hub
2. Run eval_script in "buggy" state (base_commit, no fix) → should FAIL (reward=0)
3. Apply the gold_patch (fix)
4. Run eval_script again → should PASS (reward=1)

This is exactly what happens during RL training:
- The agent generates a patch
- The patch is applied to the buggy repo
- eval_script.sh runs and returns 0 (pass) or non-zero (fail)
- reward = 1.0 if returncode == 0 else 0.0
"""

import json
import os
import sys
import subprocess
import glob
import time


def run_in_container(image_name: str, command: str, timeout: int = 300) -> dict:
    """Run a command in a Docker container and return result."""
    try:
        result = subprocess.run(
            ["docker", "run", "--rm", image_name, "bash", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "returncode": result.returncode,
            "output": result.stdout + result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {"returncode": -1, "output": "TIMEOUT"}


def demonstrate_reward(task_dir: str):
    """Show reward signal for a single task."""
    task_json_path = os.path.join(task_dir, "task.json")
    with open(task_json_path) as f:
        task = json.load(f)

    instance_id = task["instance_id"]
    image_name = task["image_name"]
    eval_script = task["eval_script"]
    gold_patch = task["gold_patch"]
    test_patch = task.get("test_patch", "")

    print(f"\n{'='*70}")
    print(f"Task: {instance_id}")
    print(f"Image: {image_name}")
    print(f"{'='*70}")

    # --- Step 1: Run eval_script on BUGGY state (no fix applied) ---
    print(f"\n--- Step 1: Evaluate BUGGY state (base_commit, test patch only) ---")
    # Apply test patch first (so the test exists), then run eval
    buggy_cmd = f"""
cd /workspace
git apply --allow-empty <<'PATCH_EOF'
{test_patch}
PATCH_EOF
{eval_script}
"""
    print(f"  Running eval_script in buggy state...")
    t0 = time.time()
    result = run_in_container(image_name, buggy_cmd)
    elapsed = time.time() - t0
    buggy_reward = 1.0 if result["returncode"] == 0 else 0.0
    print(f"  Return code: {result['returncode']}")
    print(f"  Reward: {buggy_reward}")
    print(f"  Time: {elapsed:.1f}s")
    if result["output"]:
        # Show last 500 chars of output
        output_tail = result["output"][-500:]
        print(f"  Output (last 500 chars):\n    {'    '.join(output_tail.splitlines(True))}")

    # --- Step 2: Run eval_script on FIXED state (gold patch applied) ---
    print(f"\n--- Step 2: Evaluate FIXED state (gold patch applied) ---")
    fixed_cmd = f"""
cd /workspace
git apply --allow-empty <<'PATCH_EOF'
{gold_patch}
PATCH_EOF
{eval_script}
"""
    print(f"  Running eval_script with gold patch...")
    t0 = time.time()
    result = run_in_container(image_name, fixed_cmd)
    elapsed = time.time() - t0
    fixed_reward = 1.0 if result["returncode"] == 0 else 0.0
    print(f"  Return code: {result['returncode']}")
    print(f"  Reward: {fixed_reward}")
    print(f"  Time: {elapsed:.1f}s")
    if result["output"]:
        output_tail = result["output"][-500:]
        print(f"  Output (last 500 chars):\n    {'    '.join(output_tail.splitlines(True))}")

    # --- Summary ---
    print(f"\n--- Reward Signal Summary ---")
    print(f"  Buggy state:  reward = {buggy_reward}  (expected: 0.0)")
    print(f"  Fixed state:  reward = {fixed_reward}  (expected: 1.0)")

    if buggy_reward == 0.0 and fixed_reward == 1.0:
        print(f"  ✅ Reward signal is correct!")
        return True
    else:
        print(f"  ❌ Reward signal mismatch — check eval_script and patches")
        return False


def main():
    tasks_dir = sys.argv[1] if len(sys.argv) > 1 else "tasks"
    task_dirs = sorted(glob.glob(os.path.join(tasks_dir, "task_*")))

    if not task_dirs:
        print(f"No task directories found in {tasks_dir}/")
        sys.exit(1)

    print(f"Demonstrating reward signal for {len(task_dirs)} task(s)")
    print(f"This simulates the SkyRL training reward pipeline:")
    print(f"  agent patch → apply → eval_script → reward ∈ {{0, 1}}")

    results = []
    for task_dir in task_dirs:
        ok = demonstrate_reward(task_dir)
        results.append(ok)

    print(f"\n{'='*70}")
    print(f"FINAL RESULTS")
    print(f"{'='*70}")
    for task_dir, ok in zip(task_dirs, results):
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  {os.path.basename(task_dir)}: {status}")

    all_ok = all(results)
    print(f"\nOverall: {'✅ All reward signals correct' if all_ok else '❌ Some rewards incorrect'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
