#!/bin/bash

# Ensure we are in the repository root
cd "$(dirname "$0")/.."

echo "======================================================="
echo "  🦆 DUCK SIMULATOR + VOICE CONTROL SINGLE LAUNCHER 🦆  "
echo "======================================================="

# Function to clean up simulator on exit
cleanup() {
    echo -e "\n[*] Stopping background simulator bridge (PID: $SIM_PID)..."
    if [ ! -z "$SIM_PID" ]; then
        kill $SIM_PID 2>/dev/null
    fi
    if [ -f "bridge.pid" ]; then
        rm bridge.pid
    fi
    echo "[+] Done. Goodbye!"
    exit 0
}

# Trap Ctrl+C and exit signals
trap cleanup INT TERM EXIT

# Step 1: Start Simulator Bridge in the background
echo "[*] Launching MuJoCo Simulator Bridge in dynamic REAL mode..."
export DUCK_SIM_MODE=real
.venv/bin/mjpython -m uvicorn duck_agent_sim.main:app --host 127.0.0.1 --port 8765 > bridge_test.log 2>&1 &
SIM_PID=$!
echo $SIM_PID > bridge.pid
echo "[+] Simulator background process started (PID: $SIM_PID)."

# Step 2: Wait for bridge to become healthy
echo "[*] Waiting for simulator bridge to initialize (checking health endpoint)..."
READY=0
for i in {1..15}; do
    curl -s http://127.0.0.1:8765/health | grep -q "ok"
    if [ $? -eq 0 ]; then
        echo "[+] Simulator Bridge is online and healthy!"
        READY=1
        break
    fi
    sleep 1
done

if [ $READY -eq 0 ]; then
    echo "[!] Error: Simulator Bridge failed to start or respond in time."
    echo "Check 'bridge_test.log' for details."
    exit 1
fi

# Step 3: Run the local Voice Control in the foreground
echo "[*] Starting Voice Control Node..."
.venv/bin/python -m duck_agent_sim.agent.voice_control --url http://127.0.0.1:8765 --model tiny
