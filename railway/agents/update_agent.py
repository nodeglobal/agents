import os
import anthropic
from memory.mem0_client import search_memory, add_memory, log_agent_update
from notifications.discord import notifier
import datetime

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

SYSTEM_PROMPT = """You are the Update Agent for the DeltaNode agent stack.
Your job: keep every agent current with latest capabilities and patterns.

SEARCH AND MONITOR:
1. Claude Code latest updates and new capabilities
2. New Anthropic model releases or pricing changes
3. LangGraph release notes — new primitives or breaking changes
4. New MCP servers relevant to the user's projects
5. Agent performance issues from memory — recurring failures or gaps

PRODUCE:
STACK_CHANGES:    [what changed in underlying tools]
AGENT_UPDATES:    [specific proposed changes per agent — be precise]
NEW_MCPS:         [new MCP servers worth adding]
PERFORMANCE:      [patterns showing agent weaknesses from memory]
PRIORITY:         [Critical/High/Medium/Low for each change]
APPROVAL_NEEDED:  [list every change requiring owner approval]

HARD RULE: You NEVER update prompts autonomously.
Every proposed change requires explicit owner approval. Always."""

async def run_update_agent() -> dict:
    recent_issues = search_memory('validation failed blocked error retry', project='agents', limit=10)
    recent_updates = search_memory('updated agent prompt change', project='agents', limit=5)

    perf_ctx = ''
    if recent_issues:
        perf_ctx = '\nRecent performance patterns:\n' + '\n'.join(
            f"- {m.get('memory','')}" for m in recent_issues
        )

    update_history = ''
    if recent_updates:
        update_history = '\nRecent updates applied:\n' + '\n'.join(
            f"- {m.get('memory','')}" for m in recent_updates
        )

    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        tools=[{'type':'web_search_20250305','name':'web_search'}],
        messages=[{'role':'user','content':
            f"""Weekly update scan for DeltaNode Agent Stack.

Search for:
1. Latest Claude Code updates and new capabilities (past 7 days)
2. New Anthropic model releases or capability changes
3. LangGraph latest release notes{perf_ctx}{update_history}

Produce full update report."""}]
    )

    report = ''
    for block in response.content:
        if hasattr(block,'text'):
            report += block.text

    log_agent_update('Update Agent', f'Weekly scan completed {datetime.date.today()}')

    summary = report[:300] + '...' if len(report) > 300 else report
    await notifier.send_update_report(summary)

    return {'update_report': report, 'status': 'awaiting_approval'}
