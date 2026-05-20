#!/bin/bash
# Run FastAPI & WebSockets simulation bridge

# Activate virtualenv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Set default DUCK_SIM_MODE to mock if not configured
export DUCK_SIM_MODE=${DUCK_SIM_MODE:-mock}
export BRIDGE_PORT=${BRIDGE_PORT:-8765}
export BRIDGE_HOST=${BRIDGE_HOST:-127.0.0.1}

echo "Starting Duck Agent Simulation Bridge in [${DUCK_SIM_MODE}] mode..."
uvicorn duck_agent_sim.main:app --reload --host "$BRIDGE_HOST" --port "$BRIDGE_PORT"
