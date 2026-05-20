#!/bin/bash
# Invokes the pre-scripted walk-square scenario via curl

PORT=${BRIDGE_PORT:-8765}
HOST=${BRIDGE_HOST:-127.0.0.1}

echo "=========================================="
echo "    Executing Walk Square Scenario via API"
echo "=========================================="

echo "Sending POST request to http://$HOST:$PORT/scenario/walk-square..."
echo ""

# Try sending command, outputting the returned JSON
curl -s -X POST "http://$HOST:$PORT/scenario/walk-square" \
     -H "Content-Type: application/json" | python3 -m json.tool || {
         echo ""
         echo "Error: Could not connect to API server on http://$HOST:$PORT"
         echo "Please ensure the bridge is running by executing 'bash scripts/run_bridge.sh' first!"
         exit 1
     }
