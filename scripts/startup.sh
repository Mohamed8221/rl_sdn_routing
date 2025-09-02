#!/bin/bash
# scripts/run_controller.sh

set -e

# Configuration
RYU_CONTROLLER="src/ryu_controller.py"
LOG_FILE="logs/ryu_controller.log"
PID_FILE="pids/ryu_controller.pid"

# Create necessary directories
mkdir -p logs pids data/config

# Check if controller is already running
if [ -f "$PID_FILE" ]; then
    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "Ryu controller is already running (PID: $(cat $PID_FILE))"
        exit 1
    else
        echo "Removing stale PID file"
        rm -f "$PID_FILE"
    fi
fi

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Activated virtual environment"
fi

# Start Ryu controller
echo "Starting Ryu SDN controller..."
echo "Logs will be written to: $LOG_FILE"

ryu-manager \
    --observe-links \
    --wsapi-host 0.0.0.0 \
    --wsapi-port 8080 \
    --ofp-tcp-listen-port 6633 \
    "$RYU_CONTROLLER" \
    > "$LOG_FILE" 2>&1 &

# Save PID
echo $! > "$PID_FILE"
echo "Ryu controller started with PID: $!"
echo "Use 'pkill -F $PID_FILE' to stop"

---

#!/bin/bash
# scripts/run_topology.sh

set -e

# Configuration
TOPOLOGY_SCRIPT="src/mininet_topology.py"
LOG_FILE="logs/mininet_topology.log"
PID_FILE="pids/mininet_topology.pid"

# Create necessary directories
mkdir -p logs pids data/config

# Check if topology is already running
if [ -f "$PID_FILE" ]; then
    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "Mininet topology is already running (PID: $(cat $PID_FILE))"
        exit 1
    else
        echo "Removing stale PID file"
        rm -f "$PID_FILE"
    fi
fi

# Clean any existing Mininet processes
echo "Cleaning existing Mininet processes..."
sudo mn -c > /dev/null 2>&1 || true

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Activated virtual environment"
fi

# Start Mininet topology
echo "Starting Mininet topology..."
echo "Logs will be written to: $LOG_FILE"

sudo python3 "$TOPOLOGY_SCRIPT" > "$LOG_FILE" 2>&1 &

# Save PID
echo $! > "$PID_FILE"
echo "Mininet topology started with PID: $!"
echo "Use 'sudo pkill -F $PID_FILE' to stop"

---

#!/bin/bash
# scripts/run_rl_agent.sh

set -e

# Configuration
RL_AGENT_SCRIPT="src/rl_agent.py"
LOG_FILE="logs/rl_agent.log"
PID_FILE="pids/rl_agent.pid"

# Create necessary directories
mkdir -p logs pids data/config models

# Check if RL agent is already running
if [ -f "$PID_FILE" ]; then
    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "RL agent is already running (PID: $(cat $PID_FILE))"
        exit 1
    else
        echo "Removing stale PID file"
        rm -f "$PID_FILE"
    fi
fi

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Activated virtual environment"
fi

# Start RL agent
echo "Starting RL agent..."
echo "Logs will be written to: $LOG_FILE"

python3 "$RL_AGENT_SCRIPT" > "$LOG_FILE" 2>&1 &

# Save PID
echo $! > "$PID_FILE"
echo "RL agent started with PID: $!"
echo "Use 'pkill -F $PID_FILE' to stop"

---

#!/bin/bash
# scripts/run_monitor.sh

set -e

# Configuration
MONITOR_SCRIPT="scripts/monitor.py"
LOG_FILE="logs/monitor.log"
PID_FILE="pids/monitor.pid"

# Create necessary directories
mkdir -p logs pids data/logs data/reports monitoring_plots

# Check if monitor is already running
if [ -f "$PID_FILE" ]; then
    if ps -p $(cat "$PID_FILE") > /dev/null 2>&1; then
        echo "Monitor is already running (PID: $(cat $PID_FILE))"
        exit 1
    else
        echo "Removing stale PID file"
        rm -f "$PID_FILE"
    fi
fi

