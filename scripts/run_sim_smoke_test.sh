#!/bin/bash
# Sim smoke tests - runs unit tests to verify kinematics, schemas and safety monitor

if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

echo "=========================================="
echo "    Running Simulator Smoke Tests (pytest)"
echo "=========================================="

pytest -v
