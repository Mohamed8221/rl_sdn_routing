#!/usr/bin/env python3

import json
import os
import time
import argparse
import requests
import socket
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

class LinearTopo(Topo):
    """Linear topology: h1-s1-s2(h2)-s3(h3)-s4-h4"""
    def build(self):
        # Add switches
        switches = []
        for i in range(1, 5):
            switch = self.addSwitch(f's{i}', dpid=str(i).zfill(16))
            switches.append(switch)
        
        # Add hosts
        hosts = []
        for i in range(1, 5):
            host = self.addHost(f'h{i}', ip=f'10.0.0.{i}/24', mac=f'00:00:00:00:00:0{i}')
            hosts.append(host)
        
        # Add host-switch links
        self.addLink(hosts[0], switches[0], port1=0, port2=1, cls=TCLink, bw=10, delay='1ms', loss=0)
        self.addLink(hosts[1], switches[1], port1=0, port2=1, cls=TCLink, bw=10, delay='1ms', loss=0)
        self.addLink(hosts[2], switches[2], port1=0, port2=1, cls=TCLink, bw=10, delay='1ms', loss=0)
        self.addLink(hosts[3], switches[3], port1=0, port2=1, cls=TCLink, bw=10, delay='1ms', loss=0)
        
        # Add switch-switch links
        for i in range(len(switches)-1):
            self.addLink(switches[i], switches[i+1], port1=2+i, port2=2, cls=TCLink, bw=10, delay='1ms', loss=0)
        
        # Generate topology info
        self.generate_topology_info(switches, hosts)

    def generate_topology_info(self, switches, hosts):
        """Generate topology_info.json for the linear topology"""
        topology_info = {
            'switches': {f's{i+1}': {'dpid': i+1, 'ports': {}} for i in range(len(switches))},
            'hosts': {f'h{i+1}': {'ip': f'10.0.0.{i+1}', 'mac': f'00:00:00:00:00:0{i+1}', 'connected_to': f's{i+1}'} for i in range(len(hosts))},
            'links': []
        }
        
        # Add host-switch links
        for i in range(len(hosts)):
            topology_info['switches'][f's{i+1}']['ports'][f'h{i+1}'] = 1
            topology_info['links'].append({'src': f'h{i+1}', 'dst': f's{i+1}', 'port': 1})
        
        # Add switch-switch links
        for i in range(len(switches)-1):
            src_switch = f's{i+1}'
            dst_switch = f's{i+2}'
            topology_info['switches'][src_switch]['ports'][dst_switch] = 2+i
            topology_info['switches'][dst_switch]['ports'][src_switch] = 2
            topology_info['links'].append({'src': src_switch, 'dst': dst_switch, 'port': 2+i})
        
        os.makedirs('data/config', exist_ok=True)
        with open('data/config/topology_info.json', 'w') as f:
            json.dump(topology_info, f, indent=2)
        info("Generated topology_info.json for linear topology\n")

