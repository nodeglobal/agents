#!/bin/bash
set -e

GREEN='\033[0;32m'
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║${NC}     DeltaNode Agents — One-Click Install     ${CYAN}║${NC}"
echo -e "${CYAN}║${NC}     Autonomous AI Agent Workflow System      ${CYAN}║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""

# Check prerequisites
echo -e "${CYAN}Checking prerequisites...${NC}"

if ! command -v python3 &>/dev/null; then
    echo -e "${RED}✗ Python 3 not found. Install it first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Python 3 found"

if ! command -v git &>/dev/null; then
    echo -e "${RED}✗ Git not found. Install it first.${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Git found"

if ! command -v claude &>/dev/null; then
    echo -e "${RED}✗ Claude Code not found.${NC}"
    echo "  Install it: npm install -g @anthropic-ai/claude-code"
    echo "  Requires a Claude Pro or Max subscription."
    exit 1
fi
echo -e "${GREEN}✓${NC} Claude Code found"

# Setup
INSTALL_DIR="$(pwd)"
WORKSPACE="${WORKSPACE_PATH:-$HOME/deltanode-workspace}"

echo ""
echo -e "${CYAN}Setting up environment...${NC}"

# Create workspace
mkdir -p "$WORKSPACE"
echo -e "${GREEN}✓${NC} Workspace at $WORKSPACE"

# Create virtual environment
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
echo -e "${GREEN}✓${NC} Virtual environment ready"

# Install dependencies
pip install -q -r railway/requirements.txt
echo -e "${GREEN}✓${NC} Dependencies installed"

# Setup .env
if [ ! -f ".env" ]; then
    echo ""
    echo -e "${YELLOW}No .env file found. Let's set up your API key.${NC}"
    echo ""
    echo "  Get your Anthropic API key at: console.anthropic.com"
    echo ""
    read -p "  Paste your Anthropic API key (sk-ant-...): " API_KEY
    echo ""

    cat > .env << EOF
ANTHROPIC_API_KEY=$API_KEY
DISCORD_BOT_TOKEN=
DISCORD_CHANNEL_ID=
WORKSPACE_PATH=$WORKSPACE
PORT=8000
EOF
    echo -e "${GREEN}✓${NC} .env created"
else
    echo -e "${GREEN}✓${NC} .env already exists"
fi

# Create memory database directory
mkdir -p "$HOME/.deltanode"
echo -e "${GREEN}✓${NC} Memory database ready"

echo ""
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo -e "${GREEN}  DeltaNode Agents installed successfully!${NC}"
echo -e "${GREEN}══════════════════════════════════════════════${NC}"
echo ""
echo "  Start the agent system:"
echo ""
echo -e "    ${CYAN}source .venv/bin/activate${NC}"
echo -e "    ${CYAN}cd railway && python main.py${NC}"
echo ""
echo "  Then open: http://localhost:8000"
echo ""
echo "  Submit tasks from the web dashboard or via API:"
echo -e "    ${CYAN}curl -X POST http://localhost:8000/task \\${NC}"
echo -e "    ${CYAN}  -H 'Content-Type: application/json' \\${NC}"
echo -e "    ${CYAN}  -d '{\"task\": \"Add a health check endpoint\", \"project\": \"my-project\"}'${NC}"
echo ""
echo "  Docs: https://github.com/nodeglobal/deltanode-agents"
echo ""
