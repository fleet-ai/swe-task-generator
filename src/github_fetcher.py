"""GitHub PR data fetcher module"""

import logging
from typing import Dict, Any, Optional, List
from github import Github, GithubException
from github.PullRequest import PullRequest
from github.Repository import Repository
import git

from .utils import get_github_token

logger = logging.getLogger(__name__)


class GitHubPRFetcher:
    """Fetches PR data from GitHub API"""
    
    def __init__(self, token: Optional[str] = None):
        """
        Initialize GitHub API client.
        
        Args:
            token: GitHub API token (optional, will use env var if not provided)
        """
        self.token = token or get_github_token()
        self.github = Github(self.token) if self.token else Github()
        
    def fetch_pr_data(self, repo_name: str, pr_number: int) -> Dict[str, Any]:
        """
        Fetch PR data from GitHub.
        
        Args:
            repo_name: Repository name (owner/repo)
            pr_number: PR number
            
        Returns:
            Dictionary containing PR data
        """
        try:
            repo = self.github.get_repo(repo_name)
            pr = repo.get_pull(pr_number)
            
            logger.info(f"Fetching PR #{pr_number} from {repo_name}")
            
            # Get base commit (before PR)
            base_commit = pr.base.sha
            
            # Get head commit (after PR)
            head_commit = pr.head.sha
            
            # Get changed files
            changed_files = [f.filename for f in pr.get_files()]
            
            # Get issue if linked
            issue_data = None
            if pr.body:
                issue_data = self._extract_issue_from_body(pr.body, repo)
            
            # Get PR diff
            diff = self._get_pr_diff(pr)
            
            pr_data = {
                'repo': repo_name,
                'pr_number': pr_number,
                'title': pr.title,
                'body': pr.body or "",
                'base_commit': base_commit,
                'head_commit': head_commit,
                'changed_files': changed_files,
                'diff': diff,
                'issue': issue_data,
                'merged': pr.merged,
                'state': pr.state,
                'created_at': pr.created_at.isoformat(),
                'merged_at': pr.merged_at.isoformat() if pr.merged_at else None,
            }
            
            logger.info(f"Successfully fetched PR #{pr_number}")
            return pr_data
            
        except GithubException as e:
            logger.error(f"GitHub API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching PR data: {e}")
            raise
    
    def _extract_issue_from_body(self, body: str, repo: Repository) -> Optional[Dict[str, Any]]:
        """
        Extract linked issue from PR body.
        
        Args:
            body: PR body text
            repo: GitHub repository object
            
        Returns:
            Issue data or None
        """
        # Look for common issue reference patterns
        import re
        patterns = [
            r'[Ff]ixes #(\d+)',
            r'[Cc]loses #(\d+)',
            r'[Rr]esolves #(\d+)',
            r'#(\d+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, body)
            if match:
                issue_number = int(match.group(1))
                try:
                    issue = repo.get_issue(issue_number)
                    return {
                        'number': issue_number,
                        'title': issue.title,
                        'body': issue.body or "",
                    }
                except GithubException:
                    continue
        
        return None
    
    def _get_pr_diff(self, pr: PullRequest) -> str:
        """
        Get unified diff for PR in proper git apply format.
        
        Args:
            pr: PullRequest object
            
        Returns:
            Unified diff string with proper --- a/file and +++ b/file headers
        """
        try:
            # Get diff from GitHub API
            files = pr.get_files()
            diff_parts = []
            
            for file in files:
                if file.patch:
                    diff_parts.append(f"diff --git a/{file.filename} b/{file.filename}")
                    # Add the --- and +++ headers that git apply requires
                    if file.status == 'added':
                        diff_parts.append(f"--- /dev/null")
                        diff_parts.append(f"+++ b/{file.filename}")
                    elif file.status == 'removed':
                        diff_parts.append(f"--- a/{file.filename}")
                        diff_parts.append(f"+++ /dev/null")
                    else:
                        diff_parts.append(f"--- a/{file.filename}")
                        diff_parts.append(f"+++ b/{file.filename}")
                    diff_parts.append(file.patch)
            
            return "\n".join(diff_parts)
        except Exception as e:
            logger.warning(f"Could not fetch diff: {e}")
            return ""
    
    def fetch_multiple_prs(self, repo_name: str, pr_numbers: List[int]) -> List[Dict[str, Any]]:
        """
        Fetch multiple PRs from a repository.
        
        Args:
            repo_name: Repository name (owner/repo)
            pr_numbers: List of PR numbers
            
        Returns:
            List of PR data dictionaries
        """
        pr_data_list = []
        for pr_number in pr_numbers:
            try:
                pr_data = self.fetch_pr_data(repo_name, pr_number)
                pr_data_list.append(pr_data)
            except Exception as e:
                logger.error(f"Failed to fetch PR #{pr_number}: {e}")
                continue
        
        return pr_data_list
    
    def clone_repository(self, repo_name: str, target_dir: str, commit: str) -> None:
        """
        Clone repository and checkout specific commit.
        
        Args:
            repo_name: Repository name (owner/repo)
            target_dir: Directory to clone into
            commit: Commit SHA to checkout
        """
        try:
            repo_url = f"https://github.com/{repo_name}.git"
            logger.info(f"Cloning {repo_url} to {target_dir}")
            
            repo = git.Repo.clone_from(repo_url, target_dir)
            repo.git.checkout(commit)
            
            logger.info(f"Checked out commit {commit}")
        except Exception as e:
            logger.error(f"Error cloning repository: {e}")
            raise
    
    def get_test_commands(self, repo_name: str) -> Optional[Dict[str, Any]]:
        """
        Try to determine test commands from repository.
        
        Args:
            repo_name: Repository name (owner/repo)
            
        Returns:
            Dictionary with test command info or None
        """
        try:
            repo = self.github.get_repo(repo_name)
            
            # Check for common CI files
            ci_files = [
                '.github/workflows/test.yml',
                '.github/workflows/ci.yml',
                '.travis.yml',
                'circle.yml',
                '.circleci/config.yml',
            ]
            
            for ci_file in ci_files:
                try:
                    content = repo.get_contents(ci_file)
                    # Parse CI file to extract test commands
                    # This is a simplified version
                    return {
                        'ci_file': ci_file,
                        'content': content.decoded_content.decode('utf-8')
                    }
                except GithubException:
                    continue
            
            return None
        except Exception as e:
            logger.warning(f"Could not fetch test commands: {e}")
            return None
