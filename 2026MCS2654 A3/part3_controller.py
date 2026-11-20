#!/usr/bin/env python3
"""
COL7524: Advanced Networks - Assignment 3
Name: Karan Joshi (Entry No: 2026MCS2654)

Part 3: Congestion-Aware Routing Controller
Uses OpenFlow 1.3 on Ryu SDN Framework.
Monitors switch port statistics periodically, estimates link utilization,
penalizes congested link costs, and adapts Dijkstra shortest-path calculations
for new incoming flows while preserving existing active flows.

Operating Modes (configured via ROUTING_MODE environment variable):
- ROUTING_MODE=dynamic (Default): Dynamically penalizes links exceeding the 70%
  utilization threshold (+200ms penalty) and routes new flows over alternative paths.
- ROUTING_MODE=static: Continuously collects and logs port statistics/utilization
  without altering static link costs (baseline reference mode).

Configuration:
- LINK_CONFIG: Path to JSON topology properties (default: p3_baseline.json).
- MONITOR_INTERVAL: Polling interval in seconds (default: 2s).
- CONGESTION_THRESHOLD: Congestion trigger threshold (default: 0.70 / 70%).

Run Command:
  ROUTING_MODE=dynamic ryu-manager part3_controller.py
  ROUTING_MODE=static ryu-manager part3_controller.py
"""

import os
import time
import heapq
try:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib import hub
    from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4, tcp, udp
except ImportError:
    import logging

    class app_manager:
        class RyuApp:
            def __init__(self, *args, **kwargs):
                self.logger = logging.getLogger(self.__class__.__name__)
                if not self.logger.handlers:
                    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    class ofproto_v1_3:
        OFP_VERSION = 4

    class hub:
        @staticmethod
        def spawn(func, *args, **kwargs):
            return None

        @staticmethod
        def sleep(sec):
            pass

    def set_ev_cls(*args, **kwargs):
        def decorator(f):
            return f
        return decorator

    class ofp_event:
        class EventOFPSwitchFeatures: pass
        class EventOFPPacketIn: pass
        class EventOFPPortStatsReply: pass
    CONFIG_DISPATCHER = "config"
    MAIN_DISPATCHER = "main"
    ethernet = None
    packet = None
    ether_types = None
    arp = None
    ipv4 = None
    tcp = None
    udp = None


