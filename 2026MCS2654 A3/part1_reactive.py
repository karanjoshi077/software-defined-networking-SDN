#!/usr/bin/env python3
"""
COL7524: Advanced Networks - Assignment 3
Name: Karan Joshi (Entry No: 2026MCS2654)

Part 1: Reactive Flow Management Controller
Uses OpenFlow 1.3 on Ryu SDN Framework.
Forwarding rules are installed dynamically on-demand when traffic arrives at a switch.
"""

try:
    from ryu.base import app_manager
    from ryu.controller import ofp_event
    from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from ryu.ofproto import ofproto_v1_3
    from ryu.lib.packet import packet, ethernet, ether_types
except ImportError:
    # Graceful fallback stubs when ryu is not installed in the local python environment
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


class Part1ReactiveController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Part1ReactiveController, self).__init__(*args, **kwargs)
        # mac_to_port table: dpid -> {mac: port}
        self.mac_to_port = {}
        # Metrics tracking: maintain both total (including IPv6/LLDP) and user-traffic counts
        self.total_packet_ins = 0
        self.user_packet_ins = 0
        self.packet_in_count = 0  # Tracks user-traffic Packet-Ins
        self.flow_install_count = 0
        self.logger.info("Part 1 Reactive Flow Management Controller initialized.")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """
        Installs the table-miss flow entry on switch connection.
        Sends unmatched packets to the controller (Packet-In).
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.mac_to_port.setdefault(dpid, {})

        # Table-miss rule: Priority 0, match all, send to controller
        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)
        ]
        self.add_flow(datapath, priority=0, match=match, actions=actions)
        self.logger.info("Switch s%d connected. Installed table-miss entry.", dpid)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=60, hard_timeout=0):
        """Helper method to install a flow rule on an OpenFlow 1.3 datapath."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout,
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
                idle_timeout=idle_timeout,
                hard_timeout=hard_timeout,
            )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Reactive packet-in handler.
        Learns source MAC on the arrival port and installs forwarding rules once destination is known.
        Tracks both total datapath Packet-Ins and post-filter user traffic Packet-Ins.
        """
        self.total_packet_ins += 1
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # Ignore LLDP and IPv6 multicast discovery frames (NDP / router advertisements)
        # Mininet/Linux kernel hosts automatically generate IPv6 traffic that traps to controller.
        if eth.ethertype == ether_types.ETH_TYPE_LLDP or eth.ethertype == ether_types.ETH_TYPE_IPV6:
            return

        # Increment user-traffic Packet-In count strictly after filtering out control/NDP frames
        self.user_packet_ins += 1
        self.packet_in_count = self.user_packet_ins

        dst = eth.dst
        src = eth.src
        # One log line per user Packet-In so run_experiments.py can count them from the Ryu log
        self.logger.info("[USER PACKET-IN] s%d in_port=%s src=%s dst=%s ethertype=0x%04x",
                         dpid, in_port, src, dst, eth.ethertype)

        # Learn the incoming port for the source MAC
        self.mac_to_port[dpid][src] = in_port

        # Determine output port based on known MAC locations
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
            actions = [parser.OFPActionOutput(out_port)]

            # Install a flow rule reactively
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
            # Check if switch buffered the packet
            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, priority=1, match=match, actions=actions, buffer_id=msg.buffer_id)
                self.flow_install_count += 1
                self.logger.info(
                    "[REACTIVE FLOW INSTALLED] s%d: in_port=%s eth_dst=%s -> out_port=%s (Total Packet-Ins=%d)",
                    dpid, in_port, dst, out_port, self.packet_in_count,
                )
                return
            else:
                self.add_flow(datapath, priority=1, match=match, actions=actions)
                self.flow_install_count += 1
                self.logger.info(
                    "[REACTIVE FLOW INSTALLED] s%d: in_port=%s eth_dst=%s -> out_port=%s (Total Packet-Ins=%d)",
                    dpid, in_port, dst, out_port, self.packet_in_count,
                )
        else:
            # Destination unknown, flood to find host
            out_port = ofproto.OFPP_FLOOD
            actions = [parser.OFPActionOutput(out_port)]
            self.logger.debug(
                "[FLOOD] s%d: unknown dst=%s, flooding packet from src=%s on in_port=%s",
                dpid, dst, src, in_port,
            )

        # Send Packet-Out for the currently handled packet
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data,
        )
        datapath.send_msg(out)
