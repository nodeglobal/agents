import os
import asyncio
import httpx
import json
import logging
import datetime
from memory.mem0_client import add_memory, search_memory

logger = logging.getLogger(__name__)

ANTHROPIC_API_KEY = os.getenv('ANTHROPIC_API_KEY', '')

RESEARCH_PROMPT = """You are the Self-Improvement Agent for the DeltaNode Agent Stack.
Your job: analyze past performance and research improvements that will increase
first-attempt success rate and reduce iteration counts.

Given the recent task outcomes and failure patterns below, produce a structured
improvement report covering these categories:

1. NEW MCP SERVERS: Recently released MCP servers for code quality, testing,
   deployment, monitoring that could benefit the stack.
2. CLAUDE CODE UPDATES: New CLI flags, modes, tool capabilities, subagent
   patterns that the stack should adopt.
3. PROMPT IMPROVEMENTS: Patterns from successful tasks that lead to higher
   validator scores. Anti-patterns from failures to avoid.
4. WORKFLOW CHANGES: Concrete changes to reduce iteration count and improve
   first-attempt success rate.
5. SKILL GAPS: From recent failures, identify missing knowledge areas that
   should be added to agent memory.

For each finding, assign a priority: Critical / High / Medium / Low.

Output as structured JSON:
{
  "findings": [
    {
      "category": "NEW MCP SERVERS | CLAUDE CODE UPDATES | PROMPT IMPROVEMENTS | WORKFLOW CHANGES | SKILL GAPS",
      "title": "short title",
      "description": "what and why",
      "action": "specific next step",
      "priority": "Critical | High | Medium | Low"
    }
  ],
  "summary": "1-2 sentence overall assessment"
}"""


async def run_self_improve() -> dict:
    """Weekly Self-Improvement Agent — researches and stores capability improvements."""
    logger.info('[SELF-IMPROVE] Starting weekly self-improvement scan')

    # 1. Search Mem0 for past outcomes and failure patterns
    past_outcomes = search_memory(
        'agent task outcomes failures improvements patterns',
        project='agents', limit=10
    )
    recent_failures = search_memory(
        'validation failed blocked error retry iteration',
        project='agents', limit=10
    )
    recent_improvements = search_memory(
        'self-improve finding recommendation capability',
        project='agents', limit=5
    )

    # Build context from memory
    outcomes_ctx = ''
    if past_outcomes:
        outcomes_ctx = '\n\nRecent task outcomes:\n' + '\n'.join(
            f"- {m.get('memory', '')}" for m in past_outcomes
        )

    failures_ctx = ''
    if recent_failures:
        failures_ctx = '\n\nRecent failure patterns:\n' + '\n'.join(
            f"- {m.get('memory', '')}" for m in recent_failures
        )

    prev_improvements = ''
    if recent_improvements:
        prev_improvements = '\n\nPrevious improvement findings (avoid duplicates):\n' + '\n'.join(
            f"- {m.get('memory', '')}" for m in recent_improvements
        )

    # 2. Call Claude API to research improvements
    user_message = (
        f"Weekly self-improvement scan for DeltaNode Agent Stack. "
        f"Date: {datetime.date.today().isoformat()}\n\n"
        f"Analyze the following context and produce improvement recommendations."
        f"{outcomes_ctx}{failures_ctx}{prev_improvements}\n\n"
        f"Research and produce the full improvement report as JSON."
    )

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                'https://api.anthropic.com/v1/messages',
                headers={
                    'x-api-key': ANTHROPIC_API_KEY,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={
                    'model': 'claude-sonnet-4-6',
                    'max_tokens': 4000,
                    'system': RESEARCH_PROMPT,
                    'messages': [{'role': 'user', 'content': user_message}],
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception as e:
        logger.error(f'[SELF-IMPROVE] Claude API call failed: {e}')
        return {'status': 'error', 'error': str(e)}

    # Extract text from response
    report_text = ''
    for block in data.get('content', []):
        if block.get('type') == 'text':
            report_text += block['text']

    # 3. Parse findings and store in Mem0
    findings = []
    try:
        # Extract JSON from response (may be wrapped in markdown code fences)
        json_text = report_text
        if '```json' in json_text:
            json_text = json_text.split('```json')[1].split('```')[0]
        elif '```' in json_text:
            json_text = json_text.split('```')[1].split('```')[0]
        parsed = json.loads(json_text.strip())
        findings = parsed.get('findings', [])
        summary = parsed.get('summary', '')
    except (json.JSONDecodeError, IndexError, KeyError) as e:
        logger.warning(f'[SELF-IMPROVE] Could not parse JSON from response: {e}')
        # Store raw report as fallback
        summary = report_text[:500]
        findings = []

    # 4. Store findings in Mem0 with timestamp
    timestamp = datetime.date.today().isoformat()
    add_memory(
        f"[{timestamp}] Self-Improve Agent: weekly scan completed. {summary}",
        project='agents'
    )

    high_priority_items = []
    for finding in findings:
        priority = finding.get('priority', 'Low')
        category = finding.get('category', 'UNKNOWN')
        title = finding.get('title', 'untitled')
        action = finding.get('action', '')

        memory_entry = (
            f"[{timestamp}] self-improve finding [{priority}] {category}: "
            f"{title}. Action: {action}"
        )
        add_memory(memory_entry, project='agents')

        # 5. Log high-priority items
        if priority in ('Critical', 'High'):
            high_priority_items.append(finding)
            logger.warning(
                f'[SELF-IMPROVE] {priority} finding: {title} — {action}'
            )
        else:
            logger.info(f'[SELF-IMPROVE] {priority} finding: {title}')

    logger.info(
        f'[SELF-IMPROVE] Scan complete. {len(findings)} findings, '
        f'{len(high_priority_items)} high-priority.'
    )

    return {
        'status': 'complete',
        'findings_count': len(findings),
        'high_priority_count': len(high_priority_items),
        'high_priority_items': high_priority_items,
        'summary': summary,
    }
