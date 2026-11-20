#!/usr/bin/env python3
"""
COL7524: Advanced Networks - Assignment 3
Name: Karan Joshi (Entry No: 2026MCS2654)

Part 2: Link-Metric-Based Path Selection Controller
Uses OpenFlow 1.3 on Ryu SDN Framework.
Computes shortest paths using Dijkstra's algorithm based on the primary selected metric:
Delay Metric (Cost = link delay in ms; lower delay = lower cost).
Also provides optional inverse bandwidth metric (Cost = 100/bw).
"""

import os
import heapq
try:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet, ether_types, arp, ipv4
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

    def set_ev_cls(*args, **kwargs):
        def decorator(f):
            return f
        return decorator

    class ofp_event:
        class EventOFPSwitchFeatures: pass
        class EventOFPPacketIn: pass
    CONFIG_DISPATCHER = "config"
    MAIN_DISPATCHER = "main"
    ethernet = None
    packet = None
    ether_types = None
    arp = None
    ipv4 = None


class Part2MetricController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Part2MetricController, self).__init__(*args, **kwargs)

        # Datapath handles: dpid -> datapath object
        self.datapaths = {}

        # Metric mode: "delay" (lower delay = lower cost) or "bw" (higher bw = lower cost)
        # Defaults to delay, can be overridden via environment variable SDN_METRIC
        self.metric = os.environ.get("SDN_METRIC", "delay").lower()

        # Switch nodes in the ring topology
        self.nodes = [1, 2, 3, 4]

        # Topology port interconnects: adjacency[u][v] = egress_port_on_u_towards_v
        # In p3_topo:
        # s1: port 1->h1, port 2->s2, port 3->s4
        # s2: port 1->h2, port 2->s1, port 3->s3
        # s3: port 1->h3, port 2->s2, port 3->s4
        # s4: port 1->h4, port 2->s3, port 3->s1
        self.adjacency = {
            1: {2: 2, 4: 3},
            2: {1: 2, 3: 3},
            3: {2: 2, 4: 3},
            4: {3: 2, 1: 3},
        }

        # Load link properties from JSON file specified in LINK_CONFIG env var (default: p3_baseline.json)
        config_path = os.environ.get("LINK_CONFIG", "p3_baseline.json")
        self.link_properties = self._load_link_config(config_path)

        # Host attachments: MAC -> (switch_dpid, host_port, IP)
        # Seeded with standard network mapping; dynamically updated when hosts transmit packets
        self.host_db = {
            "00:00:00:00:00:01": {"dpid": 1, "port": 1, "ip": "10.0.0.1"},
            "00:00:00:00:00:02": {"dpid": 2, "port": 1, "ip": "10.0.0.2"},
            "00:00:00:00:00:03": {"dpid": 3, "port": 1, "ip": "10.0.0.3"},
            "00:00:00:00:00:04": {"dpid": 4, "port": 1, "ip": "10.0.0.4"},
        }
        self.ip_to_mac = {info["ip"]: mac for mac, info in self.host_db.items()}

        self.logger.info("Part 2 Metric Controller initialized with metric: %s", self.metric.upper())

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
                self.logger.info("Loaded link properties from config file: %s", config_path)
            except Exception as e:
                self.logger.warning("Could not parse config %s: %s. Using defaults.", config_path, e)
        else:
            self.logger.info("LINK_CONFIG not found (%s); using default baseline properties.", config_path)
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

    def get_link_cost(self, u, v):
        """
        Calculates link cost based on selected metric:
        - delay (Primary selected metric): Cost = delay (ms) -> lower delay yields lower cost.
        - bw (Optional secondary metric): Cost = 100 / bandwidth (Mbps) -> higher bandwidth yields lower cost.
        """
        props = self.link_properties.get((u, v), {"bw": 1.0, "delay": 50.0})
        if self.metric == "delay":
            return props["delay"]
        else:
            # Bandwidth metric: cost inversely proportional to bandwidth
            return 100.0 / props["bw"]

    def dijkstra(self, src, dst):
        """Computes shortest path from src dpid to dst dpid using Dijkstra's algorithm."""
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
                cost = self.get_link_cost(u, v)
                if dist[u] + cost < dist[v]:
                    dist[v] = dist[u] + cost
                    prev[v] = u
                    heapq.heappush(pq, (dist[v], v))

        # Reconstruct path
        path = []
        curr = dst
        while curr is not None:
            path.append(curr)
            curr = prev[curr]
        path.reverse()

        if path and path[0] == src:
            return path, dist[dst]
        return None, float("inf")

    def add_flow(self, datapath, priority, match, actions, idle_timeout=120, hard_timeout=0):
        """Installs an OpenFlow rule on the switch."""
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
        """Registers connected switches and installs table-miss flow entries."""
        datapath = ev.msg.datapath
        dpid = datapath.id
        self.datapaths[dpid] = datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Table-miss entry (priority 0)
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, priority=0, match=match, actions=actions, idle_timeout=0)
        self.logger.info("Switch s%d connected and registered.", dpid)

    def handle_arp(self, datapath, in_port, pkt_ethernet, pkt_arp):
        """
        Directly answers ARP requests using the known host database.
        Learns querying host attachment point dynamically, provides instant
        address resolution, and prevents broadcast storms in the ring topology.
        """
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        # Dynamically record querying host attachment
        self._learn_host(datapath.id, in_port, pkt_ethernet.src, pkt_arp.src_ip)

        if pkt_arp.opcode != arp.ARP_REQUEST:
            return

        target_ip = pkt_arp.dst_ip
        if target_ip in self.ip_to_mac:
            target_mac = self.ip_to_mac[target_ip]
            # Form ARP Reply
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
            self.logger.debug(
                "[ARP RESOLVED] s%d answered ARP for %s -> %s to host on port %d",
                datapath.id, target_ip, target_mac, in_port,
            )

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Processes incoming packets, runs Dijkstra, and installs end-to-end paths."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        in_port = msg.match["in_port"]
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore discovery packets
        if eth.ethertype == ether_types.ETH_TYPE_LLDP or eth.ethertype == ether_types.ETH_TYPE_IPV6:
            return

        # Intercept and handle ARP requests
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

        # If destination is unknown or multicast, do not install flow
        if dst_mac not in self.host_db or src_mac not in self.host_db:
            return

        src_info = self.host_db[src_mac]
        dst_info = self.host_db[dst_mac]
        src_sw = src_info["dpid"]
        dst_sw = dst_info["dpid"]

        # Case 1: Intra-switch communication
        if src_sw == dst_sw:
            match = parser.OFPMatch(eth_dst=dst_mac)
            actions = [parser.OFPActionOutput(dst_info["port"])]
            self.add_flow(datapath, priority=10, match=match, actions=actions)
            # Send current packet
            out = parser.OFPPacketOut(
                datapath=datapath, buffer_id=msg.buffer_id, in_port=in_port,
                actions=actions, data=msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None,
            )
            datapath.send_msg(out)
            return

        # Case 2: Inter-switch communication -> Compute optimal path via Dijkstra
        path, total_cost = self.dijkstra(src_sw, dst_sw)
        if not path:
            self.logger.error("No path found between s%d and s%d!", src_sw, dst_sw)
            return

        self.logger.info(
            "[PATH COMPUTED] Metric: %s | %s (s%d) -> %s (s%d) | Selected Path: %s | Total Path Cost: %.2f",
            self.metric.upper(), src_info["ip"], src_sw, dst_info["ip"], dst_sw,
            " -> ".join([f"s{sw}" for sw in path]), total_cost,
        )

        # Install flow rules forward and reverse along the computed path
        # Forward path
        for i in range(len(path)):
            curr_sw = path[i]
            dp = self.datapaths.get(curr_sw)
            if not dp:
                continue

            # Determine egress port
            if i == len(path) - 1:
                # Last hop: egress directly to destination host
                egress_port = dst_info["port"]
            else:
                next_sw = path[i + 1]
                egress_port = self.adjacency[curr_sw][next_sw]

            match = dp.ofproto_parser.OFPMatch(eth_dst=dst_mac)
            actions = [dp.ofproto_parser.OFPActionOutput(egress_port)]
            self.add_flow(dp, priority=10, match=match, actions=actions)
            self.logger.info(
                "  [FORWARD RULE] s%d: eth_dst=%s -> out_port=%d", curr_sw, dst_mac, egress_port
            )

        # Reverse path (bidirectional connectivity)
        rev_path = list(reversed(path))
        for i in range(len(rev_path)):
            curr_sw = rev_path[i]
            dp = self.datapaths.get(curr_sw)
            if not dp:
                continue

            if i == len(rev_path) - 1:
                # Egress to source host
                egress_port = src_info["port"]
            else:
                next_sw = rev_path[i + 1]
                egress_port = self.adjacency[curr_sw][next_sw]

            match = dp.ofproto_parser.OFPMatch(eth_dst=src_mac)
            actions = [dp.ofproto_parser.OFPActionOutput(egress_port)]
            self.add_flow(dp, priority=10, match=match, actions=actions)
            self.logger.info(
                "  [REVERSE RULE] s%d: eth_dst=%s -> out_port=%d", curr_sw, src_mac, egress_port
            )

        # Forward the packet that triggered this Packet-In
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
