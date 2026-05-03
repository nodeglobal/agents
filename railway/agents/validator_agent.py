import os
import re
import logging
import anthropic
from graph.state import AgentState

logger = logging.getLogger(__name__)
from memory.mem0_client import search_memory, add_memory
from notifications.discord import notifier

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

SYSTEM_PROMPT = """You are the Validator Agent for the DeltaNode agent stack.
Your job is to catch real problems — not to be adversarial for the sake of it.

You receive a summary of the Developer's work, not the full code diff. Judge based on what you CAN see.

IMPORTANT CONTEXT:
- The Developer runs Claude Code on a real codebase. It writes real files, runs real tests.
- "Tests passed: True" means actual test suites ran and passed on the machine.
- You see a summary of changes, not the raw diff. Do NOT penalize for "cannot verify code" — that is a limitation of your input, not a problem with the work.
- Files listed in "Files changed" were actually modified on disk.

CHECK FOR:
1. Does the described output address the success criteria from the Spec brief?
2. Were tests written and do they pass?
3. Obvious security concerns mentioned in the output (hardcoded secrets, missing auth)
4. Pattern violations mentioned — wrong REST prefix, callbacks instead of async/await
5. Scope creep — files changed outside what the task required
6. Contradictions with memory standards

DO NOT penalize for:
- Not being able to see the actual code (you never can)
- Using a framework that fits the project (e.g. FastAPI for Python projects is correct)
- Minor style preferences when tests pass

OUTPUT FORMAT — use EXACTLY this:
SCORE: [0-100]
VERDICT: APPROVED or BLOCKED
CRITICAL_ISSUES: [list or NONE]
MAJOR_ISSUES: [list or NONE]
MINOR_ISSUES: [list or NONE]
MEMORY_CONTRADICTIONS: [list or NONE]
NOTES: [what must change if blocked / what to watch if approved]

SCORING GUIDE:
- Tests pass + task addressed + no security issues = 80+ (APPROVED)
- Tests pass + minor concerns = 75-79 (APPROVED)
- Tests fail or missing = 50-74 (BLOCKED)
- No meaningful work done or critical security issue = 0-49 (BLOCKED)

HARD RULE: Below 75 = BLOCKED."""

async def run_validator(state: AgentState) -> dict:
    contradiction_check = search_memory(
        state.get('build_output','')[:500],
        project=state.get('project','general'),
        limit=5
    )

    mem_ctx = ''
    if contradiction_check:
        mem_ctx = '\n\nKnown standards:\n' + '\n'.join(
            f"- {m.get('memory','')}" for m in contradiction_check
        )

    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{'role':'user','content':
            f"Spec Brief:\n{state.get('spec_brief','N/A')}\n\nDeveloper Output:\n{state.get('build_output','No output')}\n\nAnnotations:\n{chr(10).join(state.get('build_annotations',['None']))}\n\nFiles: {', '.join(state.get('files_changed',['Unknown']))}\nTests passed: {state.get('tests_passed',False)}{mem_ctx}\n\nReview adversarially."}]
    )

    validation_text = response.content[0].text

    score = 0
    match = re.search(r'SCORE:\s*(\d+)', validation_text)
    if match:
        score = min(100, max(0, int(match.group(1))))

    # If tests passed and there are real file changes, floor the score at 70
    # This prevents the validator from blocking work that demonstrably runs
    tests_passed = state.get('tests_passed', False)
    has_files = len(state.get('files_changed', [])) > 0
    if tests_passed and has_files and score < 70:
        logger.info(f'[VALIDATOR] Score boosted from {score} to 70 (tests_passed=True, files_changed=True)')
        score = 70

    approved = score >= 75

    issues = []
    for line in validation_text.split('\n'):
        if 'CRITICAL_ISSUES:' in line or 'MAJOR_ISSUES:' in line:
            issue_text = line.split(':',1)[-1].strip()
            if issue_text and issue_text.upper() != 'NONE':
                issues.append(issue_text)

    iteration = state.get('iteration',0) + 1

    # Write successful decisions to memory
    if approved:
        for annotation in state.get('build_annotations',[])[:3]:
            if '// DECISION:' in annotation:
                decision = annotation.replace('// DECISION:','').strip()
                add_memory(decision, project=state.get('project','general'))

        # Send completion notification
        await notifier.send_task_complete(
            thread_id=state['thread_id'],
            project=state.get('project','general'),
            score=score,
            files=state.get('files_changed',[])
        )

    # Send escalation if max iterations reached
    elif iteration >= 3:
        await notifier.send_escalation(
            thread_id=state['thread_id'],
            project=state.get('project','general'),
            failure_summary=f"Score: {score}/100. Issues: {'; '.join(issues[:3])}"
        )

    return {
        'validation_score': score,
        'validation_notes': validation_text,
        'validation_issues': issues,
        'approved': approved,
        'iteration': iteration,
        'messages': [{'role':'validator_agent','content':validation_text,'score':score,'approved':approved}]
    }
