import os
import anthropic
from graph.state import AgentState
from memory.mem0_client import search_memory, get_all_for_project

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

DEFAULT_MCPS = ['filesystem', 'github']

SYSTEM_PROMPT = """You are the Research Agent for the DeltaNode agent stack.
You receive an approved Spec brief. Produce a context package for the Developer Agent.

YOUR JOB: Ground all work in verifiable, retrieved context. Never invent.

PRODUCE THIS STRUCTURE EXACTLY:
PAST_DECISIONS:    [relevant decisions from memory — cite each as [MEM]]
PATTERNS:          [established code/architecture patterns to follow]
CONSTRAINTS:       [hard limits, non-negotiables, known dependencies]
ACTIVE_MCPS:       [which MCP servers to activate — use project mapping]
CLAUDE_MD_RULES:   [most relevant CLAUDE.md rules for this project]
GAPS:              [context not found — state "No memory found for X"]
RECOMMENDATION:    [synthesis — concrete approach for Developer Agent to follow]

Citation rule: Every factual claim cites [MEM] or is marked [INFERRED].
Gap rule: Never fill gaps with invented context. State the gap explicitly.
UNIVERSAL RULE: Flag uncertainty with [UNCERTAIN]. Never guess."""

async def run_research(state: AgentState) -> dict:
    project = state.get('project','general')

    task_memories = search_memory(state['raw_task'], project=project, limit=8)
    project_memories = get_all_for_project(project)

    seen = {}
    for m in task_memories + project_memories:
        key = m.get('id', m.get('memory','')[:50])
        seen[key] = m
    all_memories = list(seen.values())[:15]

    memory_text = '\n'.join([
        f"[{m.get('metadata',{}).get('project','general')}] {m.get('memory','')}"
        for m in all_memories
    ]) or 'No memories found for this project yet.'

    active_mcps = DEFAULT_MCPS

    response = client.messages.create(
        model='claude-sonnet-4-20250514',
        max_tokens=3000,
        system=SYSTEM_PROMPT,
        messages=[{'role':'user','content':
            f"Spec Brief:\n{state['spec_brief']}\n\nProject: {project}\nComplexity: {state.get('spec_complexity','Medium')}\nActive MCPs available: {', '.join(active_mcps)}\n\nMemory:\n{memory_text}\n\nProduce the context package now."}]
    )

    return {
        'context_package': response.content[0].text,
        'memory_hits': all_memories,
        'messages': [{'role':'research_agent','content':response.content[0].text}]
    }
