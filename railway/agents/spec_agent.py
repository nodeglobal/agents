import os
import anthropic
from graph.state import AgentState
from memory.mem0_client import search_memory
from notifications.discord import notifier

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

SYSTEM_PROMPT = """You are the Spec Agent for an autonomous development system.

YOUR ONLY JOB: Receive a task. Produce a structured brief. Wait for approval.

OUTPUT FORMAT — use exactly this every time:
UNDERSTANDING: [what you understand the task to be]
AMBIGUITIES:   [every missing piece — be exhaustive, not lazy]
APPROACH:      [proposed method in plain language — specific, not vague]
SUCCESS:       [what done looks like — measurable and specific]
RISKS:         [dependencies, blockers, potential failure points]
COMPLEXITY:    [Simple / Medium / Complex]
MCPS_NEEDED:   [which MCP servers the Developer Agent should activate]

UNIVERSAL RULE: Confidence below 80% = STOP and ask. Never assume. Never guess. Flag it."""

async def run_spec(state: AgentState) -> dict:
    memories = search_memory(state['raw_task'], project=state.get('project','general'), limit=5)

    mem_ctx = ''
    if memories:
        mem_ctx = '\n\nRelevant context:\n' + '\n'.join(
            f"- {m.get('memory','')}" for m in memories
        )

    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{'role':'user','content':
            f"Project: {state.get('project','general')}\nTask: {state['raw_task']}{mem_ctx}\n\nProduce the brief now."}]
    )

    brief = response.content[0].text

    complexity = 'Simple'
    brief_lower = brief.lower()
    if any(w in brief_lower for w in ['complex','architecture','refactor','integrate','design','system']):
        complexity = 'Complex'
    elif any(w in brief_lower for w in ['medium','moderate','several','multiple']):
        complexity = 'Medium'

    await notifier.send_spec_brief(
        thread_id=state['thread_id'],
        project=state.get('project','general'),
        brief=brief,
        complexity=complexity
    )

    return {
        'spec_brief': brief,
        'spec_approved': False,
        'spec_clarifications': [],
        'spec_complexity': complexity,
        'memory_hits': memories,
        'messages': [{'role':'spec_agent','content':brief,'complexity':complexity}]
    }