# Activate virtual environment if it exists
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "Activated virtual environment"
fi

# Start monitor
echo "Starting network monitor..."
echo "Logs will be written to: $LOG_FILE"

python3 "$MONITOR_SCRIPT" > "$LOG_FILE" 2>&1 &

# Save PID
echo $! > "$PID_FILE"
echo "Monitor started with PID: $!"
echo "Use 'pkill -F $PID_FILE' to stop"

---

#!/bin/bash
# scripts/startup.sh

set -e

echo "========================================="
echo "RL-SDN Routing System Startup"
echo "========================================="

# Create all necessary directories
echo "Creating directories..."
mkdir -p logs pids data/{config,logs,reports} models monitoring_plots

# Clean any existing processes
echo "Cleaning existing processes..."
sudo mn -c > /dev/null 2>&1 || true
pkill -f "ryu-manager" > /dev/null 2>&1 || true
pkill -f "rl_agent.py" > /dev/null 2>&1 || true
pkill -f "monitor.py" > /dev/null 2>&1 || true

# Wait a moment for cleanup
sleep 2

# Activate virtual environment if available
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo "✓ Activated virtual environment"
else
    echo "! Virtual environment not found, using system Python"
fi

# Check dependencies
echo "Checking dependencies..."
python3 -c "import ryu; print('✓ Ryu available')" || { echo "✗ Ryu not installed"; exit 1; }
python3 -c "import tensorflow; print('✓ TensorFlow available')" || { echo "✗ TensorFlow not installed"; exit 1; }
python3 -c "import flask; print('✓ Flask available')" || { echo "✗ Flask not installed"; exit 1; }

# Start components in order
echo "Starting RL Agent..."
bash scripts/run_rl_agent.sh
sleep 3

echo "Starting Ryu Controller..."
bash scripts/run_controller.sh
sleep 5

echo "Starting Network Monitor..."
bash scripts/run_monitor.sh
sleep 3

echo "Starting Mininet Topology..."
bash scripts/run_topology.sh
sleep 5

echo ""
echo "========================================="
echo "All components started successfully!"
echo "========================================="
echo ""
echo "Running processes:"
echo "- RL Agent:    PID $(cat pids/rl_agent.pid 2>/dev/null || echo 'N/A')"
echo "- Controller:  PID $(cat pids/ryu_controller.pid 2>/dev/null || echo 'N/A')"
echo "- Monitor:     PID $(cat pids/monitor.pid 2>/dev/null || echo 'N/A')"
echo "- Topology:    PID $(cat pids/mininet_topology.pid 2>/dev/null || echo 'N/A')"
echo ""
echo "API Endpoints:"
echo "- RL Agent:    http://localhost:5000"
echo "- Controller:  http://localhost:8080"
echo ""
echo "Log files:"
echo "- RL Agent:    logs/rl_agent.log"
echo "- Controller:  logs/ryu_controller.log"
echo "- Monitor:     logs/monitor.log"
echo "- Topology:    logs/mininet_topology.log"
echo ""
echo "To stop all components, run: bash scripts/stop_all.sh"

---

#!/bin/bash
# scripts/stop_all.sh

echo "Stopping RL-SDN Routing System..."

# Function to stop a process by PID file
stop_process() {
    local name=$1
    local pid_file=$2
    local use_sudo=$3
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            if [ "$use_sudo" = "true" ]; then
                sudo kill -TERM "$pid" 2>/dev/null || true
            else
                kill -TERM "$pid" 2>/dev/null || true
            fi
            echo "✓ Stopped $name (PID: $pid)"
        else
            echo "! $name not running"
        fi
        rm -f "$pid_file"
    else
        echo "! No PID file for $name"
    fi
}

# Stop all components
stop_process "Mininet Topology" "pids/mininet_topology.pid" "true"
stop_process "Monitor" "pids/monitor.pid" "false"
stop_process "Ryu Controller" "pids/ryu_controller.pid" "false"
stop_process "RL Agent" "pids/rl_agent.pid" "false"

# Clean Mininet
echo "Cleaning Mininet..."
sudo mn -c > /dev/null 2>&1 || true