class GridTopo(Topo):
    """Grid topology for 200+ nodes (default 15x15 = 225 switches)"""
    def build(self, size=15):
        switches = []
        switch_dpid = 1
        port_counters = {}  # Track port numbers per switch
        for i in range(size):
            row = []
            for j in range(size):
                switch = self.addSwitch(f's{switch_dpid}', dpid=str(switch_dpid).zfill(16))
                row.append(switch)
                port_counters[f's{switch_dpid}'] = 1
                info(f"Added switch: s{switch_dpid}\n")
                switch_dpid += 1
            switches.append(row)
        
        # Add hosts (4 hosts at corners)
        hosts = []
        for i in range(1, 5):
            host = self.addHost(f'h{i}', ip=f'10.0.0.{i}/24', mac=f'00:00:00:00:00:0{i}')
            hosts.append(host)
            info(f"Added host: h{i}\n")
        
        # Connect hosts to corner switches
        corner_switches = [
            (hosts[0], switches[0][0], 's1'),
            (hosts[1], switches[0][size-1], f's{size}'),
            (hosts[2], switches[size-1][0], f's{size*(size-1)+1}'),
            (hosts[3], switches[size-1][size-1], f's{size*size}')
        ]
        for host, switch, switch_name in corner_switches:
            port = port_counters[switch_name]
            self.addLink(host, switch, port1=0, port2=port, cls=TCLink, bw=10, delay='1ms', loss=0)
            info(f"Added link: {host.name} (port 0) <-> {switch_name} (port {port})\n")
            port_counters[switch_name] += 1
        
        # Add grid links
        for i in range(size):
            for j in range(size):
                current_switch = switches[i][j]
                current_switch_name = f's{i * size + j + 1}'
                if j < size-1:
                    next_switch = switches[i][j+1]
                    next_switch_name = f's{i * size + j + 2}'
                    port1 = port_counters[current_switch_name]
                    port2 = port_counters[next_switch_name]
                    self.addLink(current_switch, next_switch, port1=port1, port2=port2, cls=TCLink, bw=10, delay='1ms', loss=0)
                    info(f"Added link: {current_switch_name} (port {port1}) <-> {next_switch_name} (port {port2})\n")
                    port_counters[current_switch_name] += 1
                    port_counters[next_switch_name] += 1
                if i < size-1:
                    next_switch = switches[i+1][j]
                    next_switch_name = f's{(i + 1) * size + j + 1}'
                    port1 = port_counters[current_switch_name]
                    port2 = port_counters[next_switch_name]
                    self.addLink(current_switch, next_switch, port1=port1, port2=port2, cls=TCLink, bw=10, delay='1ms', loss=0)
                    info(f"Added link: {current_switch_name} (port {port1}) <-> {next_switch_name} (port {port2})\n")
                    port_counters[current_switch_name] += 1
                    port_counters[next_switch_name] += 1
        
        # Generate topology info
        self.generate_topology_info(switches, hosts, size)

    def generate_topology_info(self, switches, hosts, size):
        """Generate topology_info.json for the grid topology"""
        topology_info = {
            'switches': {f's{i+1}': {'dpid': i+1, 'ports': {}} for i in range(size * size)},
            'hosts': {f'h{i+1}': {'ip': f'10.0.0.{i+1}', 'mac': f'00:00:00:00:00:0{i+1}', 'connected_to': ''} for i in range(len(hosts))},
            'links': []
        }
        
        port_counters = {f's{i+1}': 1 for i in range(size * size)}
        corner_switches = {
            'h1': 's1',
            'h2': f's{size}',
            'h3': f's{size*(size-1)+1}',
            'h4': f's{size*size}'
        }
        for host, switch in corner_switches.items():
            topology_info['hosts'][host]['connected_to'] = switch
            topology_info['switches'][switch]['ports'][host] = port_counters[switch]
            topology_info['links'].append({'src': host, 'dst': switch, 'port': port_counters[switch]})
            port_counters[switch] += 1
        
        for i in range(size):
            for j in range(size):
                switch_id = i * size + j + 1
                current_switch = f's{switch_id}'
                if j < size-1:
                    next_switch = f's{i * size + j + 2}'
                    topology_info['switches'][current_switch]['ports'][next_switch] = port_counters[current_switch]
                    topology_info['switches'][next_switch]['ports'][current_switch] = port_counters[next_switch]
                    topology_info['links'].append({'src': current_switch, 'dst': next_switch, 'port': port_counters[current_switch]})
                    port_counters[current_switch] += 1
                    port_counters[next_switch] += 1
                if i < size-1:
                    next_switch = f's{(i + 1) * size + j + 1}'
                    topology_info['switches'][current_switch]['ports'][next_switch] = port_counters[current_switch]
                    topology_info['switches'][next_switch]['ports'][current_switch] = port_counters[next_switch]
                    topology_info['links'].append({'src': current_switch, 'dst': next_switch, 'port': port_counters[current_switch]})
                    port_counters[current_switch] += 1
                    port_counters[next_switch] += 1
        
        os.makedirs('data/config', exist_ok=True)
        with open('data/config/topology_info.json', 'w') as f:
            json.dump(topology_info, f, indent=2)
        info("Generated topology_info.json for grid topology\n")

