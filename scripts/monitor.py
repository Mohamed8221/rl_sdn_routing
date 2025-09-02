#!/usr/bin/env python3

import os
import sys
import time
import json
import logging
import requests
import psutil
import subprocess
from datetime import datetime
from collections import defaultdict, deque
import threading

# Set up logging
os.makedirs('logs', exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    filename='logs/monitor.log',
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class NetworkMonitor:
    """Network monitoring and statistics collection"""
    
    def __init__(self, poll_interval=0.1, save_interval=5):
        self.poll_interval = poll_interval  # 100ms polling
        self.save_interval = save_interval  # Save stats every 5 seconds
        
        # Data storage
        self.switch_stats = defaultdict(lambda: defaultdict(dict))
        self.flow_stats = defaultdict(list)
        self.network_metrics = deque(maxlen=1000)  # Last 1000 measurements
        
        # Configuration
        self.ryu_controller_url = 'http://127.0.0.1:8080'
        self.rl_agent_url = 'http://127.0.0.1:5000'
        
        # Running state
        self.running = False
        self.threads = []
        
        # Performance metrics
        self.performance_metrics = {
            'latency_samples': deque(maxlen=100),
            'throughput_samples': deque(maxlen=100),
            'packet_loss_samples': deque(maxlen=100),
            'jitter_samples': deque(maxlen=100)
        }
        
        logger.info("Network monitor initialized")
    
    def start_monitoring(self):
        """Start all monitoring threads"""
        if self.running:
            logger.warning("Monitoring already running")
            return
        
        self.running = True
        
        # Start monitoring threads
        self.threads = [
            threading.Thread(target=self._monitor_ovs_switches, daemon=True),
            threading.Thread(target=self._monitor_system_resources, daemon=True),
            threading.Thread(target=self._collect_network_metrics, daemon=True),
            threading.Thread(target=self._save_periodic_data, daemon=True),
            threading.Thread(target=self._monitor_connectivity, daemon=True)
        ]
        
        for thread in self.threads:
            thread.start()
        
        logger.info("Started all monitoring threads")
    
    def stop_monitoring(self):
        """Stop all monitoring"""
        self.running = False
        logger.info("Stopped monitoring")
    
    def _monitor_ovs_switches(self):
        """Monitor OVS switches using ovs-ofctl commands"""
        while self.running:
            try:
                # Get list of bridges
                result = subprocess.run(['ovs-vsctl', 'list-br'], 
                                      capture_output=True, text=True, timeout=5)
                
                if result.returncode == 0:
                    bridges = result.stdout.strip().split('\n')
                    bridges = [b for b in bridges if b.strip()]
                    
                    for bridge in bridges:
                        self._collect_bridge_stats(bridge)
                
            except Exception as e:
                logger.debug(f"Error monitoring OVS switches: {e}")
            
            time.sleep(self.poll_interval)
    
    def _collect_bridge_stats(self, bridge_name):
        """Collect statistics for a specific bridge"""
        try:
            # Get port statistics
            result = subprocess.run(['ovs-ofctl', 'dump-ports', bridge_name],
                                  capture_output=True, text=True, timeout=2)
            
            if result.returncode == 0:
                stats = self._parse_port_stats(result.stdout)
                self.switch_stats[bridge_name]['ports'] = stats
                self.switch_stats[bridge_name]['timestamp'] = time.time()
            
            # Get flow statistics
            result = subprocess.run(['ovs-ofctl', 'dump-flows', bridge_name],
                                  capture_output=True, text=True, timeout=2)
            
            if result.returncode == 0:
                flows = self._parse_flow_stats(result.stdout)
                self.flow_stats[bridge_name] = flows
                
        except Exception as e:
            logger.debug(f"Error collecting stats for bridge {bridge_name}: {e}")
    
    def _parse_port_stats(self, output):
        """Parse ovs-ofctl dump-ports output"""
        port_stats = {}
        
        for line in output.split('\n'):
            if 'port' in line and 'rx' in line:
                try:
                    # Example line: "port  1: rx pkts=123, bytes=456, drop=0, errs=0, frame=0, over=0, crc=0"
                    parts = line.split(':')
                    if len(parts) >= 2:
                        port_num = int(parts[0].split()[-1])
                        stats_part = parts[1]
                        
                        # Parse rx stats
                        rx_stats = {}
                        if 'rx' in stats_part:
                            rx_part = stats_part.split('tx')[0]  # Get rx part only
                            for stat in rx_part.split(','):
                                if '=' in stat:
                                    key, value = stat.strip().split('=')
                                    try:
                                        rx_stats[f'rx_{key}'] = int(value)
                                    except ValueError:
                                        continue
                        
                        # Parse tx stats
                        tx_stats = {}
                        if 'tx' in stats_part:
                            tx_part = stats_part.split('tx')[1]  # Get tx part only
                            for stat in tx_part.split(','):
                                if '=' in stat:
                                    key, value = stat.strip().split('=')
                                    try:
                                        tx_stats[f'tx_{key}'] = int(value)
                                    except ValueError:
                                        continue
                        
                        port_stats[port_num] = {**rx_stats, **tx_stats}
                        
                except (ValueError, IndexError) as e:
                    logger.debug(f"Error parsing port stats line: {line}, error: {e}")
                    continue
        
        return port_stats
    
    def _parse_flow_stats(self, output):
        """Parse ovs-ofctl dump-flows output"""
        flows = []
        
        for line in output.split('\n'):
            if 'priority' in line and 'n_packets' in line:
                try:
                    # Extract flow information
                    flow_info = {
                        'line': line.strip(),
                        'timestamp': time.time()
                    }
                    
                    # Extract packet and byte counts
                    if 'n_packets=' in line:
                        start = line.find('n_packets=') + 10
                        end = line.find(',', start)
                        if end == -1:
                            end = line.find(' ', start)
                        if end != -1:
                            try:
                                flow_info['n_packets'] = int(line[start:end])
                            except ValueError:
                                pass
                    
                    if 'n_bytes=' in line:
                        start = line.find('n_bytes=') + 8
                        end = line.find(',', start)
                        if end == -1:
                            end = line.find(' ', start)
                        if end != -1:
                            try:
                                flow_info['n_bytes'] = int(line[start:end])
                            except ValueError:
                                pass
                    
                    flows.append(flow_info)
                    
                except Exception as e:
                    logger.debug(f"Error parsing flow line: {line}, error: {e}")
        
        return flows
    
    def _monitor_system_resources(self):
        """Monitor system resources (CPU, memory, etc.)"""
        while self.running:
            try:
                # Get system metrics
                cpu_percent = psutil.cpu_percent(interval=None)
                memory = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                # Get network interface stats
                net_io = psutil.net_io_counters()
                
                system_stats = {
                    'timestamp': time.time(),
                    'cpu_percent': cpu_percent,
                    'memory_percent': memory.percent,
                    'memory_used_gb': memory.used / (1024**3),
                    'disk_percent': disk.percent,
                    'network_bytes_sent': net_io.bytes_sent,
                    'network_bytes_recv': net_io.bytes_recv,
                    'network_packets_sent': net_io.packets_sent,
                    'network_packets_recv': net_io.packets_recv
                }
                
                self.switch_stats['system'] = system_stats
                
            except Exception as e:
                logger.debug(f"Error monitoring system resources: {e}")
            
            time.sleep(1.0)  # System monitoring every 1 second
    
    def _collect_network_metrics(self):
        """Collect network performance metrics"""
        while self.running:
            try:
                # Calculate network metrics from switch stats
                total_throughput = 0
                total_packet_loss = 0
                active_switches = 0
                
                current_time = time.time()
                
                for bridge, stats in self.switch_stats.items():
                    if bridge == 'system':
                        continue
                        
                    if 'ports' in stats and 'timestamp' in stats:
                        # Calculate throughput and loss for this switch
                        bridge_throughput = 0
                        bridge_loss = 0
                        
                        for port_num, port_stats in stats['ports'].items():
                            if isinstance(port_stats, dict):
                                rx_bytes = port_stats.get('rx_bytes', 0)
                                tx_bytes = port_stats.get('tx_bytes', 0)
                                rx_dropped = port_stats.get('rx_drop', 0)
                                tx_dropped = port_stats.get('tx_drop', 0)
                                
                                bridge_throughput += rx_bytes + tx_bytes
                                bridge_loss += rx_dropped + tx_dropped
                        
                        total_throughput += bridge_throughput
                        total_packet_loss += bridge_loss
                        active_switches += 1
                
                # Calculate averages
                if active_switches > 0:
                    avg_throughput = total_throughput / active_switches
                    avg_packet_loss = total_packet_loss / active_switches
                else:
                    avg_throughput = 0
                    avg_packet_loss = 0
                
                # Create network state vector for RL agent
                network_state = {
                    'timestamp': current_time,
                    'avg_throughput': avg_throughput,
                    'avg_packet_loss': avg_packet_loss,
                    'num_active_switches': active_switches,
                    'total_switches': len([b for b in self.switch_stats.keys() if b != 'system'])
                }
                
                self.network_metrics.append(network_state)
                
                # Update performance metrics
                self.performance_metrics['throughput_samples'].append(avg_throughput)
                self.performance_metrics['packet_loss_samples'].append(avg_packet_loss)
                
            except Exception as e:
                logger.debug(f"Error collecting network metrics: {e}")
            
            time.sleep(self.poll_interval)
    
    def _monitor_connectivity(self):
        """Monitor network connectivity using ping"""
        while self.running:
            try:
                # Test connectivity between known hosts
                test_pairs = [
                    ('10.0.0.1', '10.0.0.2'),
                    ('10.0.0.1', '10.0.0.3'),
                    ('10.0.0.1', '10.0.0.4')
                ]
                
                for src_ip, dst_ip in test_pairs:
                    try:
                        # Use ping to measure latency
                        result = subprocess.run(
                            ['ping', '-c', '1', '-W', '1', dst_ip],
                            capture_output=True, text=True, timeout=3
                        )
                        
                        if result.returncode == 0:
                            # Parse ping output for latency
                            latency = self._parse_ping_latency(result.stdout)
                            if latency:
                                self.performance_metrics['latency_samples'].append(latency)
                        
                    except Exception as e:
                        logger.debug(f"Ping test {src_ip}->{dst_ip} failed: {e}")
                
            except Exception as e:
                logger.debug(f"Error in connectivity monitoring: {e}")
            
            time.sleep(5.0)  # Connectivity tests every 5 seconds
    
    def _parse_ping_latency(self, ping_output):
        """Parse latency from ping output"""
        try:
            for line in ping_output.split('\n'):
                if 'time=' in line:
                    # Extract time value
                    start = line.find('time=') + 5
                    end = line.find('ms', start)
                    if end != -1:
                        return float(line[start:end])
        except Exception as e:
            logger.debug(f"Error parsing ping latency: {e}")
        return None
    
    def _save_periodic_data(self):
        """Periodically save collected data"""
        while self.running:
            try:
                self._save_statistics()
                self._save_performance_report()
            except Exception as e:
                logger.error(f"Error saving periodic data: {e}")
            
            time.sleep(self.save_interval)
    
    def _save_statistics(self):
        """Save current statistics to file"""
        try:
            os.makedirs('data/logs', exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            
            # Save switch statistics
            stats_file = f'data/logs/switch_stats_{timestamp}.json'
            with open(stats_file, 'w') as f:
                # Convert defaultdict to regular dict for JSON serialization
                stats_data = {
                    'timestamp': time.time(),
                    'switch_stats': dict(self.switch_stats),
                    'flow_stats': dict(self.flow_stats)
                }
                json.dump(stats_data, f, indent=2)
            
            # Save network metrics
            metrics_file = f'data/logs/network_metrics_{timestamp}.json'
            with open(metrics_file, 'w') as f:
                json.dump(list(self.network_metrics), f, indent=2)
            
            logger.debug(f"Saved statistics to {stats_file} and {metrics_file}")
            
        except Exception as e:
            logger.error(f"Error saving statistics: {e}")
    
    def _save_performance_report(self):
        """Generate and save performance report"""
        try:
            # Calculate performance metrics
            report = self._generate_performance_report()
            
            # Save to traffic_results.json (main results file)
            with open('traffic_results.json', 'w') as f:
                json.dump(report, f, indent=2)
            
            # Also save timestamped version
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            report_file = f'data/reports/performance_report_{timestamp}.json'
            os.makedirs(os.path.dirname(report_file), exist_ok=True)
            
            with open(report_file, 'w') as f:
                json.dump(report, f, indent=2)
            
            logger.debug("Generated performance report")
            
        except Exception as e:
            logger.error(f"Error generating performance report: {e}")
    
    def _generate_performance_report(self):
        """Generate comprehensive performance report"""
        import numpy as np
        
        current_time = time.time()
        
        # Calculate statistics for each metric
        def calculate_stats(samples):
            if not samples:
                return {'avg': 0, 'min': 0, 'max': 0, 'std': 0}
            
            return {
                'avg': float(np.mean(samples)),
                'min': float(np.min(samples)),
                'max': float(np.max(samples)),
                'std': float(np.std(samples)),
                'count': len(samples)
            }
        
        # Get RL agent statistics
        rl_stats = {}
        try:
            response = requests.get(f'{self.rl_agent_url}/stats', timeout=2)
            if response.status_code == 200:
                rl_stats = response.json()
        except Exception as e:
            logger.debug(f"Could not fetch RL agent stats: {e}")
        
        # Get controller statistics
        controller_stats = {}
        try:
            response = requests.get(f'{self.ryu_controller_url}/rlcontroller/stats', timeout=2)
            if response.status_code == 200:
                controller_stats = response.json()
        except Exception as e:
            logger.debug(f"Could not fetch controller stats: {e}")
        
        # Generate report
        report = {
            'timestamp': current_time,
            'report_generated': datetime.now().isoformat(),
            'monitoring_duration_seconds': len(self.network_metrics) * self.poll_interval,
            
            # Network Performance Metrics
            'network_performance': {
                'latency_ms': calculate_stats(self.performance_metrics['latency_samples']),
                'throughput_bps': calculate_stats(self.performance_metrics['throughput_samples']),
                'packet_loss_rate': calculate_stats(self.performance_metrics['packet_loss_samples']),
                'jitter_ms': calculate_stats(self.performance_metrics['jitter_samples'])
            },
            
            # System Performance
            'system_performance': {
                'cpu_usage_percent': self.switch_stats.get('system', {}).get('cpu_percent', 0),
                'memory_usage_percent': self.switch_stats.get('system', {}).get('memory_percent', 0),
                'disk_usage_percent': self.switch_stats.get('system', {}).get('disk_percent', 0)
            },
            
            # Topology Information
            'topology_info': {
                'active_switches': len([k for k in self.switch_stats.keys() if k != 'system']),
                'total_flows': sum(len(flows) for flows in self.flow_stats.values()),
                'monitoring_samples': len(self.network_metrics)
            },
            
            # RL Agent Performance
            'rl_agent_performance': rl_stats,
            
            # Controller Statistics
            'controller_stats': controller_stats,
            
            # Raw data availability
            'data_files': {
                'switch_stats': list(self.switch_stats.keys()),
                'flow_stats': list(self.flow_stats.keys()),
                'performance_samples': {
                    'latency': len(self.performance_metrics['latency_samples']),
                    'throughput': len(self.performance_metrics['throughput_samples']),
                    'packet_loss': len(self.performance_metrics['packet_loss_samples'])
                }
            }
        }
        
        return report
    
    def get_current_network_state(self):
        """Get current network state for RL agent"""
        try:
            if not self.network_metrics:
                return (0.0, 0.0, 0.0, 0.0)
            
            latest_metrics = self.network_metrics[-1]
            
            # Calculate utilization (normalized)
            avg_throughput = latest_metrics.get('avg_throughput', 0)
            max_throughput = 1000000000  # 1 Gbps assumption
            utilization = min(avg_throughput / max_throughput, 1.0)
            
            # Calculate packet loss rate (normalized)
            avg_packet_loss = latest_metrics.get('avg_packet_loss', 0)
            packet_loss_rate = min(avg_packet_loss / 1000.0, 1.0)  # Normalize to [0,1]
            
            # Network size metric
            num_switches = latest_metrics.get('num_active_switches', 0)
            network_size = min(num_switches / 100.0, 1.0)  # Normalize to [0,1]
            
            # Queue length approximation (using packet loss as proxy)
            queue_length = packet_loss_rate
            
            return (utilization, packet_loss_rate, network_size, queue_length)
            
        except Exception as e:
            logger.error(f"Error getting network state: {e}")
            return (0.0, 0.0, 0.0, 0.0)
    
    def get_monitoring_summary(self):
        """Get summary of monitoring data"""
        return {
            'monitoring_active': self.running,
            'switches_monitored': len([k for k in self.switch_stats.keys() if k != 'system']),
            'network_samples': len(self.network_metrics),
            'performance_samples': {
                'latency': len(self.performance_metrics['latency_samples']),
                'throughput': len(self.performance_metrics['throughput_samples']),
                'packet_loss': len(self.performance_metrics['packet_loss_samples'])
            },
            'latest_network_state': self.get_current_network_state(),
            'uptime_seconds': time.time() - getattr(self, 'start_time', time.time())
        }


def create_monitoring_plots():
    """Create monitoring visualization plots"""
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        
        os.makedirs('monitoring_plots', exist_ok=True)
        
        # Load latest data
        try:
            with open('traffic_results.json', 'r') as f:
                report = json.load(f)
        except FileNotFoundError:
            logger.warning("No traffic results file found for plotting")
            return
        
        # Create performance plots
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        fig.suptitle('Network Performance Monitoring', fontsize=16)
        
        # Plot 1: Latency over time
        if 'network_performance' in report and 'latency_ms' in report['network_performance']:
            latency_data = report['network_performance']['latency_ms']
            if latency_data['count'] > 0:
                axes[0, 0].bar(['Avg', 'Min', 'Max'], 
                              [latency_data['avg'], latency_data['min'], latency_data['max']],
                              color=['blue', 'green', 'red'])
                axes[0, 0].set_title('Latency (ms)')
                axes[0, 0].set_ylabel('Milliseconds')
        
        # Plot 2: Throughput
        if 'network_performance' in report and 'throughput_bps' in report['network_performance']:
            throughput_data = report['network_performance']['throughput_bps']
            if throughput_data['count'] > 0:
                axes[0, 1].bar(['Avg', 'Min', 'Max'], 
                              [throughput_data['avg']/1000000, throughput_data['min']/1000000, throughput_data['max']/1000000],
                              color=['orange', 'yellow', 'purple'])
                axes[0, 1].set_title('Throughput (Mbps)')
                axes[0, 1].set_ylabel('Mbps')
        
        # Plot 3: Packet Loss
        if 'network_performance' in report and 'packet_loss_rate' in report['network_performance']:
            loss_data = report['network_performance']['packet_loss_rate']
            if loss_data['count'] > 0:
                axes[1, 0].bar(['Avg', 'Min', 'Max'], 
                              [loss_data['avg'], loss_data['min'], loss_data['max']],
                              color=['red', 'orange', 'darkred'])
                axes[1, 0].set_title('Packet Loss Rate')
                axes[1, 0].set_ylabel('Loss Rate')
        
        # Plot 4: System Resources
        if 'system_performance' in report:
            system_data = report['system_performance']
            resources = ['CPU %', 'Memory %', 'Disk %']
            values = [
                system_data.get('cpu_usage_percent', 0),
                system_data.get('memory_usage_percent', 0),
                system_data.get('disk_usage_percent', 0)
            ]
            axes[1, 1].bar(resources, values, color=['lightblue', 'lightgreen', 'lightcoral'])
            axes[1, 1].set_title('System Resource Usage')
            axes[1, 1].set_ylabel('Percentage')
        
        # Save plot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plot_file = f'monitoring_plots/performance_plot_{timestamp}.png'
        plt.tight_layout()
        plt.savefig(plot_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Generated monitoring plot: {plot_file}")
        
        # Create RL agent performance plot if data available
        if 'rl_agent_performance' in report and report['rl_agent_performance']:
            create_rl_performance_plot(report['rl_agent_performance'])
        
    except ImportError:
        logger.warning("Matplotlib not available, skipping plot generation")
    except Exception as e:
        logger.error(f"Error creating monitoring plots: {e}")


def create_rl_performance_plot(rl_stats):
    """Create RL agent specific performance plots"""
    try:
        import matplotlib.pyplot as plt
        
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        fig.suptitle('RL Agent Performance', fontsize=16)
        
        # Plot 1: Reward over time
        if 'recent_rewards' in rl_stats and rl_stats['recent_rewards']:
            rewards = rl_stats['recent_rewards']
            axes[0].plot(rewards, color='blue')
            axes[0].set_title('Recent Rewards')
            axes[0].set_xlabel('Time Steps')
            axes[0].set_ylabel('Reward')
            axes[0].grid(True, alpha=0.3)
        
        # Plot 2: Epsilon decay
        if 'epsilon' in rl_stats:
            epsilon_value = rl_stats['epsilon']
            axes[1].bar(['Current Epsilon'], [epsilon_value], color='green')
            axes[1].set_title('Exploration Rate')
            axes[1].set_ylabel('Epsilon Value')
            axes[1].set_ylim(0, 1)
        
        # Plot 3: Agent statistics
        stats_labels = []
        stats_values = []
        
        if 'total_requests' in rl_stats:
            stats_labels.append('Total\nRequests')
            stats_values.append(rl_stats['total_requests'])
        
        if 'average_reward' in rl_stats:
            stats_labels.append('Avg\nReward')
            stats_values.append(rl_stats['average_reward'])
        
        if 'memory_size' in rl_stats:
            stats_labels.append('Memory\nSize')
            stats_values.append(rl_stats['memory_size'])
        
        if stats_labels:
            axes[2].bar(stats_labels, stats_values, color=['orange', 'purple', 'red'][:len(stats_labels)])
            axes[2].set_title('Agent Statistics')
        
        # Save plot
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        plot_file = f'monitoring_plots/rl_performance_{timestamp}.png'
        plt.tight_layout()
        plt.savefig(plot_file, dpi=300, bbox_inches='tight')
        plt.close()
        
        logger.info(f"Generated RL performance plot: {plot_file}")
        
    except Exception as e:
        logger.error(f"Error creating RL performance plot: {e}")


def main():
    """Main function to run network monitoring"""
    try:
        # Initialize monitor
        monitor = NetworkMonitor(poll_interval=0.1, save_interval=10)
        monitor.start_time = time.time()
        
        logger.info("Starting network monitoring...")
        print("Starting network monitoring... (Press Ctrl+C to stop)")
        
        # Start monitoring
        monitor.start_monitoring()
        
        # Main loop - generate plots periodically
        last_plot_time = time.time()
        plot_interval = 60  # Generate plots every minute
        
        try:
            while True:
                time.sleep(5)
                
                # Print monitoring summary
                summary = monitor.get_monitoring_summary()
                print(f"\rSwitches: {summary['switches_monitored']}, "
                      f"Samples: {summary['network_samples']}, "
                      f"Uptime: {summary['uptime_seconds']:.0f}s", end='', flush=True)
                
                # Generate plots periodically
                current_time = time.time()
                if current_time - last_plot_time >= plot_interval:
                    create_monitoring_plots()
                    last_plot_time = current_time
                
        except KeyboardInterrupt:
            print("\nStopping monitoring...")
            
        finally:
            monitor.stop_monitoring()
            
            # Generate final plots and report
            create_monitoring_plots()
            
            print("Final performance report saved to traffic_results.json")
            print("Monitoring plots saved to monitoring_plots/")
            
    except Exception as e:
        logger.error(f"Error in main monitoring loop: {e}")
        print(f"Error: {e}")


if __name__ == '__main__':
    # Create necessary directories
    os.makedirs('data/logs', exist_ok=True)
    os.makedirs('data/reports', exist_ok=True)
    os.makedirs('monitoring_plots', exist_ok=True)
    
    main()
