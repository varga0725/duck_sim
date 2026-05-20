#!/bin/bash
# Exit immediately if a command exits with a non-zero status
set -e

echo "=========================================================="
echo "    Setting up Open Duck Simulation Workspace Environment"
echo "=========================================================="

# Create external directory
mkdir -p external

# Clone Open_Duck_Playground if not already present
if [ ! -d "external/Open_Duck_Playground" ]; then
    echo "Cloning apirrone/Open_Duck_Playground..."
    git clone https://github.com/apirrone/Open_Duck_Playground external/Open_Duck_Playground
else
    echo "external/Open_Duck_Playground is already cloned."
fi

# Set up python virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating Python virtual environment using standard venv..."
    python3 -m venv .venv
fi

# Activate virtualenv
source .venv/bin/activate

echo "Upgrading pip..."
pip install --upgrade pip

echo "Installing package dependencies in editable dev mode..."
pip install -e ".[dev]"

echo ""
echo "=== Success! Environment is ready. ==="
echo "To run the API bridge, run:"
echo "  source .venv/bin/activate"
echo "  bash scripts/run_bridge.sh"
echo "=========================================================="
