from typing import TypedDict, Optional, List, Annotated
import operator

class AgentState(TypedDict):
    raw_task: str
    project: str
    spec_brief: Optional[str]
    spec_approved: bool
    spec_clarifications: List[str]
    spec_complexity: str
    context_package: Optional[str]
    memory_hits: List[dict]
    build_output: Optional[str]
    build_annotations: List[str]
    files_changed: List[str]
    tests_passed: bool
    validation_score: Optional[int]
    validation_notes: str
    validation_issues: List[str]
    approved: bool
    iteration: int
    thread_id: str
    messages: Annotated[List[dict], operator.add]
    error: Optional[str]
    session_id: Optional[str]
