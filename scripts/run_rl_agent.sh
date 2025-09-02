#!/bin/bash
echo "Starting RL Agent..."
source venv/bin/activate

# Ensure controller is running
echo "Waiting for controller to be ready..."
max_retries=10
for ((i=1; i<=$max_retries; i++)); do
    if nc -z localhost 8888 2>/dev/null; then
        echo "Controller API ready"
        break
    fi
    echo "Attempt $i/$max_retries: Controller API not ready, retrying..."
    sleep 3
done

if [ $i -gt $max_retries ]; then
    echo "Warning: Controller API not ready after $max_retries seconds"
    echo "The agent will continue to try connecting during runtime"
fi

echo "Starting RL Agent with the following configuration:"
echo "  Mode: train"
echo "  Config: data/config/agent_config.json"
echo ""
echo "Agent logs will be saved to data/logs/rl_agent.log"
echo "Models will be saved to data/models/"
echo "Metrics database: data/models/agent_metrics.db"
echo ""
echo "Training mode - the agent will learn from network interactions"
echo "Training progress will be logged. Use Ctrl+C to stop gracefully"

mkdir -p data/logs data/models monitoring_plots
python3 src/rl_agent.py > data/logs/rl_agent.log 2>&1 &
echo $! > pids/rl_agent.pid

echo "Press Ctrl+C to stop"
wait