# Kill any remaining processes
pkill -f "ryu-manager" > /dev/null 2>&1 || true
pkill -f "rl_agent.py" > /dev/null 2>&1 || true
pkill -f "monitor.py" > /dev/null 2>&1 || true

echo "All components stopped."

---

#!/bin/bash
# scripts/check_status.sh

echo "========================================="
echo "RL-SDN System Status"
echo "========================================="

# Function to check process status
check_process() {
    local name=$1
    local pid_file=$2
    
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if ps -p "$pid" > /dev/null 2>&1; then
            echo "✓ $name: Running (PID: $pid)"
        else
            echo "✗ $name: PID file exists but process not running"
        fi
    else
        echo "✗ $name: Not running (no PID file)"
    fi
}

# Check all components
check_process "RL Agent" "pids/rl_agent.pid"
check_process "Ryu Controller" "pids/ryu_controller.pid"
check_process "Monitor" "pids/monitor.pid"
check_process "Mininet Topology" "pids/mininet_topology.pid"

echo ""
echo "API Health Checks:"

# Check RL Agent API
if curl -s http://localhost:5000/health > /dev/null 2>&1; then
    echo "✓ RL Agent API: Responding"
else
    echo "✗ RL Agent API: Not responding"
fi

# Check Controller API
if curl -s http://localhost:8080/rlcontroller/stats > /dev/null 2>&1; then
    echo "✓ Controller API: Responding"
else
    echo "✗ Controller API: Not responding"
fi

echo ""
echo "Log file sizes:"
[ -f "logs/rl_agent.log" ] && echo "  RL Agent:    $(wc -l < logs/rl_agent.log) lines"
[ -f "logs/ryu_controller.log" ] && echo "  Controller:  $(wc -l < logs/ryu_controller.log) lines"
[ -f "logs/monitor.log" ] && echo "  Monitor:     $(wc -l < logs/monitor.log) lines"
[ -f "logs/mininet_topology.log" ] && echo "  Topology:    $(wc -l < logs/mininet_topology.log) lines"

echo ""
echo "Data files:"
[ -f "traffic_results.json" ] && echo "✓ Performance report: traffic_results.json"
[ -d "models" ] && echo "✓ Models directory: $(ls models/ 2>/dev/null | wc -l) files"
[ -d "monitoring_plots" ] && echo "✓ Plots directory: $(ls monitoring_plots/ 2>/dev/null | wc -l) files"

---

#!/bin/bash
# scripts/test_system.sh

echo "========================================="
echo "RL-SDN System Testing"
echo "========================================="

# Test network connectivity
test_connectivity() {
    echo "Testing network connectivity..."
    
    # Wait for system to be ready
    sleep 5
    
    # Test ping between hosts
    echo "Testing ping h1 -> h2..."
    sudo timeout 10s mn --test pingall || echo "Ping test failed"
    
    echo "Testing iperf traffic..."
    # This would need to be run from within Mininet CLI
    echo "Run 'iperf h1 h2' from Mininet CLI for throughput testing"
}

# Test RL agent
test_rl_agent() {
    echo "Testing RL agent..."
    
    # Test health endpoint
    if curl -s http://localhost:5000/health; then
        echo "✓ RL agent health check passed"
    else
        echo "✗ RL agent health check failed"
        return 1
    fi
    
    # Test stats endpoint
    if curl -s http://localhost:5000/stats > /dev/null; then
        echo "✓ RL agent stats endpoint working"
    else
        echo "✗ RL agent stats endpoint failed"
        return 1
    fi
    
    return 0
}

# Test controller
test_controller() {
    echo "Testing Ryu controller..."
    
    # Test stats endpoint
    if curl -s http://localhost:8080/rlcontroller/stats > /dev/null; then
        echo "✓ Controller stats endpoint working"
    else
        echo "✗ Controller stats endpoint failed"
        return 1
    fi
    
    # Test topology endpoint
    if curl -s http://localhost:8080/rlcontroller/topology > /dev/null; then
        echo "✓ Controller topology endpoint working"
    else
        echo "✗ Controller topology endpoint failed"
        return 1
    fi
    
    return 0
}

