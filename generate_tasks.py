#!/usr/bin/env python3
"""
Generate SWE-Universe task instances from GitHub PRs.

Uses the agentic pipeline (arXiv:2602.02361) where Claude autonomously
generates evaluation scripts through iterative self-verification.

Usage:
    python generate_tasks.py --repo marshmallow-code/marshmallow --prs 2894 2892
    python generate_tasks.py --repo owner/repo --prs 123 --build-images --push-images
"""

import argparse
import logging
import os
import sys

from src.pipeline import TaskGenerationPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("task_generation.log"),
    ],
)
logger = logging.getLogger(__name__)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate SWE-Universe task instances from GitHub PRs (agentic pipeline)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python generate_tasks.py --repo marshmallow-code/marshmallow --prs 2894 2892
  python generate_tasks.py --repo owner/repo --prs 123 --build-images --push-images
  python generate_tasks.py --repo owner/repo --prs 123 --output-dir my_tasks
        """,
    )

    parser.add_argument("--repo", required=True, help="Repository (owner/repo)")
    parser.add_argument("--prs", type=int, nargs="+", required=True, help="PR numbers")
    parser.add_argument("--output-dir", default="tasks", help="Output directory (default: tasks)")
    parser.add_argument("--dockerhub-username", default="erranli", help="Docker Hub username")
    parser.add_argument("--github-token", help="GitHub token (or set GITHUB_TOKEN env var)")
    parser.add_argument("--anthropic-api-key", help="Anthropic API key (or set ANTHROPIC_API_KEY)")
    parser.add_argument("--build-images", action="store_true", help="Build Docker images")
    parser.add_argument("--push-images", action="store_true", help="Push Docker images")
    parser.add_argument("--validate", action="store_true", help="Validate tasks after creation")
    parser.add_argument("--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.push_images and not args.build_images:
        parser.error("--push-images requires --build-images")

    return args


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve API keys
    github_token = args.github_token or os.getenv("GITHUB_TOKEN")
    anthropic_key = args.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")

    if not anthropic_key:
        logger.error("Anthropic API key required. Use --anthropic-api-key or set ANTHROPIC_API_KEY")
        return 1

    logger.info("=" * 70)
    logger.info("SWE-Universe Agentic Task Generation")
    logger.info("=" * 70)

    try:
        pipeline = TaskGenerationPipeline(
            dockerhub_username=args.dockerhub_username,
            github_token=github_token,
            output_dir=args.output_dir,
            anthropic_api_key=anthropic_key,
        )

        tasks = pipeline.generate_tasks(
            repo=args.repo,
            pr_numbers=args.prs,
            build_images=args.build_images,
            push_images=args.push_images,
        )

        if args.validate:
            pipeline.validate_tasks()

        logger.info("=" * 70)
        logger.info(f"Generated {len(tasks)} task(s) in {args.output_dir}/")
        for t in tasks:
            logger.info(f"  {t['instance_id']}: {t.get('pr_title', '')}")
        logger.info("=" * 70)

        return 0

    except KeyboardInterrupt:
        logger.warning("Interrupted")
        return 1
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
