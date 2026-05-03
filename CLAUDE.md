# DeltaNode Dev Agents — Claude Code Execution Instructions

## Task Execution

When a task arrives, Claude Code executes it in an isolated git worktree.

### Steps

1. **Parse** the session_id and JSON payload
2. **Read the spec_brief** — task specification with UNDERSTANDING, APPROACH, SUCCESS criteria, RISKS
3. **Read the context_package** — memory context, patterns, constraints from the Research Agent
4. **Navigate to the project directory**
5. **Read the project's CLAUDE.md** if it exists in the project root
6. **Create a feature branch**: `agent/{session_id}`
7. **Write tests first** — always TDD
8. **Implement** the task per the spec_brief
9. **Run tests** and fix until passing
10. **Commit** with clear atomic messages — never commit to main
11. **Annotate** key decisions in code with `// DECISION: reason`

### Rules

- Always work on a feature branch, never main
- Write tests before implementation
- If the task is unclear, report `tests_passed: false` and explain in output
- If `iteration` > 0, the previous attempt was rejected — fix the issues listed in context_package
