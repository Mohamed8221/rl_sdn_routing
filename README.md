# RL-SDN Routing Project

This project implements a Software-Defined Networking (SDN) controller integrated with a Reinforcement Learning (RL) agent to optimize routing in a network. The system uses the Ryu SDN framework, a Deep Q-Network (DQN) for path selection, and Mininet for network emulation. It supports TCP traffic, achieves live rerouting within 1-2 seconds, and aims to outperform traditional OSPF/shortest-path (SP) routing by 50% in terms of throughput. A real-time monitoring dashboard provides insights into network performance and RL rewards.

## Table of Contents
- [Project Overview](#project-overview)
- [Features](#features)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Setup Instructions](#setup-instructions)
- [Usage](#usage)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [Future Improvements](#future-improvements)
- [License](#license)

## Project Overview
The RL-SDN Routing project combines SDN with RL to dynamically select optimal network paths. The Ryu controller (`ryu_controller.py`) handles OpenFlow 1.3 switches, processes `PacketIn` events, and installs TCP flows based on paths provided by the RL agent (`rl_agent.py`). The RL agent uses a DQN to learn optimal paths, with state inputs including flow count, link utilization, and recent rewards. Mininet emulates a linear topology (default: 4 switches, 4 hosts), and a monitoring script (`monitor.py`) provides a web-based dashboard for real-time metrics. The system supports rapid rerouting (within 1-2 seconds) upon link failures and avoids redundant flows.

## Features
- **SDN Controller**: Ryu-based controller for OpenFlow 1.3 switches, handling `PacketIn`, `SwitchFeatures`, and `PortStatus` events.
- **RL-based Routing**: DQN agent selects optimal paths based on network state (flow count, flow entries, link utilization, RL rewards).
- **TCP Support**: Enforces TCP flows (`ip_proto=6`) for reliable data transfer.
- **Live Rerouting**: Detects link failures and reroutes flows within 1-2 seconds using RL or shortest-path fallback.
- **Duplicate Flow Prevention**: Checks for existing flows to avoid redundancy.
- **Real-Time Monitoring**: Web dashboard at `http://127.0.0.1:8080/dashboard` displays flow stats and RL rewards.
- **Performance Goal**: Aims to outperform OSPF/SP by 50% in throughput after RL training.
- **Scalability**: Designed for large topologies with configurable paths (`possible_paths.json`).

## Prerequisites
- **Operating System**: Ubuntu 20.04 or later (Linux-based system recommended).
- **Python**: Version 3.8 or higher.
- **Dependencies**:
  ```bash
  sudo apt update
  sudo apt install -y python3-pip mininet openvswitch-switch
  pip3 install ryu==4.34 flask==2.0.1 numpy==1.22.0 tensorflow==2.8.0 networkx==2.6.3 requests==2.26.0
  ```
- **Mininet**: Version 2.3.0 or higher for network emulation.
- **Open vSwitch**: Version 2.13.0 or higher for OpenFlow support.
- **Hardware**: Minimum 4GB RAM, 2 CPU cores for Mininet and Ryu.

## Project Structure
```
rl_sdn_routing/
├── data/
│   └── config/
│       ├── rl_config.json         # RL agent configuration (state size, learning rate, etc.)
│       ├── possible_paths.json    # Predefined paths for src-dst pairs
│       └── topology_info.json     # Topology details (switches, hosts, links)
├── logs/
│   ├── ryu_controller.log         # Ryu controller logs
│   ├── rl_agent.log               # RL agent logs
│   └── monitor.log                # Monitor dashboard logs
├── models/
│   └── dqn_model_*.h5            # Saved DQN models
├── src/
│   ├── ryu_controller.py          # Ryu SDN controller
│   ├── rl_agent.py                # RL agent with DQN
│   ├── mininet_topology.py        # Mininet topology script
│   └── monitor.py                 # Monitoring dashboard
├── templates/
│   └── dashboard.html             # Web dashboard template
└── README.md                      # This file
```

## Setup Instructions
1. **Clone the Repository**:
   ```bash
   git clone <repository-url>
   cd rl_sdn_routing
   ```

2. **Create Directories**:
   ```bash
   mkdir -p data/config logs models templates
   chmod -R 777 data logs models templates
   ```

3. **Install Dependencies**:
   ```bash
   sudo apt update
   sudo apt install -y python3-pip mininet openvswitch-switch
   pip3 install ryu==4.34 flask==2.0.1 numpy==1.22.0 tensorflow==2.8.0 networkx==2.6.3 requests==2.26.0
   ```

4. **Configure Files**:
   - **rl_config.json**:
     ```bash
     echo '{"state_size": 4, "learning_rate": 0.1, "discount_factor": 0.9, "save_interval": 300}' > data/config/rl_config.json
     ```
   - **possible_paths.json** (for a linear topology with 4 switches):
     ```bash
     python3 -c "import json; paths = {'1->2': [[1, 2]], '1->3': [[1, 2, 3]], '1->4': [[1, 2, 3, 4]], '2->1': [[2, 1]], '2->3': [[2, 3]], '2->4': [[2, 3, 4]], '3->1': [[3, 2, 1]], '3->2': [[3, 2]], '3->4': [[3, 4]], '4->1': [[4, 3, 2, 1]], '4->2': [[4, 3, 2]], '4->3': [[4, 3]]}; with open('data/config/possible_paths.json', 'w') as f: json.dump(paths, f, indent=2)"
     ```
   - **topology_info.json** (example for 4-switch linear topology):
     ```bash
     echo '{
       "switches": {
         "s1": {"dpid": 1},
         "s2": {"dpid": 2},
         "s3": {"dpid": 3},
         "s4": {"dpid": 4}
       },
       "hosts": {
         "h1": {"ip": "10.0.0.1", "connected_to": "s1"},
         "h2": {"ip": "10.0.0.2", "connected_to": "s2"},
         "h3": {"ip": "10.0.0.3", "connected_to": "s3"},
         "h4": {"ip": "10.0.0.4", "connected_to": "s4"}
       },
       "links": [
         {"src": "s1", "dst": "s2", "port": 1},
         {"src": "s2", "dst": "s1", "port": 1},
         {"src": "s2", "dst": "s3", "port": 2},
         {"src": "s3", "dst": "s2", "port": 1},
         {"src": "s3", "dst": "s4", "port": 2},
         {"src": "s4", "dst": "s3", "port": 1},
         {"src": "h1", "dst": "s1", "port": 2},
         {"src": "h2", "dst": "s2", "port": 3},
         {"src": "h3", "dst": "s3", "port": 3},
         {"src": "h4", "dst": "s4", "port": 2}
       ]
     }' > data/config/topology_info.json
     ```

5. **Clean Mininet Environment**:
   ```bash
   sudo mn -c
   sudo ip link delete s2-eth2 2>/dev/null
   sudo ip link delete s17-eth2 2>/dev/null
   ```

## Usage
1. **Start RL Agent**:
   ```bash
   python3 src/rl_agent.py &
   ```
   - Runs a Flask server on `http://127.0.0.1:5000`.
   - Logs to `logs/rl_agent.log`.
   - Provides `/get_path`, `/update`, `/stats`, and `/health` endpoints.

2. **Start Ryu Controller**:
   ```bash
   ryu-manager --verbose --ofp-tcp-listen-port 6653 src/ryu_controller.py &
   ```
   - Listens for OpenFlow switches on port 6653.
   - Provides REST API at `http://127.0.0.1:8080` (`/force_path`, `/force_sp_path`, `/stats`).
   - Logs to `logs/ryu_controller.log`.

3. **Start Monitor**:
   ```bash
   python3 src/monitor.py &
   ```
   - Serves dashboard at `http://127.0.0.1:8080/dashboard`.
   - Logs to `logs/monitor.log`.

4. **Run Mininet Topology**:
   ```bash
   sudo python3 src/mininet_topology.py --topo linear
   ```
   - Creates a linear topology with 4 switches and 4 hosts (default).
   - Configurable via `--topo` (e.g., `linear`, `tree`, `fat-tree`).

## Testing
Follow these steps to verify the system:

1. **Verify RL Agent**:
   ```bash
   curl http://127.0.0.1:5000/health
   ```
   Expect: `{"status": "healthy", "agent_initialized": true, "timestamp": ...}`
   ```bash
   curl -X POST http://127.0.0.1:5000/get_path -H "Content-Type: application/json" -d '{"src": "1", "dst": "4", "state": [28, 28, 0.33333333, 0]}'
   ```
   Expect: `{"path": [1, 2, 3, 4], "action_idx": 0}`
   Check `logs/rl_agent.log` for:
   - `RL agent initialized successfully`
   - `Returning path [1, 2, 3, 4] for 1->4`

2. **Verify Ryu Controller**:
   ```bash
   curl http://127.0.0.1:8080/stats
   ```
   Expect: `{"status": "success", "stats": [...]}` (e.g., `[0, 0, 0.33333333, 0]`)
   Check `logs/ryu_controller.log` for:
   - `Switch connected: dpid=1`
   - `Topology graph updated with 4 nodes, 3 edges`
   - `PacketIn: dpid=..., in_port=..., eth_src=..., eth_dst=...`
   - `RL agent path for 1->4: {"path": [1, 2, 3, 4], "action_idx": 0}`

3. **Test Connectivity**:
   ```bash
   mininet> pingall
   ```
   Expect: `0% dropped`
   ```bash
   mininet> dpctl dump-flows
   ```
   Expect TCP flows: `priority=10,tcp,nw_src=10.0.0.1,nw_dst=10.0.0.2,actions=output:2`

4. **Test TCP Traffic**:
   ```bash
   mininet> h4 iperf -s &
   mininet> h1 iperf -c 10.0.0.4 -t 30
   ```
   Expect: ~9.5 Mbps throughput.

5. **Test Rerouting**:
   ```bash
   mininet> link s1 s2 down
   mininet> h1 iperf -c 10.0.0.4 -t 10
   ```
   Expect: Success within 2 seconds using RL path.
   Check `logs/ryu_controller.log` for: `Rerouted TCP flow: 10.0.0.1 -> 10.0.0.4 via path ...`

6. **Test RL Path Installation**:
   ```bash
   curl -X POST http://127.0.0.1:8080/force_path -H "Content-Type: application/json" -d '{"src_ip": "10.0.0.1", "dst_ip": "10.0.0.4", "is_tcp": true}'
   ```
   Expect: `{"status": "success", "message": "Path [1, 2, 3, 4] installed for 10.0.0.1 -> 10.0.0.4"}`

7. **Test Shortest Path**:
   ```bash
   curl -X POST http://127.0.0.1:8080/force_sp_path -H "Content-Type: application/json" -d '{"path": [1, 2], "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "is_tcp": true}'
   ```
   Run `iperf` and compare with RL path performance.

8. **View Dashboard**:
   Open `http://127.0.0.1:8080/dashboard` in a browser to see flow stats and RL rewards.

## Troubleshooting
1. **RL Agent Fails to Start**:
   - Check `logs/rl_agent.log` for errors (e.g., `Configuration file ... not found`).
   - Verify `data/config/rl_config.json` and `data/config/possible_paths.json` exist.
   - Ensure Flask server is running:
     ```bash
     netstat -tuln | grep 5000
     ```
     Expect: `tcp 0 0 0.0.0.0:5000 0.0.0.0:* LISTEN`

2. **Ryu Controller Errors**:
   - Check `logs/ryu_controller.log` for:
     - `AttributeError: ... OFPP_NO_BUFFER`: Ensure `ryu_controller.py` uses `ofproto.OFP_NO_BUFFER`.
     - `Error requesting path from RL agent`: Verify RL agent is running and `/get_path` works.
   - Confirm Ryu version:
     ```bash
     pip show ryu
     ```
     Expect: Version >= 4.34. If not:
     ```bash
     pip install ryu --upgrade
     ```

3. **JSON Serialization Error**:
   - Check `logs/rl_agent.log` for `Object of type int64 is not JSON serializable`.
   - Ensure `rl_agent.py` converts `int64` to `int` in `get_action`.

4. **UDP Instead of TCP Flows**:
   - Check `logs/ryu_controller.log` for `Installed TCP flow`.
   - Verify flows with:
     ```bash
     mininet> dpctl dump-flows
     ```
     Expect: `ip_proto=6`.
   - Use `tcpdump`:
     ```bash
     mininet> h1 tcpdump -i h1-eth0
     ```

5. **No Connectivity**:
   - Run `pingall` and check `logs/ryu_controller.log` for `PacketIn` and `PacketOut` messages.
   - Ensure `topology_info.json` matches the Mininet topology.

6. **Excessive PacketIn Events**:
   - Check `logs/ryu_controller.log`:
     ```bash
     grep "PacketIn" logs/ryu_controller.log
     ```
   - Debug with `tcpdump` to identify unexpected traffic.

If issues persist, share:
- `logs/ryu_controller.log`, `logs/rl_agent.log`, `logs/monitor.log`.
- Output of `cat data/config/rl_config.json`, `cat data/config/possible_paths.json`, `cat data/config/topology_info.json`.
- Results of `dpctl dump-flows`, `iperf`, `tcpdump`.
- Output of `pip show ryu`, `pip show numpy`, `pip show tensorflow`.

## Future Improvements
- **Advanced Topologies**: Support tree, fat-tree, or custom topologies in `mininet_topology.py`.
- **Enhanced DQN**: Incorporate experience replay and target networks for better RL performance.
- **Dynamic Rewards**: Calculate rewards based on real-time latency and throughput.
- **Scalability Testing**: Evaluate performance on larger topologies (e.g., 20 switches).
- **Security**: Add authentication to RL agent and controller APIs.
- **Dashboard Enhancements**: Visualize topology and flow paths in real-time.

## License
This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.