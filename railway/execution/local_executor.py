"""
Local Executor — runs Claude Code sessions locally using subprocess.
Replaces the M2 session_manager + recovery_engine + worktree_manager.
Uses git worktrees for parallel isolation, subprocess for execution (no tmux).
"""
import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import uuid
from typing import Optional

logger = logging.getLogger(__name__)

# Timeout per complexity in seconds
COMPLEXITY_TIMEOUTS = {
    'Simple': 600,
    'Medium': 1500,
    'Complex': 2400,
}

WORKSPACE = os.getenv('WORKSPACE_PATH', os.path.expanduser('~/deltanode-workspace'))
MAX_SESSIONS = int(os.getenv('MAX_SESSIONS', 3))

# In-memory session tracking
_active_sessions: dict = {}


class WorktreeManager:
    """Manages git worktrees for isolated parallel execution."""

    def __init__(self, workspace: str):
        self.workspace = workspace

    def create_worktree(self, repo_name: str, session_id: str) -> str:
        """Create an isolated git worktree for a session."""
        repo_path = os.path.join(self.workspace, repo_name)
        worktree_path = os.path.join(self.workspace, f'{repo_name}-wt-{session_id}')

        if not os.path.exists(repo_path):
            logger.error(f'Repo not found: {repo_path}')
            return ''

        try:
            # Pull latest main
            subprocess.run(
                ['git', 'pull', 'origin', 'main'],
                cwd=repo_path, capture_output=True, timeout=30
            )

            # Create worktree on a new branch
            branch_name = f'agent/{session_id[:8]}'
            subprocess.run(
                ['git', 'worktree', 'add', '-b', branch_name, worktree_path, 'main'],
                cwd=repo_path, check=True, capture_output=True, timeout=30
            )

            logger.info(f'Worktree created: {worktree_path} on branch {branch_name}')
            return worktree_path

        except subprocess.CalledProcessError as e:
            logger.error(f'Failed to create worktree: {e}')
            return ''

    def remove_worktree(self, worktree_path: str):
        """Remove a git worktree after session completes."""
        parent = worktree_path.rsplit('-wt-', 1)[0]

        try:
            subprocess.run(
                ['git', 'worktree', 'remove', '--force', worktree_path],
                cwd=parent, capture_output=True, timeout=15
            )
            logger.info(f'Worktree removed: {worktree_path}')
        except Exception as e:
            logger.warning(f'Could not remove worktree {worktree_path}: {e}')


