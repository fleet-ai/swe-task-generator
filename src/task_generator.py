"""Task instance generator module"""

import logging
from typing import Dict, Any, Optional, List
from pathlib import Path

from .utils import (
    sanitize_instance_id,
    extract_test_files,
    save_json,
)

logger = logging.getLogger(__name__)


class TaskGenerator:
    """Generates task.json metadata for task instances"""
    
    def __init__(self, dockerhub_username: str):
        """
        Initialize task generator.
        
        Args:
            dockerhub_username: Docker Hub username for image names
        """
        self.dockerhub_username = dockerhub_username
    
    def generate_task_json(
        self,
        pr_data: Dict[str, Any],
        output_dir: Path,
        eval_script_content: str
    ) -> Dict[str, Any]:
        """
        Generate task.json metadata file.
        
        Args:
            pr_data: PR data from GitHub
            output_dir: Output directory for task
            eval_script_content: Content of eval_script.sh
            
        Returns:
            Task metadata dictionary
        """
        instance_id = sanitize_instance_id(pr_data['repo'], pr_data['pr_number'])
        
        # Create problem statement from PR and issue
        problem_statement = self._create_problem_statement(pr_data)
        
        # Extract test files
        test_files = extract_test_files(pr_data['changed_files'])
        
        # Generate image name
        image_name = f"{self.dockerhub_username}/swe-task-{instance_id}:latest"
        
        task_data = {
            "instance_id": instance_id,
            "repo": pr_data['repo'],
            "base_commit": pr_data['base_commit'],
            "head_commit": pr_data['head_commit'],
            "problem_statement": problem_statement,
            "gold_patch": pr_data['diff'],
            "test_files": test_files,
            "changed_files": pr_data['changed_files'],
            "image_name": image_name,
            "eval_script": eval_script_content,
            "pr_number": pr_data['pr_number'],
            "pr_title": pr_data['title'],
            "merged": pr_data['merged'],
            "created_at": pr_data['created_at'],
        }
        
        # Save task.json
        task_json_path = output_dir / "task.json"
        save_json(task_data, task_json_path)
        
        logger.info(f"Generated task.json for {instance_id}")
        return task_data
    
    def _create_problem_statement(self, pr_data: Dict[str, Any]) -> str:
        """
        Create problem statement from PR and issue data.
        
        Args:
            pr_data: PR data from GitHub
            
        Returns:
            Problem statement string
        """
        parts = []
        
        # Add issue information if available
        if pr_data.get('issue'):
            issue = pr_data['issue']
            parts.append(f"# Issue #{issue['number']}: {issue['title']}\n")
            parts.append(issue['body'])
            parts.append("\n---\n")
        
        # Add PR information
        parts.append(f"# Pull Request #{pr_data['pr_number']}: {pr_data['title']}\n")
        parts.append(pr_data['body'])
        
        # Add context about changed files
        if pr_data['changed_files']:
            parts.append("\n## Files Changed\n")
            for file in pr_data['changed_files']:
                parts.append(f"- {file}")
        
        return "\n".join(parts)
    
    def generate_batch(
        self,
        pr_data_list: List[Dict[str, Any]],
        base_output_dir: Path,
        eval_script_generator
    ) -> List[Dict[str, Any]]:
        """
        Generate multiple task instances.
        
        Args:
            pr_data_list: List of PR data dictionaries
            base_output_dir: Base output directory
            eval_script_generator: EvalScriptGenerator instance
            
        Returns:
            List of task metadata dictionaries
        """
        tasks = []
        
        for i, pr_data in enumerate(pr_data_list, 1):
            try:
                instance_id = sanitize_instance_id(pr_data['repo'], pr_data['pr_number'])
                task_dir = base_output_dir / f"task_{i:03d}"
                task_dir.mkdir(parents=True, exist_ok=True)
                
                # Generate eval script first
                eval_script_content = eval_script_generator.generate_eval_script(
                    pr_data, task_dir
                )
                
                # Generate task.json
                task_data = self.generate_task_json(
                    pr_data, task_dir, eval_script_content
                )
                
                tasks.append(task_data)
                logger.info(f"Generated task {i}/{len(pr_data_list)}: {instance_id}")
                
            except Exception as e:
                logger.error(f"Failed to generate task for PR #{pr_data['pr_number']}: {e}")
                continue
        
        return tasks
    
    def validate_task(self, task_data: Dict[str, Any]) -> bool:
        """
        Validate task data.
        
        Args:
            task_data: Task metadata dictionary
            
        Returns:
            True if valid, False otherwise
        """
        required_fields = [
            'instance_id',
            'repo',
            'base_commit',
            'problem_statement',
            'gold_patch',
            'image_name',
            'eval_script',
        ]
        
        for field in required_fields:
            if field not in task_data:
                logger.error(f"Missing required field: {field}")
                return False
            if not task_data[field]:
                logger.error(f"Empty required field: {field}")
                return False
        
        # Validate that we have test files
        if not task_data.get('test_files'):
            logger.warning(f"No test files found for {task_data['instance_id']}")
            # This is a warning, not an error - some PRs might not modify test files directly
        
        return True