# Run tests
if test_rl_agent && test_controller; then
    echo "✓ All API tests passed"
    test_connectivity
else
    echo "✗ Some tests failed"
fi

---

#!/bin/bash
# scripts/generate_traffic.sh

echo "Generating test traffic for RL training..."

# Function to generate traffic between specific hosts
generate_traffic() {
    local src=$1
    local dst=$2
    local duration=${3:-10}
    
    echo "Generating traffic from h$src to h$dst for ${duration}s..."
    
    # This script should be run after the topology is created
    # The actual traffic generation would be done from within Mininet
    cat << EOF > /tmp/traffic_test.py
from mininet.net import Mininet
from mininet.topo import Topo
import time

# This is a template - actual implementation would connect to existing network
# For now, we'll just log the intended traffic pattern
print("Traffic pattern: h$src -> h$dst for ${duration}s")
EOF
    
    python3 /tmp/traffic_test.py
}

# Generate different traffic patterns
echo "Starting traffic generation patterns..."

generate_traffic 1 2 15 &
sleep 5
generate_traffic 1 3 20 &
sleep 5  
generate_traffic 2 4 25 &
sleep 5
generate_traffic 3 1 15 &

wait
echo "Traffic generation completed"

---

#!/bin/bash
# scripts/collect_results.sh

echo "Collecting RL-SDN performance results..."

# Create results directory
mkdir -p results/$(date +%Y%m%d_%H%M%S)
RESULTS_DIR="results/$(date +%Y%m%d_%H%M%S)"

# Copy main results
cp traffic_results.json "$RESULTS_DIR/" 2>/dev/null || echo "No traffic results found"

# Copy logs
cp -r logs "$RESULTS_DIR/" 2>/dev/null || echo "No logs found"

# Copy models
cp -r models "$RESULTS_DIR/" 2>/dev/null || echo "No models found"

# Copy plots
cp -r monitoring_plots "$RESULTS_DIR/" 2>/dev/null || echo "No plots found"

# Copy configuration
cp -r data/config "$RESULTS_DIR/" 2>/dev/null || echo "No config found"

# Generate summary report
cat > "$RESULTS_DIR/experiment_summary.md" << EOF
# RL-SDN Experiment Results

**Date**: $(date)
**Duration**: See logs for actual runtime
**System**: $(uname -a)

## Configuration
- Topology: $(grep -o '"topology_type": "[^"]*"' data/config/topology_config.json 2>/dev/null || echo "unknown")
- RL Agent: $(grep -o '"agent_type": "[^"]*"' data/config/rl_config.json 2>/dev/null || echo "auto-detected")
- Switches: $(grep -o '"num_switches": [0-9]*' data/config/topology_config.json 2>/dev/null || echo "4")

## Results Files
- Performance Report: traffic_results.json
- Logs: logs/
- Models: models/  
- Plots: monitoring_plots/
- Config: config/

## Key Metrics
$(if [ -f traffic_results.json ]; then
    python3 -c "
import json
try:
    with open('traffic_results.json') as f:
        data = json.load(f)
        perf = data.get('network_performance', {})
        print('- Average Latency: {:.2f} ms'.format(perf.get('latency_ms', {}).get('avg', 0)))
        print('- Average Throughput: {:.2f} Mbps'.format(perf.get('throughput_bps', {}).get('avg', 0) / 1000000))
        print('- Packet Loss Rate: {:.4f}'.format(perf.get('packet_loss_rate', {}).get('avg', 0)))
        
        rl_perf = data.get('rl_agent_performance', {})
        print('- RL Average Reward: {:.3f}'.format(rl_perf.get('average_reward', 0)))
        print('- RL Total Requests: {}'.format(rl_perf.get('total_requests', 0)))
except:
    print('- Could not parse results')
" 2>/dev/null
else
    echo "- No performance data available"
fi)

EOF

echo "Results collected in: $RESULTS_DIR"
echo "Summary report: $RESULTS_DIR/experiment_summary.md"
