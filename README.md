# DeltaNode Dev Agents

Autonomous AI agent workflow system powered by Claude Code. Submit a task in plain English, get production-ready code back — reviewed, tested, and on a feature branch.

## How it works

```
You describe a task
    ↓
Spec Agent writes a structured brief
    ↓
You approve (web dashboard or API)
    ↓
Research Agent pulls context from memory
    ↓
Developer Agent executes via Claude Code (isolated git worktree)
    ↓
Validator Agent scores the output (0-100)
    ↓
Score ≥ 75 → Approved. Score < 75 → Retry (up to 3x)
```

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/deploy/deltanode-dev-agents?referralCode=genclik&utm_medium=integration&utm_source=template&utm_campaign=generic)

**6 specialized agents:**

| Agent | Role |
|-------|------|
| **Spec** | Writes structured brief with success criteria and risk analysis |
| **Research** | Pulls relevant context from persistent memory |
| **Developer** | Executes code via Claude Code in isolated worktrees |
| **Validator** | Adversarial review — scores 0-100, blocks below 75 |
| **Update** | Weekly scan for stack changes (requires approval) |
| **Self-Improve** | Analyzes past outcomes, recommends workflow improvements |

## Quick start

**Prerequisites:** Python 3.11+, Git, [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (requires Claude Pro or Max subscription)

```bash
git clone https://github.com/nodeglobal/deltanode-agents.git
cd deltanode-agents
bash install.sh
```

The installer checks prerequisites, creates a virtual environment, installs dependencies, and prompts for your Anthropic API key.

Then start:

```bash
source .venv/bin/activate
cd railway && python main.py
```

Open **http://localhost:8000** for the web dashboard.

## Submit a task

**From the dashboard:** Open http://localhost:8000, type your task, pick a project, click Submit.

**From the API:**

```bash
# Submit a task
curl -X POST http://localhost:8000/task \
  -H 'Content-Type: application/json' \
  -d '{"task": "Add a health check endpoint that returns uptime", "project": "my-project"}'

# Approve the spec
curl -X POST http://localhost:8000/approve/{thread_id}

# Check status
curl http://localhost:8000/status/{thread_id}
```

**From Claude Code (MCP):**

```bash
# Add to your Claude Code config
claude mcp add deltanode-agents bash ./mcp-serve.sh
```

Then ask Claude Code: "Submit a task to deltanode-agents: add a health check endpoint"

## Architecture

Built on [LangGraph](https://github.com/langchain-ai/langgraph) for orchestration with human-in-the-loop approval gates.

- **Spec → Research → Develop → Validate** pipeline with conditional retry
- **Git worktree isolation** — each task gets its own branch, no race conditions
- **Validation threshold** — code scoring below 75/100 gets automatically retried
- **Persistent memory** — SQLite-based, agents learn from past decisions
- **Self-improvement loop** — weekly analysis of outcomes and failure patterns

## Configuration

Edit `config.yaml` to add your projects and customize settings:

```yaml
projects:
  - name: my-app
    mcps:
      - filesystem
      - github

agents:
  max_iterations: 3
  validation_threshold: 75
```

## Project setup

Your projects should be git repositories inside the workspace directory:

```
~/deltanode-workspace/
├── my-app/          # git repo
├── another-project/ # git repo
└── ...
```

## Discord notifications (optional)

To get task notifications on Discord:

1. Create a Discord bot at discord.com/developers
2. Add the bot to your server
3. Set `DISCORD_BOT_TOKEN` and `DISCORD_CHANNEL_ID` in `.env`

Without Discord, use the web dashboard at http://localhost:8000.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | Yes | — | Your Anthropic API key |
| `WORKSPACE_PATH` | No | `~/deltanode-workspace` | Where your project repos live |
| `PORT` | No | `8000` | Server port |
| `DISCORD_BOT_TOKEN` | No | — | Discord bot token (optional) |
| `DISCORD_CHANNEL_ID` | No | — | Discord channel for notifications |

## How validation works

The Validator Agent scores every output 0-100:

- **Tests written and passing?** (major factor)
- **Addresses spec success criteria?**
- **Security issues?** (hardcoded secrets, missing auth)
- **Pattern violations?** (conventions, async/await)
- **Scope creep?** (did it do more than asked?)

Score ≥ 75 = **Approved** → ready to merge

Score < 75 = **Blocked** → retries with feedback (up to 3 attempts)

3 failures = **Escalated** → needs human intervention

## Built by

[DeltaNode Global](https://deltanodeglobal.com) — AI consulting & implementation. We build production AI agent systems.

## License

MIT
