"""
Agentic Environment Builder based on SWE-Universe methodology (Section 2.1)
Reference: https://arxiv.org/abs/2602.02361
"""

import os
import logging
import subprocess
import json
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import anthropic

logger = logging.getLogger(__name__)


class AgenticEnvironmentBuilder:
    """
    Autonomous agent that builds verifiable SWE environments using Claude.
    
    Implements the methodology from SWE-Universe paper:
    - Patch separation (test patch vs fix patch)
    - Agent-based environment building with tools
    - Iterative validation loop
    - In-loop hacking detection
    """
    
    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514", max_turns: int = 30):
        """
        Initialize the agentic builder.
        
        Args:
            api_key: Anthropic API key
            model: Claude model to use
            max_turns: Maximum iterations for validation loop
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_turns = max_turns
        self.conversation_history = []
        
    def separate_patches(self, pr_data: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
        """
        Step 1: Patch Separation
        Programmatically separate PR diff into test patch and fix patch by file.
        
        Test files: any file with 'test' in its path
        Fix files: source code files (not tests, docs, changelog, etc.)
        
        Args:
            pr_data: PR data containing diff/gold_patch
            
        Returns:
            Tuple of (test_patch, fix_patch) or (None, None) if no test component
        """
        logger.info("Step 1: Patch Separation - Splitting diff by test vs source files")
        
        # Support both field names: 'gold_patch' (from task.json) and 'diff' (from GitHub fetcher)
        gold_patch = pr_data.get('gold_patch', '') or pr_data.get('diff', '')
        if not gold_patch:
            logger.warning("No gold patch found in PR data (checked 'gold_patch' and 'diff' fields)")
            return None, None
        
        # Split diff by file
        # Each file diff starts with "diff --git a/... b/..."
        import re
        file_diffs = re.split(r'(?=diff --git )', gold_patch)
        file_diffs = [d for d in file_diffs if d.strip()]
        
        test_parts = []
        fix_parts = []
        skip_patterns = [
            'CHANGELOG', 'AUTHORS', 'README', '.rst', '.md',
            'CHANGES', 'HISTORY', 'NEWS', 'CONTRIBUTING',
            '.gitignore', '.github/', 'LICENSE',
        ]
        
        for diff_part in file_diffs:
            # Extract filename from the diff header
            match = re.search(r'diff --git a/(.+?) b/', diff_part)
            if not match:
                continue
            filename = match.group(1)
            
            # Classify the file
            if 'test' in filename.lower():
                test_parts.append(diff_part)
                logger.info(f"  TEST file: {filename}")
            elif any(pat.lower() in filename.lower() for pat in skip_patterns):
                logger.info(f"  SKIP file: {filename} (docs/metadata)")
            else:
                fix_parts.append(diff_part)
                logger.info(f"  FIX file:  {filename}")
        
        if not test_parts:
            logger.info("PR has no test component - discarding")
            return None, None
        
        if not fix_parts:
            logger.info("PR has no source code fix component - discarding")
            return None, None
        
        test_patch = "\n".join(test_parts)
        fix_patch = "\n".join(fix_parts)
        
        logger.info(f"Patch separation: {len(test_parts)} test files, {len(fix_parts)} fix files")
        logger.info(f"Test patch size: {len(test_patch)} chars, Fix patch size: {len(fix_patch)} chars")
        
        return test_patch, fix_patch
    
    def build_environment(
        self,
        pr_data: Dict[str, Any],
        test_patch: str,
        fix_patch: str,
        workspace_dir: Path
    ) -> Optional[str]:
        """
        Step 2: Agent-based Environment Building
        
        Claude autonomously generates evaluation.sh with access to tools:
        - bash: Execute shell commands
        - switch-to-resolved: Apply fix patch (fixed state)
        - switch-to-bug: Revert fix patch (buggy state)
        - submit_eval_script: Submit the final evaluation.sh content
        
        Args:
            pr_data: PR metadata
            test_patch: Test-related changes
            fix_patch: Source code fix
            workspace_dir: Working directory with cloned repository
            
        Returns:
            Path to generated evaluation.sh or None if failed
        """
        logger.info("Step 2: Agent-based Environment Building - Starting agentic loop")
        
        # Initialize workspace
        self._setup_workspace(workspace_dir, pr_data, test_patch, fix_patch)
        
        # Reset conversation for new task
        self.conversation_history = []
        
        system_prompt = self._create_system_prompt(pr_data, test_patch)
        
        for turn in range(1, self.max_turns + 1):
            logger.info(f"Turn {turn}/{self.max_turns}: Agent generating evaluation.sh")
            
            # Nudge the agent to submit after many turns of exploration
            if turn == 10 and self.conversation_history:
                self.conversation_history.append({
                    "role": "user",
                    "content": "You've been exploring for a while. Please submit your evaluation.sh now using the submit_eval_script tool. A simple script that runs pytest on the specific test is usually sufficient."
                })
            elif turn == 20 and self.conversation_history:
                self.conversation_history.append({
                    "role": "user",
                    "content": "URGENT: You must submit evaluation.sh NOW using submit_eval_script. Time is running out. Submit a script that runs: pytest <test_file>::<test_function> -xvs"
                })
            
            try:
                # Call Claude with tool use
                response = self._call_claude_with_tools(system_prompt)
                
                # Process tool uses and get results
                tool_results = []
                submitted_script = None
                submit_tool_id = None
                
                for content_block in response.content:
                    if content_block.type == "tool_use":
                        tool_name = content_block.name
                        tool_input = content_block.input
                        
                        logger.info(f"Agent using tool: {tool_name}")
                        
                        # Check for submit_eval_script tool
                        if tool_name == "submit_eval_script":
                            submitted_script = tool_input.get("script_content", "")
                            submit_tool_id = content_block.id
                            # Placeholder - will be replaced with validation result
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": content_block.id,
                                "content": "Script received. Validating..."
                            })
                            continue
                        
                        # Execute tool
                        result = self._execute_tool(
                            tool_name,
                            tool_input,
                            workspace_dir,
                            fix_patch
                        )
                        
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": content_block.id,
                            "content": result
                        })
                
                # If no tools were called, agent might be done
                if not tool_results:
                    logger.info("Agent finished without tool calls")
                    # Last chance: check if evaluation.sh exists in either location
                    eval_script_content = self._find_eval_script(workspace_dir)
                    if eval_script_content:
                        submitted_script = eval_script_content
                    else:
                        break
                
                # Also check if bash created evaluation.sh in repo_dir
                if not submitted_script:
                    eval_script_content = self._find_eval_script(workspace_dir)
                    if eval_script_content:
                        submitted_script = eval_script_content
                
                # If evaluation.sh was submitted/found, validate it
                if submitted_script:
                    logger.info("Step 3: Iterative Validation - Testing evaluation.sh")
                    
                    # Save script to workspace
                    eval_path = workspace_dir / "evaluation.sh"
                    eval_path.write_text(submitted_script)
                    eval_path.chmod(0o755)
                    
                    # Also save to repo dir for the agent's bash commands
                    repo_eval_path = workspace_dir / "repo" / "evaluation.sh"
                    repo_eval_path.write_text(submitted_script)
                    repo_eval_path.chmod(0o755)
                    
                    # Step 4: In-loop Hacking Detection
                    if self._detect_hacking(submitted_script):
                        logger.warning("Hacking detected! Script uses string matching instead of execution")
                        feedback = "VALIDATION FAILED: Your evaluation.sh uses hacking patterns (grep/string matching instead of running actual tests). You must execute actual tests. Please revise and submit again using submit_eval_script."
                        self._cleanup_eval_scripts(workspace_dir)
                    else:
                        # Test in both states
                        buggy_result, fixed_result = self._validate_script(workspace_dir, fix_patch)
                        
                        # Check if validation passed
                        if buggy_result != 0 and fixed_result == 0:
                            logger.info(f"✓ SUCCESS! evaluation.sh works correctly after {turn} turns")
                            logger.info(f"  - Buggy state: exit code {buggy_result} (expected non-zero)")
                            logger.info(f"  - Fixed state: exit code {fixed_result} (expected zero)")
                            return str(eval_path)
                        else:
                            feedback = f"VALIDATION FAILED:\n"
                            feedback += f"- Buggy state exit code: {buggy_result} (expected non-zero)\n"
                            feedback += f"- Fixed state exit code: {fixed_result} (expected zero)\n"
                            feedback += f"The script must FAIL (non-zero exit) in buggy state and PASS (exit 0) in fixed state.\n"
                            feedback += "Please revise your evaluation.sh and submit again with submit_eval_script."
                            
                            logger.warning(f"Validation failed: buggy={buggy_result}, fixed={fixed_result}")
                            self._cleanup_eval_scripts(workspace_dir)
                    
                    # Update the submit tool result with validation feedback
                    if submit_tool_id:
                        for tr in tool_results:
                            if tr["tool_use_id"] == submit_tool_id:
                                tr["content"] = feedback
                                break
                    # If no submit tool was used (script found via bash), add as user message after tool results
                    elif tool_results:
                        # Append tool results first, then add feedback as separate user message
                        self.conversation_history.append({"role": "assistant", "content": response.content})
                        self.conversation_history.append({"role": "user", "content": tool_results})
                        self.conversation_history.append({"role": "assistant", "content": [{"type": "text", "text": "I see the evaluation.sh was created."}]})
                        self.conversation_history.append({"role": "user", "content": feedback})
                        continue
                
                # Continue conversation with tool results
                if tool_results:
                    self.conversation_history.append({"role": "assistant", "content": response.content})
                    self.conversation_history.append({"role": "user", "content": tool_results})
                
            except Exception as e:
                logger.error(f"Error in turn {turn}: {e}")
                break
        
        logger.error(f"Failed to build environment after {self.max_turns} turns")
        return None
    
    def _find_eval_script(self, workspace_dir: Path) -> Optional[str]:
        """Check for evaluation.sh in both workspace_dir and repo_dir"""
        for path in [
            workspace_dir / "evaluation.sh",
            workspace_dir / "repo" / "evaluation.sh",
        ]:
            if path.exists():
                content = path.read_text().strip()
                if content and len(content) > 10:  # Sanity check
                    logger.info(f"Found evaluation.sh at {path}")
                    return content
        return None
    
    def _cleanup_eval_scripts(self, workspace_dir: Path):
        """Remove evaluation.sh from both locations so we don't reuse a bad one"""
        for path in [
            workspace_dir / "evaluation.sh",
            workspace_dir / "repo" / "evaluation.sh",
        ]:
            if path.exists():
                path.unlink()
    
    def _setup_workspace(self, workspace_dir: Path, pr_data: Dict[str, Any], test_patch: str, fix_patch: str):
        """Setup workspace with cloned repository and patches"""
        workspace_dir.mkdir(parents=True, exist_ok=True)
        
        # Save patches
        (workspace_dir / "test.patch").write_text(test_patch)
        (workspace_dir / "fix.patch").write_text(fix_patch)
        
        # Clone repository if not exists
        repo_dir = workspace_dir / "repo"
        if not repo_dir.exists():
            repo = pr_data['repo']
            base_commit = pr_data['base_commit']
            
            logger.info(f"Cloning {repo} at {base_commit}")
            subprocess.run(
                f"git clone https://github.com/{repo}.git repo",
                shell=True,
                cwd=workspace_dir,
                capture_output=True
            )
            subprocess.run(
                f"git checkout {base_commit}",
                shell=True,
                cwd=repo_dir,
                capture_output=True
            )
        
        # Apply test patch (try multiple approaches)
        self._apply_patch(repo_dir, workspace_dir / "test.patch", "test")
    
    def _apply_patch(self, repo_dir: Path, patch_path: Path, patch_name: str):
        """Apply a patch with multiple fallback strategies"""
        # Resolve to absolute paths to avoid cwd issues with subprocess
        abs_patch_path = patch_path.resolve()
        abs_repo_dir = repo_dir.resolve()
        
        if not abs_patch_path.exists():
            logger.warning(f"Patch file not found: {abs_patch_path}")
            return
        
        patch_content = abs_patch_path.read_text().strip()
        if not patch_content:
            logger.warning(f"Empty {patch_name} patch, skipping")
            return
        
        # Strategy 1: git apply
        result = subprocess.run(
            f"git apply '{abs_patch_path}'",
            shell=True,
            cwd=abs_repo_dir,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"Applied {patch_name} patch successfully with git apply")
            return
        
        # Strategy 2: git apply with --3way
        result = subprocess.run(
            f"git apply --3way '{abs_patch_path}'",
            shell=True,
            cwd=abs_repo_dir,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"Applied {patch_name} patch successfully with git apply --3way")
            return
        
        # Strategy 3: patch -p1
        result = subprocess.run(
            f"patch -p1 < '{abs_patch_path}'",
            shell=True,
            cwd=abs_repo_dir,
            capture_output=True,
            text=True
        )
        if result.returncode == 0:
            logger.info(f"Applied {patch_name} patch successfully with patch -p1")
            return
        
        logger.warning(f"Could not apply {patch_name} patch with any strategy. Agent will need to apply changes manually.")
        logger.warning(f"git apply error: {result.stderr}")
    
    def _create_system_prompt(self, pr_data: Dict[str, Any], test_patch: str) -> str:
        """Create system prompt for the agent"""
        pr_title = pr_data.get('pr_title', '') or pr_data.get('title', '')
        return f"""You are an autonomous agent building a verifiable software engineering environment.

**Task**: Generate a bash script called `evaluation.sh` that reliably distinguishes between buggy and fixed repository states.

**Context**:
- Repository: {pr_data['repo']}
- PR #{pr_data['pr_number']}: {pr_title}
- Base commit: {pr_data['base_commit']}
- The repository has been cloned and checked out at the base commit.

**Test Patch** (these are the test changes from the PR):
```diff
{test_patch[:3000]}{'...' if len(test_patch) > 3000 else ''}
```

**Requirements for evaluation.sh**:
1. The script MUST exit with 0 (success) when tests pass in the FIXED state
2. The script MUST exit with non-zero (failure) when tests fail in the BUGGY state
3. The script MUST execute actual tests (pytest, unittest, etc), NOT just check file contents with grep
4. The script should be self-contained: install dependencies, then run the specific tests

**Available Tools**:
- `bash`: Execute shell commands in the repo directory
- `switch-to-resolved`: Apply the fix patch (switch to fixed state)
- `switch-to-bug`: Revert the fix patch (switch to buggy state)
- `submit_eval_script`: Submit your final evaluation.sh script content

**Workflow** (follow this exactly):
1. Explore the repo structure briefly (ls, cat setup.py/pyproject.toml, look at test directory)
2. Identify the test framework (pytest, tox, unittest, etc.)
3. Figure out which specific test(s) from the test patch should be run
4. Write and submit evaluation.sh using `submit_eval_script`
5. If validation fails, revise and resubmit

**IMPORTANT**:
- Keep exploration BRIEF. Don't read every file - focus on finding the test command.
- The evaluation.sh should typically just: install deps, then run the specific test.
- Use `submit_eval_script` tool to submit when ready. Do NOT use `cat > evaluation.sh`.
- A typical evaluation.sh for a Python project looks like:
  ```
  #!/bin/bash
  set -e
  pip install -e ".[dev]" 2>/dev/null || pip install -e . 2>/dev/null || true
  pytest tests/test_specific.py::TestClass::test_method -xvs
  ```

Begin by quickly exploring the repository structure."""
    
    def _call_claude_with_tools(self, system_prompt: str):
        """Call Claude with tool definitions"""
        tools = [
            {
                "name": "bash",
                "description": "Execute bash commands in the repository directory. Use this to explore files, install dependencies, run tests, etc. Keep commands focused and brief.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The bash command to execute"
                        }
                    },
                    "required": ["command"]
                }
            },
            {
                "name": "switch-to-resolved",
                "description": "Apply the fix patch to switch the repository to the FIXED state (where tests should pass).",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "switch-to-bug",
                "description": "Revert the fix patch to switch the repository to the BUGGY state (where tests should fail).",
                "input_schema": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "submit_eval_script",
                "description": "Submit the final evaluation.sh script. This is how you deliver your solution. The script will be validated automatically in both buggy and fixed states.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "script_content": {
                            "type": "string",
                            "description": "The complete content of evaluation.sh (must start with #!/bin/bash)"
                        }
                    },
                    "required": ["script_content"]
                }
            }
        ]
        
        messages = self.conversation_history if self.conversation_history else [
            {"role": "user", "content": "Start building the environment. Explore the repository briefly, then write and submit evaluation.sh."}
        ]
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=system_prompt,
            tools=tools,
            messages=messages
        )
        
        return response
    
    def _execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        workspace_dir: Path,
        fix_patch: str
    ) -> str:
        """Execute a tool and return the result"""
        repo_dir = workspace_dir / "repo"
        
        if tool_name == "bash":
            command = tool_input.get("command", "")
            logger.info(f"Executing bash: {command[:200]}")
            
            try:
                result = subprocess.run(
                    command,
                    shell=True,
                    cwd=repo_dir,
                    capture_output=True,
                    timeout=120,
                    text=True
                )
                output = f"Exit code: {result.returncode}\n"
                if result.stdout:
                    output += f"STDOUT:\n{result.stdout[:3000]}\n"
                if result.stderr:
                    output += f"STDERR:\n{result.stderr[:2000]}\n"
                return output
            except subprocess.TimeoutExpired:
                return "Error: Command timed out after 120 seconds"
            except Exception as e:
                return f"Error executing command: {e}"
        
        elif tool_name == "switch-to-resolved":
            try:
                abs_repo_dir = repo_dir.resolve()
                # First revert any existing changes, then apply patches
                subprocess.run(
                    "git checkout -- .",
                    shell=True,
                    cwd=abs_repo_dir,
                    capture_output=True
                )
                # Re-apply test patch
                self._apply_patch(abs_repo_dir, workspace_dir / "test.patch", "test")
                # Apply fix patch
                self._apply_patch(abs_repo_dir, workspace_dir / "fix.patch", "fix")
                return "Successfully switched to FIXED state (test + fix patches applied)"
            except Exception as e:
                return f"Error switching to fixed state: {e}"
        
        elif tool_name == "switch-to-bug":
            try:
                abs_repo_dir = repo_dir.resolve()
                # Clean checkout and re-apply test patch only
                subprocess.run(
                    "git checkout -- .",
                    shell=True,
                    cwd=abs_repo_dir,
                    capture_output=True
                )
                # Re-apply test patch
                self._apply_patch(abs_repo_dir, workspace_dir / "test.patch", "test")
                return "Successfully switched to BUGGY state (only test patch applied, no fix)"
            except Exception as e:
                return f"Error switching to buggy state: {e}"
        
        return f"Unknown tool: {tool_name}"
    
    def _detect_hacking(self, script_content: str) -> bool:
        """
        Step 4: In-loop Hacking Detection
        Simple heuristic check - if script ONLY uses grep/sed/awk without test runners
        """
        logger.info("Step 4: In-loop Hacking Detection")
        
        # Quick heuristic: if the script contains common test runners, it's likely valid
        test_runners = ['pytest', 'python -m pytest', 'python -m unittest', 'tox', 'nosetests',
                       'npm test', 'cargo test', 'go test', 'mvn test', 'make test']
        has_test_runner = any(runner in script_content for runner in test_runners)
        
        # Check for hacking patterns (only text matching, no actual execution)
        hacking_patterns = [r'grep.*return\|exit', r'awk.*print.*exit']
        has_hacking = False
        
        lines = script_content.split('\n')
        non_comment_lines = [l.strip() for l in lines if l.strip() and not l.strip().startswith('#')]
        
        # If the script ONLY does grep/cat/diff on source files without running tests
        if not has_test_runner:
            grep_only = all(
                any(cmd in line for cmd in ['grep', 'cat', 'diff', 'echo', 'if', 'then', 'fi', 'else', 'exit'])
                for line in non_comment_lines
                if line and not line.startswith('set ') and not line.startswith('cd ')
                and not line.startswith('#!/')
            )
            if grep_only and len(non_comment_lines) > 2:
                logger.warning("Script appears to use only text matching without running actual tests")
                return True
        
        return False
    
    def _validate_script(self, workspace_dir: Path, fix_patch: str) -> Tuple[int, int]:
        """
        Step 3: Iterative Validation
        Run evaluation.sh in both buggy and fixed states
        
        Returns:
            Tuple of (buggy_exit_code, fixed_exit_code)
        """
        repo_dir = workspace_dir.resolve() / "repo"
        eval_script = workspace_dir.resolve() / "evaluation.sh"
        
        # Make script executable
        eval_script.chmod(0o755)
        
        # Test in BUGGY state (test patch applied, fix NOT applied)
        subprocess.run("git checkout -- .", shell=True, cwd=repo_dir, capture_output=True)
        self._apply_patch(repo_dir, workspace_dir / "test.patch", "test")
        
        logger.info("Testing in BUGGY state...")
        try:
            buggy_result = subprocess.run(
                f"bash '{eval_script}'",
                shell=True,
                cwd=repo_dir,
                capture_output=True,
                timeout=300
            )
            buggy_exit_code = buggy_result.returncode
            if buggy_result.stderr:
                logger.debug(f"Buggy stderr: {buggy_result.stderr.decode()[:500]}")
        except subprocess.TimeoutExpired:
            buggy_exit_code = 1  # Treat timeout as failure
        logger.info(f"Buggy state exit code: {buggy_exit_code}")
        
        # Test in FIXED state (test patch + fix patch applied)
        subprocess.run("git checkout -- .", shell=True, cwd=repo_dir, capture_output=True)
        self._apply_patch(repo_dir, workspace_dir / "test.patch", "test")
        self._apply_patch(repo_dir, workspace_dir / "fix.patch", "fix")
        
        logger.info("Testing in FIXED state...")
        try:
            fixed_result = subprocess.run(
                f"bash '{eval_script}'",
                shell=True,
                cwd=repo_dir,
                capture_output=True,
                timeout=300
            )
            fixed_exit_code = fixed_result.returncode
            if fixed_result.stderr:
                logger.debug(f"Fixed stderr: {fixed_result.stderr.decode()[:500]}")
        except subprocess.TimeoutExpired:
            fixed_exit_code = 1  # Treat timeout as failure
        logger.info(f"Fixed state exit code: {fixed_exit_code}")
        
        return buggy_exit_code, fixed_exit_code
