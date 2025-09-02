#!/bin/bash
# scripts/run_controller.sh - Start Ryu Controller

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"

echo "Starting Ryu Controller..."

# Activate virtual environment
if [ -f "$VENV_PATH/bin/activate" ]; then
    source "$VENV_PATH/bin/activate"
    echo "Virtual environment activated"
else
    echo "Error: Virtual environment not found at $VENV_PATH"
    exit 1
fi

# Change to project directory
cd "$PROJECT_ROOT"

# Create logs directory
mkdir -p data/logs

# Set PYTHONPATH
export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

# Start Ryu controller with REST API
echo "Starting Ryu controller with REST API on port 8080..."
echo "Controller logs will be saved to data/logs/ryu_controller.log"
echo "Press Ctrl+C to stop"

exec ryu-manager \
    --wsapi-host 127.0.0.1 \
    --wsapi-port 8080 \
    --ofp-tcp-listen-port 6653 \
    --verbose \
    src/ryu_controller.py
