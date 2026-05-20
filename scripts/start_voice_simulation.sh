#!/bin/bash

# Ensure we are in the repository root
cd "$(dirname "$0")/.."

echo "======================================================="
echo "  🦆 DUCK SIMULATOR + VOICE CONTROL SINGLE LAUNCHER 🦆  "
echo "======================================================="

# Function to clean up simulator on exit
cleanup() {
    echo -e "\n[*] Stopping background monitor and voice control processes..."
    if [ ! -z "$LAUNCHER_PID" ]; then
        kill $LAUNCHER_PID 2>/dev/null
    fi
    pkill -f "duck_agent_sim.agent.voice_control" 2>/dev/null
    echo "[+] Done. Goodbye!"
    exit 0
}

# Trap Ctrl+C and exit signals
trap cleanup INT TERM EXIT

# Background subshell launcher that waits for the simulator and launches voice control
start_voice_control() {
    echo "[*] Background monitor: waiting for simulator bridge to initialize (checking health endpoint)..."
    READY=0
    for i in {1..20}; do
        # Sleep first to let uvicorn initialize a bit
        sleep 1
        curl -s http://127.0.0.1:8765/health | grep -q "ok"
        if [ $? -eq 0 ]; then
            echo "[+] Background monitor: Simulator Bridge is online and healthy!"
            READY=1
            break
        fi
    done

    if [ $READY -eq 0 ]; then
        echo "[!] Background monitor Error: Simulator Bridge failed to start or respond in time."
        # If health fails, trigger parent exit by killing parent PID
        kill -s TERM $$
        exit 1
    fi

    echo "[*] Background monitor: Starting Voice Control Node..."
    .venv/bin/python -m duck_agent_sim.agent.voice_control --url http://127.0.0.1:8765 "$@"
}

# Launch the voice control monitor function in the background!
start_voice_control "$@" &
LAUNCHER_PID=$!

# Launch the MuJoCo Simulator Bridge in the FOREGROUND!
# Running in the foreground allows macOS GLFW to allocate GUI window frame buffers.
echo "[*] Launching MuJoCo Simulator Bridge in dynamic REAL mode (foreground)..."
export DUCK_SIM_MODE=real
.venv/bin/mjpython -m uvicorn duck_agent_sim.main:app --host 127.0.0.1 --port 8765
