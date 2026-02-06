"""
Agentic task generation pipeline.

Implements the SWE-Universe methodology (arXiv:2602.02361):
1. Fetch PR data from GitHub
2. Separate test and fix patches
3. Agent-based environment building (Claude generates evaluation.sh)
4. Iterative validation with hacking detection
5. Package into task instance (task.json, Dockerfile, eval_script.sh)
"""

import logging
import shutil
from typing import List, Dict, Any, Optional
from pathlib import Path

from .github_fetcher import GitHubPRFetcher
from .task_generator import TaskGenerator
from .dockerfile_generator import DockerfileGenerator
from .docker_builder import DockerBuilder
from .agentic_builder import AgenticEnvironmentBuilder
from .utils import setup_output_directory, save_json

logger = logging.getLogger(__name__)


class TaskGenerationPipeline:
    """
    Agentic task generation pipeline.

    Takes GitHub PRs and converts them into task instances using an
    autonomous Claude agent to generate evaluation scripts, following
    the SWE-Universe methodology.
    """

    def __init__(
        self,
        dockerhub_username: str,
        github_token: Optional[str] = None,
        output_dir: str = "tasks",
        anthropic_api_key: Optional[str] = None,
    ):
        """
        Initialize pipeline.

        Args:
            dockerhub_username: Docker Hub username for image names
            github_token: GitHub API token (optional, falls back to GITHUB_TOKEN env)
            output_dir: Base output directory for tasks
            anthropic_api_key: Anthropic API key for Claude agent
        """
        self.dockerhub_username = dockerhub_username
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Core components
        self.github_fetcher = GitHubPRFetcher(github_token)
        self.task_generator = TaskGenerator(dockerhub_username)
        self.dockerfile_generator = DockerfileGenerator()
        self.docker_builder = DockerBuilder()

        # Agentic builder (required)
        if not anthropic_api_key:
            raise ValueError("anthropic_api_key is required for the agentic pipeline")
        self.agentic_builder = AgenticEnvironmentBuilder(anthropic_api_key)

        logger.info(f"Pipeline initialized (output: {self.output_dir})")

    def generate_task(
        self,
        repo: str,
        pr_number: int,
        task_id: Optional[str] = None,
        build_image: bool = False,
        push_image: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate a single task instance from a GitHub PR.

        Pipeline steps:
          1. Fetch PR data from GitHub
          2. Separate patches (test vs fix)
          3. Agent builds evaluation.sh via iterative validation
          4. Generate Dockerfile and task.json
          5. Optionally build & push Docker image

        Args:
            repo: Repository (owner/repo)
            pr_number: PR number
            task_id: Custom task ID (auto-generated if None)
            build_image: Build Docker image after generation
            push_image: Push Docker image to registry

        Returns:
            Task metadata dictionary

        Raises:
            ValueError: If PR lacks valid test and fix patches
        """
        logger.info(f"Generating task for {repo} PR #{pr_number}")

        # --- Step 1: Fetch PR data ---
        logger.info("Step 1: Fetching PR data from GitHub")
        pr_data = self.github_fetcher.fetch_pr_data(repo, pr_number)

        # --- Step 2: Patch separation ---
        logger.info("Step 2: Separating test and fix patches")
        test_patch, fix_patch = self.agentic_builder.separate_patches(pr_data)

        if not test_patch or not fix_patch:
            raise ValueError("PR does not have valid test and fix patches")

        # --- Step 3: Create task directory ---
        if not task_id:
            task_id = f"task_{pr_number:03d}"
        task_dir = setup_output_directory(self.output_dir, task_id)
        logger.info(f"Step 3: Task directory: {task_dir}")

        # --- Step 4: Agent-based environment building ---
        logger.info("Step 4: Agent building evaluation.sh")
        workspace_dir = task_dir / "agentic_workspace"
        eval_script_path = self.agentic_builder.build_environment(
            pr_data, test_patch, fix_patch, workspace_dir
        )

        if not eval_script_path:
            raise ValueError("Agent failed to generate valid evaluation.sh")

        # Copy evaluation.sh to task directory
        eval_dest = task_dir / "eval_script.sh"
        shutil.copy(eval_script_path, eval_dest)
        eval_dest.chmod(0o755)
        eval_script_content = eval_dest.read_text()

        logger.info("Agent successfully generated evaluation.sh")

        # --- Step 5: Generate Dockerfile ---
        logger.info("Step 5: Generating Dockerfile")
        self.dockerfile_generator.generate_dockerfile(pr_data, task_dir)

        # --- Step 6: Generate task.json ---
        logger.info("Step 6: Generating task.json")
        task_data = self.task_generator.generate_task_json(
            pr_data, task_dir, eval_script_content
        )
        task_data["generation_method"] = "agentic"
        task_data["test_patch"] = test_patch
        task_data["fix_patch"] = fix_patch

        # --- Step 7: Build & push Docker image (optional) ---
        if build_image:
            image_name = task_data["image_name"]
            logger.info(f"Step 7: Building Docker image: {image_name}")
            build_ok = self.docker_builder.build_image(task_dir, image_name)
            task_data["build_status"] = "success" if build_ok else "failed"

            if push_image and build_ok:
                logger.info(f"Pushing Docker image: {image_name}")
                push_ok = self.docker_builder.push_image(image_name)
                task_data["push_status"] = "success" if push_ok else "failed"

        # Save final task.json
        save_json(task_data, task_dir / "task.json")

        logger.info(f"Task generation complete: {task_id}")
        return task_data

    def generate_tasks(
        self,
        repo: str,
        pr_numbers: List[int],
        build_images: bool = False,
        push_images: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Generate task instances from a list of PRs.

        Args:
            repo: Repository (owner/repo)
            pr_numbers: List of PR numbers
            build_images: Build Docker images
            push_images: Push Docker images

        Returns:
            List of task metadata dictionaries
        """
        logger.info(f"Generating {len(pr_numbers)} tasks from {repo}")

        tasks = []
        for i, pr_number in enumerate(pr_numbers, 1):
            task_id = f"task_{i:03d}"
            try:
                task_data = self.generate_task(
                    repo=repo,
                    pr_number=pr_number,
                    task_id=task_id,
                    build_image=build_images,
                    push_image=push_images,
                )
                tasks.append(task_data)
                logger.info(f"Progress: {i}/{len(pr_numbers)}")
            except Exception as e:
                logger.error(f"Failed PR #{pr_number}: {e}")
                continue

        # Save summary
        summary = {
            "total_tasks": len(tasks),
            "repo": repo,
            "tasks": [
                {
                    "instance_id": t["instance_id"],
                    "pr_number": t["pr_number"],
                    "image_name": t["image_name"],
                    "build_status": t.get("build_status", "not_built"),
                }
                for t in tasks
            ],
        }
        save_json(summary, self.output_dir / "summary.json")

        logger.info(f"Generated {len(tasks)}/{len(pr_numbers)} tasks")
        return tasks

    def validate_tasks(self) -> Dict[str, Any]:
        """
        Validate all generated tasks in the output directory.

        Returns:
            Validation report dictionary
        """
        task_dirs = sorted([d for d in self.output_dir.iterdir() if d.is_dir()])

        report = {"total": len(task_dirs), "valid": 0, "invalid": 0, "details": []}

        for task_dir in task_dirs:
            has_all = all(
                (task_dir / f).exists()
                for f in ["task.json", "Dockerfile", "eval_script.sh"]
            )

            if has_all:
                import json

                with open(task_dir / "task.json") as f:
                    task_data = json.load(f)
                is_valid = self.task_generator.validate_task(task_data)
            else:
                is_valid = False

            if is_valid:
                report["valid"] += 1
            else:
                report["invalid"] += 1

            report["details"].append(
                {"task_id": task_dir.name, "valid": is_valid}
            )

        logger.info(f"Validation: {report['valid']}/{report['total']} valid")
        return report