def check_controller_connection(ip='127.0.0.1', port=6653, timeout=5):
    """Check if controller is reachable"""
    try:
        with socket.create_connection((ip, port), timeout):
            info(f"Controller at {ip}:{port} is reachable\n")
            return True
    except Exception as e:
        info(f"Failed to connect to controller at {ip}:{port}: {e}\n")
        return False

def install_tools(net):
    """Install iperf and tcpdump on all hosts"""
    for host in net.hosts:
        host.cmd('apt-get update && apt-get install -y iperf tcpdump &')
    max_wait = 60
    start_time = time.time()
    while time.time() - start_time < max_wait:
        all_done = True
        for host in net.hosts:
            if host.cmd('ps aux | grep apt-get | grep -v grep') != '':
                all_done = False
                break
        if all_done:
            break
        time.sleep(2)
    info("Tool installation completed\n")

def trigger_initial_flows(net):
    """Proactively trigger flow installation for all host pairs with retries"""
    hosts = net.hosts
    max_retries = 5
    retry_delay = 3
    controller_ready = False
    
    # Check controller readiness
    start_time = time.time()
    while time.time() - start_time < 30:
        try:
            response = requests.get('http://127.0.0.1:8080/stats', timeout=2.0)
            response.raise_for_status()
            controller_ready = True
            info("Controller is ready\n")
            break
        except Exception as e:
            info(f"Controller not ready: {e}\n")
            time.sleep(1)
    
    if not controller_ready:
        info("Controller not ready after 30 seconds\n")
        return
    
    for i, src_host in enumerate(hosts):
        for j, dst_host in enumerate(hosts):
            if i != j:
                src_ip = src_host.IP()
                dst_ip = dst_host.IP()
                for attempt in range(max_retries):
                    try:
                        payload = {
                            'src_ip': src_ip,
                            'dst_ip': dst_ip,
                            'is_tcp': True
                        }
                        response = requests.post(
                            'http://127.0.0.1:8080/force_path',
                            json=payload,
                            timeout=3.0
                        )
                        response.raise_for_status()
                        info(f"Triggered flow installation for {src_ip} -> {dst_ip}\n")
                        break
                    except Exception as e:
                        info(f"Failed to trigger flow for {src_ip} -> {dst_ip} (attempt {attempt+1}/{max_retries}): {e}\n")
                        if attempt < max_retries - 1:
                            time.sleep(retry_delay)
                        else:
                            info(f"Failed to install flow for {src_ip} -> {dst_ip} after {max_retries} attempts\n")

def run_topology(topo_type='linear', grid_size=15):
    """Run the specified topology"""
    setLogLevel('info')
    
    # Clean up residual interfaces
    os.system('sudo ip link delete s2-eth2 2>/dev/null')
    os.system('sudo ip link delete s17-eth2 2>/dev/null')
    
    if topo_type == 'linear':
        topo = LinearTopo()
    elif topo_type == 'grid':
        topo = GridTopo(size=grid_size)
    else:
        info("Invalid topology type. Use 'linear' or 'grid'.\n")
        return
    
    # Check controller connectivity
    if not check_controller_connection():
        info("Aborting: Cannot connect to controller\n")
        return
    
    net = Mininet(
        topo=topo,
        controller=RemoteController('c0', ip='127.0.0.1', port=6653),
        link=TCLink,
        autoSetMacs=True
    )
    
    info("*** Starting network\n")
    net.start()
    
    info("*** Waiting for controller connection\n")
    time.sleep(15)  # Increased wait time
    
    info("*** Installing tools on hosts\n")
    install_tools(net)
    
    info("*** Triggering initial flow installations\n")
    trigger_initial_flows(net)
    
    info("*** Testing connectivity\n")
    net.pingAll()
    
    info("*** Starting CLI\n")
    CLI(net)
    
    info("*** Stopping network\n")
    net.stop()

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Run Mininet topology for RL-SDN')
    parser.add_argument('--topo', choices=['linear', 'grid'], default='linear', help='Topology type')
    parser.add_argument('--grid-size', type=int, default=15, help='Grid size for grid topology')
    args = parser.parse_args()
    
    run_topology(args.topo, args.grid_size)
