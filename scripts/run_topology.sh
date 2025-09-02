#!/bin/bash
# scripts/run_topology.sh - Simple Mininet Topology Starter

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PATH="$PROJECT_ROOT/venv"

echo "Starting Mininet Topology (Simple Mode)..."

# Activate virtual environment
source "$VENV_PATH/bin/activate" || { echo "Error: Virtual environment not found at $VENV_PATH"; exit 1; }
echo "Virtual environment activated"

# Create directories
mkdir -p data/logs data/config

# Parse arguments
CONFIG_FILE="data/config/topo_config.json"
LOG_LEVEL="info"
while [[ $# -gt 0 ]]; do
    case $1 in
        -c|--config) CONFIG_FILE="$2"; shift 2 ;;
        -l|--log-level) LOG_LEVEL="$2"; shift 2 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
done

echo "Using config: $CONFIG_FILE"
echo "Log level: $LOG_LEVEL"
echo

echo "NOTE: Make sure you have started the following services manually:"
echo "1. Open vSwitch: sudo systemctl start openvswitch-switch"
echo "2. Ryu Controller: ryu-manager --ofp-tcp-listen-port 6653 src/ryu_controller.py"
echo

echo "Waiting 5 seconds for you to verify services are running..."
sleep 5

# Simple connectivity check
echo "Checking if controller is reachable..."
if nc -z 127.0.0.1 6653 2>/dev/null; then
    echo "✓ Controller is reachable on port 6653"
else
    echo "✗ Warning: Cannot connect to controller on port 6653"
    echo "Make sure Ryu controller is running with: ryu-manager --ofp-tcp-listen-port 6653 src/ryu_controller.py"
fi

echo "Checking if OVS is working..."
if sudo ovs-vsctl show > /dev/null 2>&1; then
    echo "✓ OVS is working"
else
    echo "✗ Warning: OVS is not working properly"
    echo "Make sure OVS is running with: sudo systemctl start openvswitch-switch"
fi

echo
echo "Starting Mininet topology..."
cd "$PROJECT_ROOT"
sudo -E "$VENV_PATH/bin/python3" src/mininet_topology.py --config "$CONFIG_FILE" --log-level "$LOG_LEVEL"
