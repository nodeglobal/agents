import os
import logging
from graph.state import AgentState
from execution.local_executor import execute

logger = logging.getLogger(__name__)


async def run_developer(state: AgentState) -> dict:
    """Developer Agent — executes Claude Code task locally via local_executor."""

    project = state.get('project', 'general')
    complexity = state.get('spec_complexity', 'Medium')
    thread_id = state.get('thread_id', 'unknown')
    session_id = thread_id[:8]

    logger.info(f"[DEV-AGENT] Starting for session={session_id} project={project} complexity={complexity}")

    # Build retry context if this is a retry
    retry_ctx = ''
    if state.get('iteration', 0) > 0 and state.get('validation_notes'):
        retry_ctx = f"\n\nPREVIOUS VALIDATION ISSUES TO FIX:\n{state['validation_notes']}\n\nIssues: {', '.join(state.get('validation_issues', []))}"

    spec_brief = state.get('spec_brief', '')
    context_package = (state.get('context_package') or 'No context available.') + retry_ctx

    # Execute locally — no HTTP, no M2
    result = await execute(
        spec_brief=spec_brief,
        context_package=context_package,
        project=project,
        session_id=session_id,
        complexity=complexity,
    )

    output = result.get('output', '')
    tests_passed = result.get('tests_passed', False)
    files_changed = result.get('files_changed', [])
    annotations = result.get('annotations', [])

    logger.info(f"[DEV-AGENT] Session {session_id} complete — tests_passed={tests_passed} files={files_changed}")

    return {
        'build_output': output,
        'build_annotations': annotations,
        'files_changed': files_changed,
        'tests_passed': tests_passed,
        'messages': [{'role': 'developer_agent', 'content': output, 'session_id': session_id}],
    }


def _error_result(message: str) -> dict:
    """Build a standard error result dict."""
    return {
        'build_output': f'ERROR: {message}',
        'build_annotations': [],
        'files_changed': [],
        'tests_passed': False,
        'error': message,
        'messages': [{'role': 'developer_agent', 'content': f'ERROR: {message}'}],
    }
