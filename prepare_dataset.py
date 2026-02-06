"""
Prepare SkyRL-compatible dataset from our generated task instances.

Converts tasks/task_*/task.json into train.parquet and validation.parquet
in the format expected by SkyRL's PromptDataset:

Required columns:
  - data_source: str  (dataset identifier)
  - prompt: List[Dict]  (chat messages, e.g. [{"role": "user", "content": ...}])
  - env_class: str  ("null" — we use custom env via mini-swe-agent)
  - instance: Dict  (full task metadata including instance_id, eval_script, image_name, etc.)
"""

import argparse
import json
import os
import glob

import pyarrow as pa
import pyarrow.parquet as pq


def load_tasks(tasks_dir: str):
    """Load all task.json files from the tasks directory."""
    tasks = []
    task_dirs = sorted(glob.glob(os.path.join(tasks_dir, "task_*")))
    for task_dir in task_dirs:
        task_json = os.path.join(task_dir, "task.json")
        if os.path.exists(task_json):
            with open(task_json) as f:
                task = json.load(f)
            tasks.append(task)
            print(f"  Loaded: {task['instance_id']}")
    return tasks


def tasks_to_parquet(tasks, output_path: str, data_source: str):
    """Convert task instances to a parquet file in SkyRL format."""
    rows = []
    for task in tasks:
        row = {
            "data_source": data_source,
            "prompt": json.dumps([
                {
                    "role": "user",
                    "content": task["problem_statement"],
                }
            ]),
            "env_class": "null",
            # Store full instance as JSON string (pyarrow handles nested dicts poorly)
            "instance": json.dumps(task),
        }
        rows.append(row)

    table = pa.table({
        "data_source": pa.array([r["data_source"] for r in rows]),
        "prompt": pa.array([r["prompt"] for r in rows]),
        "env_class": pa.array([r["env_class"] for r in rows]),
        "instance": pa.array([r["instance"] for r in rows]),
    })

    pq.write_table(table, output_path)
    print(f"  Wrote {len(rows)} instances to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Prepare SkyRL dataset from task instances")
    parser.add_argument("--tasks-dir", default="tasks", help="Directory containing task_* subdirectories")
    parser.add_argument("--output-dir", default="data", help="Output directory for parquet files")
    parser.add_argument("--data-source", default="swe-task-generator", help="Dataset identifier")
    args = parser.parse_args()

    tasks_dir = os.path.abspath(args.tasks_dir)
    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    print(f"Loading tasks from {tasks_dir}...")
    tasks = load_tasks(tasks_dir)

    if not tasks:
        print("ERROR: No task instances found!")
        return

    print(f"\nFound {len(tasks)} task instances")

    # For our small dataset, use same tasks for train and validation
    # In production, you'd split or use different sets
    print("\nWriting training set...")
    tasks_to_parquet(tasks, os.path.join(output_dir, "train.parquet"), args.data_source)

    print("Writing validation set...")
    tasks_to_parquet(tasks, os.path.join(output_dir, "validation.parquet"), args.data_source)

    print(f"\nDataset prepared in {output_dir}/")
    print(f"  train.parquet:      {len(tasks)} instances")
    print(f"  validation.parquet: {len(tasks)} instances")


if __name__ == "__main__":
    main()
