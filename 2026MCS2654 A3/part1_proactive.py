#!/usr/bin/env python3
"""
COL7524: Advanced Networks - Assignment 3
Name: Karan Joshi (Entry No: 2026MCS2654)

Part 1: Proactive Flow Management Controller
Uses OpenFlow 1.3 on Ryu SDN Framework.
Forwarding rules for all hosts and broadcast handling are installed proactively
at switch handshake time before traffic begins, eliminating Packet-In latency.
"""

try:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet, ether_types
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


class Part1ProactiveController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Part1ProactiveController, self).__init__(*args, **kwargs)
        # Metrics tracking: maintain both total (including IPv6/LLDP) and user-traffic counts
        self.total_packet_ins = 0
        self.user_packet_ins = 0
        self.packet_in_count = 0  # Tracks user-traffic Packet-Ins (0 in ideal proactive)
        self.flow_install_count = 0

        # Host MAC addresses and their locations in p1_topo
        # s1: port 1->h1, port 2->h2, port 3->h3, port 4->s2
        # s2: port 1->h4, port 2->h5, port 3->s1
        self.host_macs = {
            "h1": "00:00:00:00:00:01",
            "h2": "00:00:00:00:00:02",
            "h3": "00:00:00:00:00:03",
            "h4": "00:00:00:00:00:04",
            "h5": "00:00:00:00:00:05",
        }

        # Proactive unicast forwarding table: dpid -> {dst_mac: out_port}
        self.forwarding_table = {
            1: {
                self.host_macs["h1"]: 1,
                self.host_macs["h2"]: 2,
                self.host_macs["h3"]: 3,
                self.host_macs["h4"]: 4,
                self.host_macs["h5"]: 4,
            },
            2: {
                self.host_macs["h1"]: 3,
                self.host_macs["h2"]: 3,
                self.host_macs["h3"]: 3,
                self.host_macs["h4"]: 1,
                self.host_macs["h5"]: 2,
            },
        }

        # Switch active ports for broadcast flooding without loops
        self.switch_ports = {
            1: [1, 2, 3, 4],
            2: [1, 2, 3],
        }

        self.logger.info("Part 1 Proactive Flow Management Controller initialized.")

    def add_flow(self, datapath, priority, match, actions, idle_timeout=0, hard_timeout=0):
        """Helper method to install a permanent or timed flow entry."""
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
        self.flow_install_count += 1

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Installs all proactive forwarding rules as soon as switch connects.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.logger.info("Switch s%d connected. Beginning proactive rule installation...", dpid)

        # 1. Proactively install unicast forwarding rules for all known hosts (Priority 10)
        if dpid in self.forwarding_table:
            for dst_mac, out_port in self.forwarding_table[dpid].items():
                match = parser.OFPMatch(eth_dst=dst_mac)
                actions = [parser.OFPActionOutput(out_port)]
                self.add_flow(datapath, priority=10, match=match, actions=actions)
                self.logger.info(
                    "[PROACTIVE UNICAST RULE] s%d: eth_dst=%s -> out_port=%d",
                    dpid, dst_mac, out_port,
                )

        # 2. Proactively install broadcast (ARP) forwarding rules per in_port to avoid loops (Priority 5)
        # Prevents flooding back out of the receiving port.
        ports = self.switch_ports.get(dpid, [])
        for in_p in ports:
            out_ports = [p for p in ports if p != in_p]
            actions = [parser.OFPActionOutput(p) for p in out_ports]
            match = parser.OFPMatch(in_port=in_p, eth_dst="ff:ff:ff:ff:ff:ff")
            self.add_flow(datapath, priority=5, match=match, actions=actions)
            self.logger.info(
                "[PROACTIVE BCAST RULE] s%d: in_port=%d eth_dst=bcast -> out_ports=%s",
                dpid, in_p, out_ports,
            )

        # 3. Default fallback table-miss entry (Priority 0)
        # In pure proactive mode, this should ideally never be triggered by known hosts.
        match_miss = parser.OFPMatch()
        actions_miss = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, priority=0, match=match_miss, actions=actions_miss)
        self.logger.info("Switch s%d: All proactive rules successfully installed.", dpid)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Fallback packet-in handler for unexpected packets.
        Under proactive operation, user-traffic Packet-Ins should strictly remain 0.
        Tracks total datapath hits while filtering out background IPv6/LLDP frames.
        """
        self.total_packet_ins += 1
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore LLDP and IPv6 multicast discovery frames (NDP / router advertisements)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP or eth.ethertype == ether_types.ETH_TYPE_IPV6:
            return

        self.user_packet_ins += 1
        self.packet_in_count = self.user_packet_ins

        self.logger.warning(
            "[USER PACKET-IN] [UNEXPECTED] Switch s%d received packet from %s to %s on port %d (User Packet-Ins=%d, Total=%d)",
            dpid, eth.src, eth.dst, in_port, self.user_packet_ins, self.total_packet_ins,
        )
