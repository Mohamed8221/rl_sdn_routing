#!/usr/bin/env python3

import json
import logging
import os
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp
from ryu.app.wsgi import ControllerBase, WSGIApplication, route
from webob import Response
import networkx as nx
import requests
import time

# Configure logging
logging.basicConfig(filename='logs/ryu_controller.log', level=logging.DEBUG)
logger = logging.getLogger(__name__)

REROUTE_TIMEOUT = 2.0

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    _CONTEXTS = {'wsgi': WSGIApplication}

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.topology_graph = nx.Graph()
        self.switches = {}
        self.hosts = {}
        self.datapaths = {}
        self.flow_stats = {'count': 0, 'flows': []}
        self.existing_flows = {}  # Track installed flows to avoid duplicates
        self.wsgi = kwargs['wsgi']
        self.wsgi.register(RLControllerAPI, {'controller': self})
        logger.info("SimpleSwitch13 initialized")

    def add_flow(self, datapath, priority, match, actions, idle_timeout=120, hard_timeout=300):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
        # Check for duplicate flows
        flow_key = (datapath.id, str(match), str(actions))
        if flow_key in self.existing_flows:
            logger.debug(f"Flow already exists for dpid={datapath.id}, match={match}, actions={actions}")
            return
        datapath.send_msg(mod)
        self.flow_stats['count'] += 1
        self.flow_stats['flows'].append({
            'dpid': datapath.id,
            'src_ip': match.get('ipv4_src', 'unknown'),
            'dst_ip': match.get('ipv4_dst', 'unknown'),
            'actions': [str(action) for action in actions]
        })
        self.existing_flows[flow_key] = True
        logger.info(f"Added flow: dpid={datapath.id}, match={match}, actions={actions}")

    def _get_switch_for_ip(self, ip):
        try:
            with open('data/config/topology_info.json', 'r') as f:
                topology_info = json.load(f)
            for host, info in topology_info['hosts'].items():
                if info['ip'] == ip:
                    switch_name = info['connected_to']
                    return topology_info['switches'][switch_name]['dpid']
            logger.warning(f"No switch found for IP {ip}")
            return None
        except Exception as e:
            logger.error(f"Error reading topology_info.json: {e}")
            return None

    def _get_shortest_path(self, src_switch, dst_switch):
        try:
            path = nx.shortest_path(self.topology_graph, src_switch, dst_switch)
            logger.info(f"Shortest path from {src_switch} to {dst_switch}: {path}")
            return path
        except nx.NetworkXNoPath:
            logger.warning(f"No path found from {src_switch} to {dst_switch}")
            return []

    def _request_path_from_rl_agent(self, src_switch, dst_switch, network_state):
        try:
            # Convert switch IDs to strings for RL agent compatibility
            payload = {
                'src': str(src_switch),
                'dst': str(dst_switch),
                'state': list(network_state)
            }
            logger.debug(f"Sending payload to RL agent: {payload}")
            response = requests.post('http://127.0.0.1:5000/get_path', json=payload, timeout=2.0)
            response.raise_for_status()
            logger.info(f"RL agent path for {src_switch}->{dst_switch}: {response.json()}")
            return response.json()
        except Exception as e:
            logger.error(f"Error requesting path from RL agent: {e}")
            return {}

    def _install_path_flows(self, path, src_ip, dst_ip, is_tcp=True):
        for i in range(len(path) - 1):
            src_dpid = path[i]
            dst_dpid = path[i + 1]
            datapath = self.datapaths.get(src_dpid)
            if not datapath:
                logger.error(f"No datapath for dpid {src_dpid}")
                continue
            ofproto = datapath.ofproto
            parser = datapath.ofproto_parser
            try:
                port = self.topology_graph[src_dpid][dst_dpid]['port']
            except KeyError:
                logger.error(f"No port found for edge {src_dpid}->{dst_dpid}")
                continue
            match = parser.OFPMatch(
                eth_type=0x0800,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=6  # Force TCP
            )
            actions = [parser.OFPActionOutput(port)]
            self.add_flow(datapath, 10, match, actions)
            logger.info(f"Installed TCP flow: {src_ip} -> {dst_ip} via port {port} on dpid {src_dpid}")

    def _reroute_affected_flows(self, dpid, port_no):
        logger.info(f"Rerouting flows for dpid={dpid}, port={port_no}")
        affected_flows = []
        for flow in self.flow_stats['flows']:
            if flow['dpid'] == dpid:
                affected_flows.append((flow['src_ip'], flow['dst_ip']))
        for src_ip, dst_ip in affected_flows:
            src_switch = self._get_switch_for_ip(src_ip)
            dst_switch = self._get_switch_for_ip(dst_ip)
            if src_switch and dst_switch:
                network_state = self._get_current_network_state()
                path_info = self._request_path_from_rl_agent(src_switch, dst_switch, network_state)
                path = path_info.get('path', []) if path_info else []
                if not path:
                    logger.warning(f"RL agent failed for {src_ip}->{dst_ip}, using shortest path")
                    path = self._get_shortest_path(src_switch, dst_switch)
                if path:
                    self._install_path_flows(path, src_ip, dst_ip, is_tcp=True)
                    logger.info(f"Rerouted TCP flow: {src_ip} -> {dst_ip} via path {path}")
        time.sleep(REROUTE_TIMEOUT)

    def _get_current_network_state(self):
        try:
            response = requests.get('http://127.0.0.1:5000/stats', timeout=2.0)
            response.raise_for_status()
            rl_stats = response.json()
        except Exception as e:
            logger.error(f"Error fetching RL agent stats: {e}")
            rl_stats = {'count': 0, 'recent_rewards': [], 'paths': {}}
        
        state = [
            self.flow_stats['count'],
            len(self.flow_stats['flows']),
            len(self.topology_graph.edges()) / max(len(self.topology_graph.nodes()) * (len(self.topology_graph.nodes()) - 1) / 2, 1),
            len(rl_stats['recent_rewards'])
        ]
        logger.debug(f"Current network state: {state}")
        return state

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        self.datapaths[dpid] = datapath
        logger.info(f"Switch connected: dpid={dpid}")

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions, idle_timeout=0, hard_timeout=0)

        match = parser.OFPMatch(eth_type=0x0806)
        actions = [parser.OFPActionOutput(ofproto.OFPP_FLOOD)]
        self.add_flow(datapath, 5, match, actions)

        # Update topology graph
        try:
            if not os.path.exists('data/config/topology_info.json'):
                logger.error("topology_info.json not found")
                return
            with open('data/config/topology_info.json', 'r') as f:
                topology_info = json.load(f)
            
            # Add switches as nodes
            for switch_name, info in topology_info['switches'].items():
                dpid = info['dpid']
                self.topology_graph.add_node(dpid)
                self.switches[dpid] = switch_name
                logger.debug(f"Added switch node: dpid={dpid}, name={switch_name}")
            
            # Add edges from links
            for link in topology_info['links']:
                src = link['src']
                dst = link['dst']
                port = link['port']
                if src.startswith('s') and dst.startswith('s'):
                    src_dpid = topology_info['switches'][src]['dpid']
                    dst_dpid = topology_info['switches'][dst]['dpid']
                    self.topology_graph.add_edge(src_dpid, dst_dpid, port=port)
                    logger.debug(f"Added edge: {src_dpid}->{dst_dpid}, port={port}")
                elif src.startswith('h'):
                    host_ip = topology_info['hosts'][src]['ip']
                    switch_dpid = topology_info['switches'][dst]['dpid']
                    self.hosts.setdefault(switch_dpid, []).append(host_ip)
                    logger.debug(f"Added host: {host_ip} connected to dpid={switch_dpid}")
            
            logger.info(f"Topology graph updated with {len(self.topology_graph.nodes())} nodes, {len(self.topology_graph.edges())} edges")
        except Exception as e:
            logger.error(f"Error updating topology graph: {e}")

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        port_no = msg.desc.port_no
        reason = msg.reason
        dpid = dp.id
        
        logger.info(f"Port status changed: dpid={dpid}, port={port_no}, reason={reason}")
        
        if reason in [ofproto_v1_3.OFPPR_DELETE, ofproto_v1_3.OFPPR_MODIFY]:
            try:
                for neighbor in list(self.topology_graph[dpid]):
                    if self.topology_graph[dpid][neighbor].get('port') == port_no:
                        self.topology_graph.remove_edge(dpid, neighbor)
                        logger.info(f"Removed edge for dpid={dpid}, port={port_no}")
                        self._reroute_affected_flows(dpid, port_no)
            except Exception as e:
                logger.error(f"Error updating topology graph: {e}")
        elif reason == ofproto_v1_3.OFPPR_ADD:
            logger.info(f"Port {port_no} added for dpid={dpid}")

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        dpid = datapath.id

        logger.debug(f"PacketIn: dpid={dpid}, in_port={in_port}, eth_src={eth.src}, eth_dst={eth.dst}")

        if eth.ethertype == 0x0806:  # ARP
            logger.debug("ARP packet, flooding")
            return

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][eth.src] = in_port

        if eth.dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][eth.dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]
        if out_port != ofproto.OFPP_FLOOD:
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            if ip_pkt:
                src_ip = ip_pkt.src
                dst_ip = ip_pkt.dst
                logger.debug(f"IP packet: src_ip={src_ip}, dst_ip={dst_ip}")
                src_switch = self._get_switch_for_ip(src_ip)
                dst_switch = self._get_switch_for_ip(dst_ip)
                if src_switch and dst_switch:
                    network_state = self._get_current_network_state()
                    path_info = self._request_path_from_rl_agent(src_switch, dst_switch, network_state)
                    path = path_info.get('path', []) if path_info else []
                    if not path:
                        logger.warning(f"RL agent failed for {src_ip}->{dst_ip}, using shortest path")
                        path = self._get_shortest_path(src_switch, dst_switch)
                    if path:
                        self._install_path_flows(path, src_ip, dst_ip, is_tcp=True)  # Force TCP

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:  # Correct constant
            data = msg.data
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)
        logger.debug(f"Sent PacketOut: dpid={dpid}, out_port={out_port}, buffer_id={msg.buffer_id}")

