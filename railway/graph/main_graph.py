from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from graph.state import AgentState
from agents.spec_agent import run_spec
from agents.research_agent import run_research
from agents.developer_agent import run_developer
from agents.validator_agent import run_validator
import logging

logger = logging.getLogger(__name__)
MAX_ITERATIONS = 3

def route_after_spec(state: AgentState) -> str:
    approved = state.get('spec_approved')
    logger.info(f"[GRAPH] route_after_spec: spec_approved={approved} thread={state.get('thread_id', 'unknown')[:8]}")
    if approved:
        logger.info(f"[GRAPH] Routing to research")
        return 'research'
    else:
        logger.info(f"[GRAPH] spec_approved is falsy, routing to END — pipeline stops here")
        return END

def route_after_validation(state: AgentState) -> str:
    score = state.get('validation_score', 0)
    iteration = state.get('iteration', 0)
    logger.info(f"[GRAPH] route_after_validation: score={score} iteration={iteration} thread={state.get('thread_id', 'unknown')[:8]}")
    if score >= 75:
        logger.info(f"[GRAPH] Score >= 75, routing to END (approved)")
        return END
    if iteration >= MAX_ITERATIONS:
        logger.warning(f"[GRAPH] Max iterations ({MAX_ITERATIONS}) reached for {state.get('thread_id', 'unknown')[:8]}")
        return END
    logger.info(f"[GRAPH] Score < 75, routing back to developer for retry")
    return 'developer'

workflow = StateGraph(AgentState)
workflow.add_node('spec', run_spec)
workflow.add_node('research', run_research)
workflow.add_node('developer', run_developer)
workflow.add_node('validator', run_validator)

workflow.set_entry_point('spec')
workflow.add_conditional_edges('spec', route_after_spec, {'research':'research', END:END})
workflow.add_edge('research', 'developer')
workflow.add_edge('developer', 'validator')
workflow.add_conditional_edges('validator', route_after_validation, {END:END, 'developer':'developer'})

checkpointer = MemorySaver()
agent_graph = workflow.compile(checkpointer=checkpointer, interrupt_after=['spec'])