class LocalExecutor:
    """Executes Claude Code tasks locally with retry logic and worktree isolation."""

    def __init__(self, workspace: Optional[str] = None):
        self.workspace = workspace or WORKSPACE
        self.worktree_mgr = WorktreeManager(self.workspace)
        os.makedirs(self.workspace, exist_ok=True)

    async def execute(
        self,
        spec_brief: str,
        context_package: str,
        project: str,
        session_id: Optional[str] = None,
        complexity: str = 'Medium',
        max_attempts: int = 3,
    ) -> dict:
        """
        Execute a Claude Code task with retry logic and git worktree isolation.

        Returns:
            {output, files_changed, tests_passed, annotations, session_id, attempts}
        """
        if session_id is None:
            session_id = str(uuid.uuid4())[:8]

        if len(_active_sessions) >= MAX_SESSIONS:
            return {
                'output': f'All {MAX_SESSIONS} session slots busy. Retry later.',
                'files_changed': [],
                'tests_passed': False,
                'annotations': [],
                'session_id': session_id,
            }

        _active_sessions[session_id] = {'project': project, 'status': 'running'}

        try:
            result = await self._execute_with_retry(
                spec_brief=spec_brief,
                context_package=context_package,
                project=project,
                session_id=session_id,
                complexity=complexity,
                max_attempts=max_attempts,
            )
            result['session_id'] = session_id
            return result
        finally:
            _active_sessions.pop(session_id, None)

    async def _execute_with_retry(
        self,
        spec_brief: str,
        context_package: str,
        project: str,
        session_id: str,
        complexity: str,
        max_attempts: int,
    ) -> dict:
        """Execute with up to max_attempts retries."""
        previous_errors = []

        for attempt in range(1, max_attempts + 1):
            logger.info(f'[LOCAL-EXEC] Attempt {attempt}/{max_attempts} for session {session_id}')

            result = await self._single_attempt(
                spec_brief=spec_brief,
                context_package=context_package,
                project=project,
                session_id=session_id,
                complexity=complexity,
                attempt=attempt,
                previous_errors=previous_errors,
            )

            if result.get('success'):
                return {
                    'output': result['output'],
                    'annotations': result.get('annotations', []),
                    'files_changed': result.get('files_changed', []),
                    'tests_passed': result.get('tests_passed', False),
                    'attempts': attempt,
                }

            error_summary = result.get('error', 'Unknown error')
            previous_errors.append(f'Attempt {attempt}: {error_summary[:200]}')
            logger.warning(f'[LOCAL-EXEC] Attempt {attempt} failed: {error_summary[:100]}')

            if attempt < max_attempts:
                await asyncio.sleep(10)

        # All attempts failed
        return {
            'output': f'All {max_attempts} attempts failed.\n\nErrors:\n' + '\n'.join(previous_errors),
            'annotations': [],
            'files_changed': [],
            'tests_passed': False,
            'attempts': max_attempts,
            'all_failed': True,
        }

    async def _single_attempt(
        self,
        spec_brief: str,
        context_package: str,
        project: str,
        session_id: str,
        complexity: str,
        attempt: int,
        previous_errors: list,
    ) -> dict:
        """Execute a single Claude Code headless session attempt."""
        # Project name = directory name (generic mapping)
        repo_name = project
        worktree_path = None
        timeout_secs = COMPLEXITY_TIMEOUTS.get(complexity, 1500)

        try:
            # Create git worktree for isolation
            worktree_path = self.worktree_mgr.create_worktree(repo_name, session_id)
            if not worktree_path:
                return {'success': False, 'error': f'Failed to create git worktree for {repo_name}'}

            # Build the prompt
            prompt = self._build_prompt(spec_brief, context_package, project, complexity, attempt, previous_errors)

            # Build Claude Code command
            cmd = [
                'claude',
                '-p', prompt,
                '--output-format', 'json',
                '--dangerously-skip-permissions',
            ]

            logger.info(f'[LOCAL-EXEC] Starting Claude Code in {worktree_path} (timeout={timeout_secs}s)')

            # Use Max subscription auth, not API key
            env = {**os.environ}
            env.pop('ANTHROPIC_API_KEY', None)

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=worktree_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout_secs
            )

            stdout_text = stdout.decode('utf-8', errors='replace') if stdout else ''
            stderr_text = stderr.decode('utf-8', errors='replace') if stderr else ''

            if proc.returncode != 0:
                error_msg = stderr_text[:500] or f'Claude Code exited with code {proc.returncode}'
                logger.error(f'[LOCAL-EXEC] Claude Code failed: {error_msg}')
                return {'success': False, 'error': error_msg}

            # Parse JSON output
            output_text = self._parse_claude_output(stdout_text)

            return {
                'success': True,
                'output': output_text,
                'annotations': self._extract_annotations(output_text),
                'files_changed': self._extract_files(output_text, worktree_path),
                'tests_passed': self._detect_tests_passed(output_text),
            }

        except asyncio.TimeoutError:
            logger.error(f'[LOCAL-EXEC] Claude Code timed out after {timeout_secs}s')
            try:
                proc.kill()
                await proc.wait()
            except Exception:
                pass
            return {'success': False, 'error': f'Session timed out after {timeout_secs}s'}

        except Exception as e:
            logger.error(f'[LOCAL-EXEC] Attempt {attempt} exception: {e}')
            return {'success': False, 'error': str(e)}

        finally:
            if worktree_path:
                self.worktree_mgr.remove_worktree(worktree_path)

    def _build_prompt(
        self,
        brief: str,
        context: str,
        project: str,
        complexity: str,
        attempt: int,
        errors: list,
    ) -> str:
        """Build the Claude Code prompt."""
        if attempt == 1:
            retry_note = ''
        elif attempt == 2:
            retry_note = f'\n\nPREVIOUS ATTEMPT FAILED:\n{errors[-1]}\n\nPlease avoid the same approach.'
        else:
            retry_note = (
                f'\n\nTWO PREVIOUS ATTEMPTS FAILED:\n'
                + '\n'.join(errors)
                + '\n\nFocus on minimum viable implementation that satisfies the success criteria only.'
            )

        prompt = f"""DeltaNode Agent Task — Attempt {attempt}/3
Project: {project} | Complexity: {complexity}

SPEC BRIEF:
{brief}

CONTEXT PACKAGE:
{context}{retry_note}

INSTRUCTIONS:
1. Read CLAUDE.md in this project root first if it exists
2. Write tests before implementation
3. Work on a feature branch — never commit to main
4. Make atomic commits with clear messages
5. Annotate key decisions with // DECISION: reason
6. Run tests and fix until passing
7. End your response with: "Implementation complete. Tests passing. Committed to branch [name]."

Begin now."""

        return prompt

    def _parse_claude_output(self, stdout_text: str) -> str:
        """Parse JSON output from Claude Code headless mode."""
        stdout_stripped = stdout_text.strip()
        if not stdout_stripped:
            return stdout_text

        # Handle NDJSON (multiple JSON objects, one per line)
        lines = stdout_stripped.split('\n')
        if len(lines) > 1:
            result_text = None
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict) and obj.get('type') == 'result':
                        result_text = obj.get('result', '')
                        break
                except (json.JSONDecodeError, TypeError):
                    continue
            if result_text is not None:
                return result_text

        # Single JSON object
        try:
            data = json.loads(stdout_stripped)
            if isinstance(data, dict):
                if 'result' in data:
                    return data['result']
                return data.get('text', data.get('content', stdout_text))
            if isinstance(data, list):
                parts = []
                for item in data:
                    if isinstance(item, dict):
                        if item.get('type') == 'result':
                            return item.get('result', str(item))
                        parts.append(item.get('text', item.get('content', str(item))))
                    else:
                        parts.append(str(item))
                return '\n'.join(parts)
            return stdout_text
        except (json.JSONDecodeError, TypeError):
            return stdout_text

    def _extract_annotations(self, output: str) -> list:
        return [line.strip() for line in output.split('\n')
                if '// DECISION:' in line or '[CONTEXT GAP:' in line][:10]

    def _extract_files(self, output: str, worktree: str) -> list:
        """Extract changed files from git or Claude's output text."""
        try:
            result = subprocess.run(
                ['git', 'diff', '--name-only', 'main...HEAD'],
                cwd=worktree, capture_output=True, text=True, timeout=10
            )
            files = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
            if files:
                return files[:20]

            result = subprocess.run(
                ['git', 'diff', '--name-only', 'HEAD~1', 'HEAD'],
                cwd=worktree, capture_output=True, text=True, timeout=10
            )
            files = [f.strip() for f in result.stdout.strip().split('\n') if f.strip()]
            if files:
                return files[:20]
        except Exception:
            pass

        # Fallback: parse file paths from output
        file_patterns = re.findall(
            r'[`|]([a-zA-Z][\w\-./]*\.(?:ts|tsx|js|jsx|py|json|md|sql|yml|yaml|sh))[`|]',
            output
        )
        if file_patterns:
            seen = set()
            unique = []
            for f in file_patterns:
                if f not in seen and '/' in f:
                    seen.add(f)
                    unique.append(f)
            if unique:
                return unique[:20]

        return []

    def _detect_tests_passed(self, output: str) -> bool:
        output_lower = output.lower()

        # Check for explicit failure signals first
        failing_match = re.search(r'(\d+) failing', output_lower)
        if failing_match and int(failing_match.group(1)) > 0:
            return False

        # Mocha/Jest: "X passing"
        passing_match = re.search(r'(\d+) passing', output_lower)
        if passing_match and int(passing_match.group(1)) > 0:
            return True

        # Vitest: "Tests X passed"
        if re.search(r'tests?\s+\d+\s+passed', output_lower):
            return True

        # Checkmarks
        if '\u2713' in output or '\u2714' in output:
            if 'fail' not in output_lower and 'error' not in output_lower.split('decision')[-1]:
                return True

        # Natural language
        if re.search(r'tests?\s+pass(ing|ed)?', output_lower):
            return True

        if 'implementation complete' in output_lower and 'test' in output_lower:
            return True

        if 'tests complete' in output_lower:
            return True

        return False


# Module-level singleton for convenience
_executor: Optional[LocalExecutor] = None


def _get_executor() -> LocalExecutor:
    global _executor
    if _executor is None:
        _executor = LocalExecutor()
    return _executor


async def execute(
    spec_brief: str,
    context_package: str,
    project: str,
    session_id: Optional[str] = None,
    complexity: str = 'Medium',
) -> dict:
    """
    Convenience function — execute a Claude Code task locally.

    Returns:
        {output, files_changed, tests_passed, annotations, session_id}
    """
    executor = _get_executor()
    return await executor.execute(
        spec_brief=spec_brief,
        context_package=context_package,
        project=project,
        session_id=session_id,
        complexity=complexity,
    )