class RLControllerAPI(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(RLControllerAPI, self).__init__(req, link, data, **config)
        self.controller = data['controller']

    @route('rlcontroller', '/force_path', methods=['POST'])
    def force_path_installation(self, req, **kwargs):
        """Manually force path installation (for testing)"""
        try:
            data = json.loads(req.body.decode('utf-8'))
            src_ip = data.get('src_ip')
            dst_ip = data.get('dst_ip')
            is_tcp = data.get('is_tcp', True)  # Default to TCP
            path = data.get('path', [])
            
            if not src_ip or not dst_ip:
                logger.error("Missing src_ip or dst_ip in request")
                return Response(status=400, body=json.dumps({'error': 'Missing src_ip or dst_ip'}), content_type='application/json; charset=UTF-8')
            
            # Wait for topology to initialize
            max_wait = 30
            start_time = time.time()
            while time.time() - start_time < max_wait:
                if self.controller.topology_graph.nodes:
                    logger.info(f"Topology graph ready with {len(self.controller.topology_graph.nodes())} nodes")
                    break
                logger.debug("Waiting for topology graph to initialize")
                time.sleep(1)
            
            if not self.controller.topology_graph.nodes:
                logger.error("Topology graph not initialized after 30 seconds")
                return Response(status=503, body=json.dumps({'error': 'Topology not ready'}), content_type='application/json; charset=UTF-8')
            
            src_switch = self.controller._get_switch_for_ip(src_ip)
            dst_switch = self.controller._get_switch_for_ip(dst_ip)
            if not src_switch or not dst_switch:
                logger.error(f"Cannot find switches for {src_ip} -> {dst_ip}")
                return Response(status=400, body=json.dumps({'error': f'Cannot find switches for {src_ip} -> {dst_ip}'}), content_type='application/json; charset=UTF-8')
            
            if not path:
                network_state = self.controller._get_current_network_state()
                path_info = self.controller._request_path_from_rl_agent(src_switch, dst_switch, network_state)
                path = path_info.get('path', []) if path_info else []
                if not path:
                    logger.warning(f"RL agent failed for {src_ip}->{dst_ip}, using shortest path")
                    path = self.controller._get_shortest_path(src_switch, dst_switch)
            
            if not path:
                logger.error(f"No valid path found for {src_ip} -> {dst_ip}")
                return Response(status=400, body=json.dumps({'error': 'No valid path found'}), content_type='application/json; charset=UTF-8')
            
            self.controller._install_path_flows(path, src_ip, dst_ip, is_tcp=True)  # Force TCP
            logger.info(f"Installed TCP path {path} for {src_ip} -> {dst_ip}")
            
            return Response(
                content_type='application/json; charset=UTF-8',
                body=json.dumps({'status': 'success', 'message': f'Path {path} installed for {src_ip} -> {dst_ip}'})
            )
        except Exception as e:
            logger.error("Error forcing path installation: %s", e)
            return Response(status=500, body=json.dumps({'error': str(e)}), content_type='application/json; charset=UTF-8')

    @route('rlcontroller', '/force_sp_path', methods=['POST'])
    def force_sp_path_installation(self, req, **kwargs):
        """Manually force shortest path installation (for comparison)"""
        try:
            data = json.loads(req.body.decode('utf-8'))
            src_ip = data.get('src_ip')
            dst_ip = data.get('dst_ip')
            is_tcp = data.get('is_tcp', True)  # Default to TCP
            path = data.get('path', [])
            
            if not src_ip or not dst_ip or not path:
                logger.error("Missing src_ip, dst_ip, or path in request")
                return Response(status=400, body=json.dumps({'error': 'Missing src_ip, dst_ip, or path'}), content_type='application/json; charset=UTF-8')
            
            self.controller._install_path_flows(path, src_ip, dst_ip, is_tcp=True)  # Force TCP
            logger.info(f"Installed TCP shortest path {path} for {src_ip} -> {dst_ip}")
            
            return Response(
                content_type='application/json; charset=UTF-8',
                body=json.dumps({'status': 'success', 'message': f'Shortest path {path} installed for {src_ip} -> {dst_ip}'})
            )
        except Exception as e:
            logger.error("Error forcing shortest path installation: %s", e)
            return Response(status=500, body=json.dumps({'error': str(e)}), content_type='application/json; charset=UTF-8')

    @route('rlcontroller', '/stats', methods=['GET'])
    def get_stats(self, req, **kwargs):
        """Return network statistics"""
        try:
            stats = self.controller._get_current_network_state()
            return Response(
                content_type='application/json; charset=UTF-8',
                body=json.dumps({'status': 'success', 'stats': stats})
            )
        except Exception as e:
            logger.error("Error retrieving stats: %s", e)
            return Response(status=500, body=json.dumps({'error': str(e)}), content_type='application/json; charset=UTF-8')