class Part3CongestionAwareController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Part3CongestionAwareController, self).__init__(*args, **kwargs)

        self.datapaths = {}

        # Operating Mode: "dynamic" (default) or "static"
        # In static mode, congestion is observed but link costs remain static
        self.routing_mode = os.environ.get("ROUTING_MODE", "dynamic").lower()

        # Monitoring configuration
        self.MONITOR_INTERVAL = 2  # polling interval in seconds
        self.CONGESTION_THRESHOLD = 0.70  # 70% link capacity threshold
        self.CONGESTION_PENALTY = 200.0   # Cost added to congested link

        # Switch topology
        self.nodes = [1, 2, 3, 4]
        self.adjacency = {
            1: {2: 2, 4: 3},
            2: {1: 2, 3: 3},
            3: {2: 2, 4: 3},
            4: {3: 2, 1: 3},
        }

        # Port to neighbor mapping: (dpid, port) -> neighbor_dpid
        self.port_to_neighbor = {
            (1, 2): 2, (1, 3): 4,
            (2, 2): 1, (2, 3): 3,
            (3, 2): 2, (3, 3): 4,
            (4, 2): 3, (4, 3): 1,
        }

        # Load link configuration from JSON file (default: p3_baseline.json)
        config_path = os.environ.get("LINK_CONFIG", "p3_baseline.json")
        self.base_properties = self._load_link_config(config_path)

        # Dynamic link costs (updated based on utilization)
        self.link_costs = {}
        for link, props in self.base_properties.items():
            self.link_costs[link] = props["delay"]

        # Port statistics history: (dpid, port_no) -> (tx_bytes, timestamp)
        self.port_stats_history = {}

        # Port transmit rate history: (dpid, port_no) -> tx_rate_mbps
        self.port_tx_rates = {}

        # Link utilization tracking: (u, v) -> utilization ratio [0.0 - 1.0+]
        self.link_utilization = {link: 0.0 for link in self.base_properties}

        # Host attachments: MAC -> (switch_dpid, host_port, IP)
        # Seeded with standard network mapping; dynamically updated when hosts transmit packets
        self.host_db = {
            "00:00:00:00:00:01": {"dpid": 1, "port": 1, "ip": "10.0.0.1"},
            "00:00:00:00:00:02": {"dpid": 2, "port": 1, "ip": "10.0.0.2"},
            "00:00:00:00:00:03": {"dpid": 3, "port": 1, "ip": "10.0.0.3"},
            "00:00:00:00:00:04": {"dpid": 4, "port": 1, "ip": "10.0.0.4"},
        }
        self.ip_to_mac = {info["ip"]: mac for mac, info in self.host_db.items()}

        # Spawn periodic statistics monitor green-thread
        self.monitor_thread = hub.spawn(self._monitor)
        self.logger.info(
            "Part 3 Congestion-Aware Controller initialized in '%s' mode (Threshold: %.0f%%, Interval: %ds)",
            self.routing_mode.upper(), self.CONGESTION_THRESHOLD * 100, self.MONITOR_INTERVAL,
        )

    def _load_link_config(self, config_path):
        """Loads link bandwidth and delay properties from a JSON file."""
        import json
        props = {
            (1, 2): {"bw": 2.0, "delay": 20.0},
            (2, 1): {"bw": 2.0, "delay": 20.0},
            (2, 3): {"bw": 2.0, "delay": 10.0},
            (3, 2): {"bw": 2.0, "delay": 10.0},
            (3, 4): {"bw": 1.0, "delay": 20.0},
            (4, 3): {"bw": 1.0, "delay": 20.0},
            (4, 1): {"bw": 1.0, "delay": 15.0},
            (1, 4): {"bw": 1.0, "delay": 15.0},
        }
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path) as f:
                    cfg = json.load(f)
                links = cfg.get("links", cfg)
                for k, v in links.items():
                    parts = k.replace("s", "").split("-")
                    if len(parts) == 2:
                        u, w = int(parts[0]), int(parts[1])
                        bw = float(v.get("bw", 1.0))
                        delay = float(v.get("delay", 10.0))
                        props[(u, w)] = {"bw": bw, "delay": delay}
                        props[(w, u)] = {"bw": bw, "delay": delay}
                self.logger.info("Loaded base link properties from config file: %s", config_path)
            except Exception as e:
                self.logger.warning("Could not parse config %s: %s. Using defaults.", config_path, e)
        return props

    def _learn_host(self, dpid, in_port, src_mac, src_ip=None):
        """Dynamically learns host attachment point on host-facing access ports."""
        if in_port in self.adjacency.get(dpid, {}).values():
            return
        if src_mac not in self.host_db or self.host_db[src_mac]["dpid"] != dpid:
            ip = src_ip if src_ip else self.host_db.get(src_mac, {}).get("ip")
            self.host_db[src_mac] = {"dpid": dpid, "port": in_port, "ip": ip}
            if ip:
                self.ip_to_mac[ip] = src_mac
            self.logger.info("[HOST LEARNED] Host MAC %s attached to s%d port %d (IP: %s)", src_mac, dpid, in_port, ip)

    def _monitor(self):
        """Periodically polls switch port statistics every MONITOR_INTERVAL seconds."""
        while True:
            for dp in list(self.datapaths.values()):
                self._request_port_stats(dp)
            hub.sleep(self.MONITOR_INTERVAL)

    def _request_port_stats(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """
        Processes switch port statistics, computes link utilization,
        and dynamically updates link costs if utilization exceeds threshold.
        """
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        now = time.time()

        for stat in body:
            port_no = stat.port_no
            # Ignore local / internal ports
            if port_no > 10:
                continue

            # Identify if this port connects to another switch
            if (dpid, port_no) in self.port_to_neighbor:
                neighbor = self.port_to_neighbor[(dpid, port_no)]
                link = (dpid, neighbor)
                rev_link = (neighbor, dpid)

                tx_bytes = stat.tx_bytes
                key = (dpid, port_no)

                if key in self.port_stats_history:
                    prev_tx, prev_time = self.port_stats_history[key]
                    delta_bytes = tx_bytes - prev_tx
                    delta_t = now - prev_time

                    if delta_t > 0:
                        # Throughput in Mbps on this port
                        tx_rate_mbps = (delta_bytes * 8.0) / (delta_t * 1e6)
                        self.port_tx_rates[key] = tx_rate_mbps

                        # Look up reverse direction rate on neighbor's connecting port
                        rev_port = self.adjacency[neighbor][dpid]
                        rev_rate = self.port_tx_rates.get((neighbor, rev_port), 0.0)

                        # Link-level utilization considers peak utilization across the link
                        max_rate = max(tx_rate_mbps, rev_rate)
                        capacity_mbps = self.base_properties[link]["bw"]
                        util = max_rate / capacity_mbps
                        self.link_utilization[link] = util
                        self.link_utilization[rev_link] = util

                        # Per-poll telemetry in BOTH modes (parsed by run_experiments.py for the utilization timeline)
                        self.logger.info(
                            "[TELEMETRY] t=%.3f link=s%d-s%d rate_mbps=%.3f util_pct=%.1f cost_ms=%.1f mode=%s",
                            now, dpid, neighbor, max_rate, util * 100,
                            self.link_costs[link], self.routing_mode,
                        )

                        # Congestion rule applies only in dynamic mode; static mode keeps costs fixed
                        if self.routing_mode == "dynamic":
                            if util >= self.CONGESTION_THRESHOLD:
                                new_cost = self.base_properties[link]["delay"] + self.CONGESTION_PENALTY
                                if self.link_costs[link] != new_cost:
                                    self.link_costs[link] = new_cost
                                    self.link_costs[rev_link] = new_cost
                                    self.logger.warning(
                                        "[CONGESTION DETECTED] Link (s%d <-> s%d): Rate=%.2f Mbps (%.1f%% of %.1f Mbps). "
                                        "Threshold %.0f%% exceeded! Dynamic cost escalated: %.1f -> %.1f",
                                        dpid, neighbor, max_rate, util * 100, capacity_mbps,
                                        self.CONGESTION_THRESHOLD * 100, self.base_properties[link]["delay"], new_cost,
                                    )
                            else:
                                base_cost = self.base_properties[link]["delay"]
                                if self.link_costs[link] != base_cost:
                                    self.link_costs[link] = base_cost
                                    self.link_costs[rev_link] = base_cost
                                    self.logger.info(
                                        "[CONGESTION CLEARED] Link (s%d <-> s%d): Rate=%.2f Mbps (%.1f%%). "
                                        "Cost restored to base: %.1f",
                                        dpid, neighbor, max_rate, util * 100, base_cost,
                                    )

                self.port_stats_history[key] = (tx_bytes, now)

    def dijkstra(self, src, dst):
        """Computes shortest path using current dynamic link costs."""
        dist = {node: float("inf") for node in self.nodes}
        prev = {node: None for node in self.nodes}
        dist[src] = 0.0
        pq = [(0.0, src)]

        while pq:
            d, u = heapq.heappop(pq)
            if d > dist[u]:
                continue
            if u == dst:
                break
            for v in self.adjacency.get(u, {}):
                cost = self.link_costs.get((u, v), 50.0)
                if dist[u] + cost < dist[v]:
                    dist[v] = dist[u] + cost
                    prev[v] = u
                    heapq.heappush(pq, (dist[v], v))

        path = []
        curr = dst
        while curr is not None:
            path.append(curr)
            curr = prev[curr]
        path.reverse()

        if path and path[0] == src:
            return path, dist[dst]
        return None, float("inf")

    def add_flow(self, datapath, priority, match, actions, idle_timeout=30, hard_timeout=0):
        """Installs an OpenFlow forwarding rule."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Registers switch and sets default table-miss entry."""
        datapath = ev.msg.datapath
        dpid = datapath.id
        self.datapaths[dpid] = datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, priority=0, match=match, actions=actions, idle_timeout=0)
        self.logger.info("Switch s%d connected to Part 3 controller.", dpid)

    def handle_arp(self, datapath, in_port, pkt_ethernet, pkt_arp):
        """Answers ARP requests to eliminate ring broadcast loops and learns host attachments."""
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Dynamically learn querying host attachment
        self._learn_host(datapath.id, in_port, pkt_ethernet.src, pkt_arp.src_ip)

        if pkt_arp.opcode != arp.ARP_REQUEST:
            return

        target_ip = pkt_arp.dst_ip
        if target_ip in self.ip_to_mac:
            target_mac = self.ip_to_mac[target_ip]
            reply_pkt = packet.Packet()
            reply_pkt.add_protocol(
                ethernet.ethernet(
                    ethertype=ether_types.ETH_TYPE_ARP,
                    dst=pkt_ethernet.src,
                    src=target_mac,
                )
            )
            reply_pkt.add_protocol(
                arp.arp(
                    opcode=arp.ARP_REPLY,
                    src_mac=target_mac,
                    src_ip=target_ip,
                    dst_mac=pkt_ethernet.src,
                    dst_ip=pkt_arp.src_ip,
                )
            )
            reply_pkt.serialize()

            actions = [parser.OFPActionOutput(in_port)]
            out = parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=ofproto.OFP_NO_BUFFER,
                in_port=ofproto.OFPP_CONTROLLER,
                actions=actions,
                data=reply_pkt.data,
            )
            datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Assigns routes to new flows using updated link cost measurements.
        Matches flow at L4 (UDP/TCP ports) or L3 (IP) to differentiate concurrent flows.
        """
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        in_port = msg.match["in_port"]
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP or eth.ethertype == ether_types.ETH_TYPE_IPV6:
            return

        pkt_arp = pkt.get_protocol(arp.arp)
        if pkt_arp:
            self.handle_arp(datapath, in_port, eth, pkt_arp)
            return

        src_mac = eth.src
        dst_mac = eth.dst

        # Inspect IPv4 header and dynamically learn source host attachment point
        pkt_ip = pkt.get_protocol(ipv4.ipv4)
        src_ip = pkt_ip.src if pkt_ip else None
        self._learn_host(dpid, in_port, src_mac, src_ip)

        if dst_mac not in self.host_db or src_mac not in self.host_db:
            return

        src_info = self.host_db[src_mac]
        dst_info = self.host_db[dst_mac]
        src_sw = src_info["dpid"]
        dst_sw = dst_info["dpid"]

        # Intra-switch
        if src_sw == dst_sw:
            match = parser.OFPMatch(eth_dst=dst_mac)
            actions = [parser.OFPActionOutput(dst_info["port"])]
            self.add_flow(datapath, priority=10, match=match, actions=actions)
            out = parser.OFPPacketOut(
                datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port,
                actions=actions, data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None,
            )
            datapath.send_msg(out)
            return

        # Inter-switch flow: compute shortest path using dynamic link weights
        path, total_cost = self.dijkstra(src_sw, dst_sw)
        if not path:
            self.logger.error("No path found between s%d and s%d!", src_sw, dst_sw)
            return

        # Inspect L4 protocol and ports for fine-grained flow differentiation
        pkt_ip = pkt.get_protocol(ipv4.ipv4)
        pkt_tcp = pkt.get_protocol(tcp.tcp)
        pkt_udp = pkt.get_protocol(udp.udp)

        flow_desc = f"{src_info['ip']} -> {dst_info['ip']}"
        l4_port = None
        if pkt_udp:
            flow_desc += f" (UDP dst_port={pkt_udp.dst_port})"
            l4_port = pkt_udp.dst_port
        elif pkt_tcp:
            flow_desc += f" (TCP dst_port={pkt_tcp.dst_port})"
            l4_port = pkt_tcp.dst_port

        self.logger.info(
            "[NEW FLOW ROUTED] [%s MODE] Flow: %s | Selected Path: %s | Dynamic Cost: %.2f",
            self.routing_mode.upper(), flow_desc, " -> ".join([f"s{sw}" for sw in path]), total_cost,
        )

        # Install flow rules along path with idle_timeout=30s
        for i in range(len(path)):
            curr_sw = path[i]
            dp = self.datapaths.get(curr_sw)
            if not dp:
                continue

            if i == len(path) - 1:
                egress_port = dst_info["port"]
            else:
                next_sw = path[i + 1]
                egress_port = self.adjacency[curr_sw][next_sw]

            # Construct specific flow match: match on IP endpoints and L4 ports if available
            if pkt_udp and pkt_ip:
                match_fwd = dp.ofproto_parser.OFPMatch(
                    eth_type=0x0800, ip_proto=17, ipv4_src=pkt_ip.src, ipv4_dst=pkt_ip.dst, udp_src=pkt_udp.src_port, udp_dst=pkt_udp.dst_port
                )
            elif pkt_tcp and pkt_ip:
                match_fwd = dp.ofproto_parser.OFPMatch(
                    eth_type=0x0800, ip_proto=6, ipv4_src=pkt_ip.src, ipv4_dst=pkt_ip.dst, tcp_src=pkt_tcp.src_port, tcp_dst=pkt_tcp.dst_port
                )
            elif pkt_ip:
                match_fwd = dp.ofproto_parser.OFPMatch(
                    eth_type=0x0800, ipv4_src=pkt_ip.src, ipv4_dst=pkt_ip.dst
                )
            else:
                match_fwd = dp.ofproto_parser.OFPMatch(eth_dst=dst_mac)

            # Avoid same-priority overlapping rules: L4 rules (UDP/TCP) receive priority 20,
            # while coarse IP-only rules receive priority 10.
            flow_priority = 20 if (pkt_udp or pkt_tcp) else 10

            actions = [dp.ofproto_parser.OFPActionOutput(egress_port)]
            self.add_flow(dp, priority=flow_priority, match=match_fwd, actions=actions, idle_timeout=30)

        # Reverse path installation for bidirectional transport
        rev_path = list(reversed(path))
        for i in range(len(rev_path)):
            curr_sw = rev_path[i]
            dp = self.datapaths.get(curr_sw)
            if not dp:
                continue

            if i == len(rev_path) - 1:
                egress_port = src_info["port"]
            else:
                next_sw = rev_path[i + 1]
                egress_port = self.adjacency[curr_sw][next_sw]

            if pkt_udp and pkt_ip:
                match_rev = dp.ofproto_parser.OFPMatch(
                    eth_type=0x0800, ip_proto=17, ipv4_src=pkt_ip.dst, ipv4_dst=pkt_ip.src, udp_src=pkt_udp.dst_port, udp_dst=pkt_udp.src_port
                )
            elif pkt_tcp and pkt_ip:
                match_rev = dp.ofproto_parser.OFPMatch(
                    eth_type=0x0800, ip_proto=6, ipv4_src=pkt_ip.dst, ipv4_dst=pkt_ip.src, tcp_src=pkt_tcp.dst_port, tcp_dst=pkt_tcp.src_port
                )
            elif pkt_ip:
                match_rev = dp.ofproto_parser.OFPMatch(
                    eth_type=0x0800, ipv4_src=pkt_ip.dst, ipv4_dst=pkt_ip.src
                )
            else:
                match_rev = dp.ofproto_parser.OFPMatch(eth_dst=src_mac)

            flow_priority = 20 if (pkt_udp or pkt_tcp) else 10
            actions = [dp.ofproto_parser.OFPActionOutput(egress_port)]
            self.add_flow(dp, priority=flow_priority, match=match_rev, actions=actions, idle_timeout=30)

        # Forward the triggering packet
        first_dp = self.datapaths[path[0]]
        first_egress = self.adjacency[path[0]][path[1]]
        actions = [first_dp.ofproto_parser.OFPActionOutput(first_egress)]
        out = first_dp.ofproto_parser.OFPPacketOut(
            datapath=first_dp,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None,
        )
        first_dp.send_msg(out)
