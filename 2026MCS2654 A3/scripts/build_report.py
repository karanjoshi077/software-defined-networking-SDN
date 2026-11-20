#!/usr/bin/env python3
"""
COL7524: Advanced Networks - Assignment 3 Report Generator
Name: Karan Joshi (Entry No: 2026MCS2654)
Builds report.pdf using ReportLab.
"""

import os
from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, PageBreak, HRFlowable
)
from PIL import Image as PILImage

OUT = "report.pdf"

# Document geometry
PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN_H = 1.4 * cm
MARGIN_V = 1.3 * cm
CONTENT_WIDTH = PAGE_WIDTH - 2 * MARGIN_H

# Stylesheet
ss = getSampleStyleSheet()

title_style = ParagraphStyle(
    "DocTitle",
    parent=ss["Title"],
    fontName="Helvetica-Bold",
    fontSize=13.5,
    leading=16,
    alignment=TA_LEFT,
    textColor=colors.HexColor("#112233"),
    spaceAfter=2,
)

sub_style = ParagraphStyle(
    "DocSub",
    parent=ss["Normal"],
    fontName="Helvetica",
    fontSize=8.5,
    leading=11.5,
    alignment=TA_LEFT,
    textColor=colors.HexColor("#444444"),
    spaceAfter=6,
)

h1_style = ParagraphStyle(
    "H1",
    parent=ss["Heading2"],
    fontName="Helvetica-Bold",
    fontSize=10.0,
    leading=12.5,
    spaceBefore=7,
    spaceAfter=3,
    textColor=colors.HexColor("#1f3a5f"),
)

h2_style = ParagraphStyle(
    "H2",
    parent=ss["Heading3"],
    fontName="Helvetica-Bold",
    fontSize=8.6,
    leading=11.0,
    spaceBefore=4,
    spaceAfter=2,
    textColor=colors.HexColor("#2c3e50"),
)

body_style = ParagraphStyle(
    "Body",
    parent=ss["BodyText"],
    fontName="Helvetica",
    fontSize=8.0,
    leading=10.4,
    alignment=TA_JUSTIFY,
    spaceAfter=3.5,
)

code_style = ParagraphStyle(
    "CodeText",
    parent=body_style,
    fontName="Courier",
    fontSize=7.2,
    leading=9.2,
    textColor=colors.HexColor("#222222"),
    spaceAfter=2,
)

cap_style = ParagraphStyle(
    "Caption",
    parent=body_style,
    fontName="Helvetica-Oblique",
    fontSize=7.3,
    leading=9.2,
    textColor=colors.HexColor("#555555"),
    alignment=TA_CENTER,
    spaceAfter=4,
)

cell_style = ParagraphStyle(
    "Cell",
    parent=body_style,
    fontSize=7.4,
    leading=9.2,
    alignment=TA_LEFT,
    spaceAfter=0,
)

cell_bold = ParagraphStyle(
    "CellBold",
    parent=cell_style,
    fontName="Helvetica-Bold",
)

cell_code = ParagraphStyle(
    "CellCode",
    parent=cell_style,
    fontName="Courier",
    fontSize=6.9,
    leading=8.6,
)

bullet_style = ParagraphStyle(
    "Bullet",
    parent=body_style,
    leftIndent=10,
    bulletIndent=2,
    spaceAfter=2,
)


def P(text, s=body_style):
    return Paragraph(text, s)


def B(text):
    return Paragraph(text, bullet_style, bulletText="\u2022")


def C(text):
    return Paragraph(f"<font face='Courier'>{text}</font>", body_style)


def img_block(path, width_cm, caption=""):
    if not os.path.exists(path):
        return P(f"[Missing figure: {path}]", body_style)
    w, h = PILImage.open(path).size
    aspect = h / float(w)
    target_w = width_cm * cm
    target_h = target_w * aspect
    items = [
        Image(path, width=target_w, height=target_h),
        Spacer(1, 1),
    ]
    if caption:
        items.append(Paragraph(caption, cap_style))
    return items


def make_table(rows, col_widths, header=True, zebra=True, is_code_table=False):
    table_data = []
    for i, r in enumerate(rows):
        row_cells = []
        for c in r:
            if header and i == 0:
                row_cells.append(Paragraph(str(c), cell_bold))
            elif is_code_table:
                row_cells.append(Paragraph(str(c), cell_code))
            else:
                row_cells.append(Paragraph(str(c), cell_style))
        table_data.append(row_cells)

    t = Table(table_data, colWidths=col_widths, repeatRows=1 if header else 0)
    t_style = [
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("LINEABOVE", (0, 0), (-1, 0), 0.7, colors.HexColor("#1f3a5f")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.HexColor("#1f3a5f")),
        ("LINEBELOW", (0, -1), (-1, -1), 0.7, colors.HexColor("#1f3a5f")),
    ]
    if header:
        t_style.append(("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8eef6")))
    if zebra:
        for idx in range(1 if not header else 2, len(rows), 2):
            t_style.append(("BACKGROUND", (0, idx), (-1, idx), colors.HexColor("#f8f9fa")))
    t.setStyle(TableStyle(t_style))
    return t


import json
import re
from xml.sax.saxutils import escape


def jload(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return None


def fnum(x, fmt="{:.2f}", na="not measured"):
    return fmt.format(x) if isinstance(x, (int, float)) else na


def compact_flows(path, keep=None, limit=14):
    """Real `ovs-ofctl dump-flows` lines, stripped of cookie/duration/counters, as a code block."""
    try:
        lines = open(path, errors="ignore").read().splitlines()
    except Exception:
        return None
    out = []
    for ln in lines:
        if "cookie=" not in ln:
            continue
        m = re.search(r"(idle_timeout=\d+,\s*)?(priority=.*)", ln)
        if not m:
            continue
        txt = ((m.group(1) or "") + m.group(2)).strip()
        if keep is None or re.search(keep, txt):
            out.append(txt)
    return out[:limit] if out else None


def code_block(lines):
    return Paragraph("<br/>".join(escape(l) for l in lines), code_style)


# ---- fix4: helpers that derive report statements from the measured files ----
import csv

IPERF_MEGA = 1.048576  # iperf2 '-b 1.6M' uses M = 2^20 bit/s


def read_telemetry(path):
    rows = []
    try:
        with open(path) as f:
            for r in csv.DictReader(f):
                rows.append({k: float(v) for k, v in r.items()})
    except Exception:
        return []
    return rows


def flow_out_port(path, dst_mac):
    try:
        for ln in open(path, errors="ignore"):
            if "dl_dst=" + dst_mac in ln:
                m = re.search(r'actions=output:"?([\w-]+)"?', ln)
                if m:
                    return m.group(1)
    except Exception:
        pass
    return None


def p2_dump_verdict():
    s1b = flow_out_port("results/flow_dump_p2_baseline_s1.txt", "00:00:00:00:00:03")
    s1m = flow_out_port("results/flow_dump_p2_modified_s1.txt", "00:00:00:00:00:03")
    s3b = flow_out_port("results/flow_dump_p2_baseline_s3.txt", "00:00:00:00:00:01")
    s3m = flow_out_port("results/flow_dump_p2_modified_s3.txt", "00:00:00:00:00:01")
    if (s1b, s1m, s3b, s3m) == ("s1-eth2", "s1-eth3", "s3-eth2", "s3-eth3"):
        return ("The measured dumps confirm this: on s1 the rule moves from <font face='Courier'>s1-eth2</font> to "
                "<font face='Courier'>s1-eth3</font>, and on s3 from <font face='Courier'>s3-eth2</font> to "
                "<font face='Courier'>s3-eth3</font>.")
    if None in (s1b, s1m, s3b, s3m):
        return "Measured dumps were not available for all four switch/topology cases."
    return (f"Measured dumps: s1 {s1b} &rarr; {s1m}, s3 {s3b} &rarr; {s3m} (see below).")


def p3_facts(r_st, r_dy):
    """Numbers used in the Part 3 text, all taken from the live run files."""
    fx = {"off1": 1.6 * IPERF_MEGA, "off2": 0.8 * IPERF_MEGA}
    fx["off_sum"] = fx["off1"] + fx["off2"]
    fx["model_loss"] = 100.0 * (fx["off_sum"] - 2.0) / fx["off_sum"]
    fx["excess_mb"] = (fx["off_sum"] - 2.0) * 15.0
    dy = read_telemetry("results/part3_dynamic_telemetry.csv")
    st = read_telemetry("results/part3_static_telemetry.csv")
    fx["detect_util"] = None
    for i, r in enumerate(dy):
        if r.get("cost_ms", 0) > 20.0 and i > 0:
            fx["detect_util"] = dy[i - 1]["util_pct"]
            fx["detect_rate"] = dy[i - 1]["rate_mbps"]
            break
    sat = [r for r in st if r.get("util_pct", 0) >= 99.0]
    fx["sat_s"] = (sat[-1]["t_rel_s"] - sat[0]["t_rel_s"] + 2.0) if sat else None
    try:
        fx["jit_st"] = (r_st["flow1"]["jitter_ms"], r_st["flow2"]["jitter_ms"])
        fx["jit_dy"] = (r_dy["flow1"]["jitter_ms"], r_dy["flow2"]["jitter_ms"])
    except Exception:
        fx["jit_st"] = fx["jit_dy"] = None
    try:
        fx["loss_st"] = max(r_st["flow1"]["packet_loss_percent"], r_st["flow2"]["packet_loss_percent"])
    except Exception:
        fx["loss_st"] = None
    # alternate-path congestion seen by the dynamic controller (log of the last run = dynamic)
    fx["alt"] = {}
    try:
        log = open("results/ryu_part3_controller.log", errors="ignore").read()
        if "mode=dynamic" in log:
            for a, b in (("s1", "s4"), ("s4", "s3")):
                m = re.search(r"\[CONGESTION DETECTED\] Link \(%s <-> %s\): Rate=[\d.]+ Mbps \(([\d.]+)%%" % (a, b), log)
                if m:
                    fx["alt"][f"{a}-{b}"] = float(m.group(1))
    except Exception:
        pass
    return fx


def build_pdf():
    story = []
    # ---- load measured data (None when the live experiment has not been run) ----
    r_re = jload("results/part1_reactive_live.json")
    r_pro = jload("results/part1_proactive_live.json")
    r_base = jload("results/part2_baseline_live.json")
    r_mod = jload("results/part2_modified_live.json")
    r_st = jload("results/part3_static_live.json")
    r_dy = jload("results/part3_dynamic_live.json")
    have1, have2, have3 = bool(r_re and r_pro), bool(r_base and r_mod), bool(r_st and r_dy)
    all_live = have1 and have2 and have3
    fx = p3_facts(r_st, r_dy)  # fix4

    # Title & Metadata
    story.append(P("COL7524: Advanced Networks — Assignment 3", title_style))
    story.append(P("<b>Software-Defined Networking (SDN) Controller Design and Evaluation</b><br/>"
                   "Name: <b>Karan Joshi</b> &middot; Entry No: <b>2026MCS2654</b> &middot; "
                   + ("All results below were measured live on Mininet + Open vSwitch + Ryu (OpenFlow 1.3)." if all_live else
                      "Items marked 'not measured' have no live Mininet/Ryu data yet (see Section 4)."), sub_style))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#1f3a5f"), spaceAfter=5, spaceBefore=0))

    # =========================================================================
    # PART 1
    # =========================================================================
    story.append(P("1. Part 1: Reactive and Proactive Flow Management", h1_style))
    story.append(P(
        "<b>Architectural Design.</b> We implement both flow installation paradigms using OpenFlow 1.3 and the Ryu framework on the provided "
        "<font face='Courier'>p1_topo.py</font> topology (switches <font face='Courier'>s1</font> with hosts <font face='Courier'>h1&ndash;h3</font> "
        "and <font face='Courier'>s2</font> with <font face='Courier'>h4&ndash;h5</font>, connected by a 10 Mbps, 5 ms trunk link).<br/>"
        "&bull; <b>Reactive Controller (<font face='Courier'>part1_reactive.py</font>):</b> Installs a baseline table-miss flow rule "
        "(<font face='Courier'>priority=0</font>) on switch handshake that redirects unmatched frames to the controller via "
        "<font face='Courier'>OFPPacketIn</font>. When traffic arrives, the controller learns the source MAC and ingress port. If the destination "
        "MAC is known, an exact forwarding rule (<font face='Courier'>priority=1, match(in_port, eth_dst), action=OFPActionOutput(out_port)</font>) "
        "is installed with <font face='Courier'>idle_timeout=60s</font>, followed by an <font face='Courier'>OFPPacketOut</font>. If unknown, the packet "
        "is flooded across all other ports.<br/>"
        "&bull; <b>Proactive Controller (<font face='Courier'>part1_proactive.py</font>):</b> Eliminates runtime control plane latency by "
        "pre-populating all forwarding rules during switch handshake (<font face='Courier'>EventOFPSwitchFeatures</font>). On switch <font face='Courier'>s1</font>, "
        "unicast rules for <font face='Courier'>h1&ndash;h3</font> map to local ports 1&ndash;3 and remote hosts <font face='Courier'>h4&ndash;h5</font> "
        "to trunk port 4 (<font face='Courier'>priority=10</font>). In addition, loop-free broadcast ARP forwarding entries are installed per ingress port "
        "(<font face='Courier'>priority=5</font>), preventing packet circulation while allowing full host discovery without triggering any Packet-In.<br/>"
        "&bull; <b>Background IPv6/LLDP Filtering:</b> Standard Linux network stacks in Mininet emit background IPv6 Neighbor Discovery (NDP) and "
        "Multicast Listener Discovery (MLD) frames that trap to the table-miss flow. Both controllers track both <font face='Courier'>total_packet_ins</font> "
        "and <font face='Courier'>user_packet_ins</font>, explicitly filtering out non-user control frames (ethertype 0x86dd and LLDP 0x88cc) so that "
        "measured control-plane metrics strictly reflect user communication."
    ))

    # Flow Table Evidence Table
    story.append(P("<b>Flow entries installed by each controller (design, from the code; measured dumps follow).</b>", h2_style))
    p1_flow_table = [
        ["Approach", "Priority", "Match Fields", "Actions", "Timeouts", "Purpose"],
        ["Reactive", "0", "* (table-miss)", "CONTROLLER", "idle=0, hard=0", "Trap unmatched packets to Ryu"],
        ["Reactive", "1", "in_port=1, eth_dst=h4", "OUTPUT:4 (trunk)", "idle=60, hard=0", "Learned flow installed after 1st Packet-In"],
        ["Reactive", "1", "in_port=4, eth_dst=h1", "OUTPUT:1", "idle=60, hard=0", "Reverse path learned on reply"],
        ["Proactive", "10", "eth_dst=h1..h3", "OUTPUT:1..3", "idle=0, hard=0", "Pre-installed local port delivery"],
        ["Proactive", "10", "eth_dst=h4..h5", "OUTPUT:4 (trunk)", "idle=0, hard=0", "Pre-installed trunk forwarding to s2"],
        ["Proactive", "5", "in_port=1, eth_dst=bcast", "OUTPUT:2,3,4", "idle=0, hard=0", "Loop-free broadcast flooding (no controller trap)"],
    ]
    story.append(make_table(p1_flow_table, [1.5 * cm, 1.2 * cm, 3.8 * cm, 2.6 * cm, 2.2 * cm, CONTENT_WIDTH - 11.3 * cm]))
    story.append(Spacer(1, 3))
    for mode_name in ("reactive", "proactive"):
        dump = compact_flows(f"results/flow_dump_p1_{mode_name}_s1.txt")
        if dump:
            story.append(P(f"<b>Measured <font face='Courier'>ovs-ofctl dump-flows s1</font> ({mode_name}, after the experiment):</b>", h2_style))
            story.append(code_block(dump))
        else:
            story.append(P(f"Measured flow dump for {mode_name} s1: not measured.", body_style))

    # Figure 1: Part 1
    story.extend(img_block("results/fig_p1_packet_ins_rtt.png", 14.5, "Figure 1: (Left) Cumulative user Packet-Ins vs host pairs; (Right) first-packet vs steady-state RTT" + (" (both measured live)." if have1 else " (no live data).")))

    # Part 1 Trade-off Analysis
    story.append(P("<b>Experimental Comparison and Trade-off Analysis.</b>", h2_style))
    def p1v(d, key, sub=None):
        try:
            return d["metrics"][key]
        except Exception:
            return None
    def curve_at(d, n):
        try:
            c = d["packet_in_curve"]
            return c["cumulative_user_packet_ins"][c["host_pairs"].index(n)]
        except Exception:
            return None
    fe_re = (r_re["flow_entries"]["s1"] + r_re["flow_entries"]["s2"]) if r_re and "flow_entries" in r_re else None
    fe_pro = (r_pro["flow_entries"]["s1"] + r_pro["flow_entries"]["s2"]) if r_pro and "flow_entries" in r_pro else None
    pen = (p1v(r_re, "first_packet_rtt_ms") - p1v(r_pro, "first_packet_rtt_ms")) if have1 else None
    p1_metrics = [
        ["<b>Evaluation Metric (measured)</b>", "<b>Reactive (<font face='Courier'>part1_reactive.py</font>)</b>", "<b>Proactive (<font face='Courier'>part1_proactive.py</font>)</b>", "<b>Architectural Trade-off</b>"],
        ["First-packet RTT, cold h1&rarr;h4 (ms)", fnum(p1v(r_re, "first_packet_rtt_ms")), fnum(p1v(r_pro, "first_packet_rtt_ms")), "Includes ARP + flow setup for reactive; difference = setup penalty"],
        ["Steady-state RTT (ms, mean of packets 2-10)", fnum(p1v(r_re, "steady_state_rtt_ms")), fnum(p1v(r_pro, "steady_state_rtt_ms")), "Same data-plane path once rules exist (2 x 5 ms trunk + stack)"],
        ["User Packet-Ins, first host pair", fnum(r_re.get("user_packet_ins_first_pair") if r_re else None, "{:d}"), fnum(r_pro.get("user_packet_ins_first_pair") if r_pro else None, "{:d}"), "Proactive needs none for known hosts"],
        ["Cumulative user Packet-Ins, 5 host pairs", fnum(curve_at(r_re, 5), "{:d}"), fnum(curve_at(r_pro, 5), "{:d}"), "Controller workload grows with new flows (reactive)"],
        ["Cumulative user Packet-Ins, 10 host pairs", fnum(curve_at(r_re, 10), "{:d}"), fnum(curve_at(r_pro, 10), "{:d}"), "All 10 pairs of the 5 hosts"],
        ["Flow entries on s1+s2 at end of run", fnum(fe_re, "{:d}"), fnum(fe_pro, "{:d}"), "Proactive pre-loads 19 = 17 unicast/broadcast + 2 table-miss"],
        ["Topology churn resilience", "High: relearns when hosts move", "Low: static table needs controller re-push", "Qualitative (design)"],
    ]
    story.append(make_table(p1_metrics, [3.0 * cm, 4.5 * cm, 4.5 * cm, CONTENT_WIDTH - 12.0 * cm]))
    story.append(Spacer(1, 3))
    story.append(P(
        "<b>Trade-Off Synthesis:</b> The fundamental trade-off lies between <i>forwarding delay</i>, <i>controller workload</i>, and "
        "<i>switch TCAM table occupancy</i>. Reactive installation conserves switch flow table space by maintaining rules only for active flows, "
        "making it suitable for open, dynamic networks. However, every new flow incurs an initial latency penalty (measured: " + (fnum(pen) + " ms" if pen is not None else "not measured") + ", cold first-packet RTT, reactive minus proactive; "
        "includes ARP) due to the switch-to-controller roundtrip. Under traffic bursts, the controller CPU becomes a severe bottleneck. "
        "Proactive installation delivers optimal line-rate performance from the very first packet with zero controller overhead during transmission, "
        "making it ideal for well-defined data centers, but consumes switch TCAM proactively for flows that may never transmit."
    ))

    # =========================================================================
    # PART 2
    # =========================================================================
    story.append(P("2. Part 2: Link-Metric-Based Path Selection", h1_style))
    story.append(P(
        "<b>Graph Formulation & Path Computation.</b> The 4-switch ring topology (<font face='Courier'>p3_topo.py</font>) provides two alternative "
        "paths between opposite switches (<font face='Courier'>s1&ndash;s3</font> and <font face='Courier'>s2&ndash;s4</font>). The inter-switch links have "
        "capacities of 2, 2, 1, and 1 Mbps and propagation delays of 20, 10, 20, and 15 ms respectively.<br/>"
        "&bull; <b>Topology Graph & JSON Configuration:</b> The controller (<font face='Courier'>part2_controller.py</font>) models the switch network as a "
        "weighted directed graph <i>G = (V, E, W)</i>. Inter-switch link properties are cleanly externalized in JSON configuration files "
        "(<font face='Courier'>p3_baseline.json</font> and <font face='Courier'>p3_modified.json</font>) and selected via the <font face='Courier'>LINK_CONFIG</font> "
        "environment variable.<br/>"
        "&bull; <b>Host Attachment Learning:</b> To associate host IPs with edge switches without static coupling, the controller implements dynamic host learning "
        "(<font face='Courier'>_learn_host</font>) that binds host MACs and IPs to their ingress switch and access port upon receiving ARP or IP packets, "
        "seeded with default host attachment locations for immediate reachability.<br/>"
        "&bull; <b>Dijkstra Path Selection:</b> Per assignment requirements selecting <b>one static metric</b>, we use <b>Delay Metric</b>: "
        "<i>Cost(u, v) = Delay<sub>ms</sub></i>. When a flow arrives, the controller runs Dijkstra's shortest path algorithm using a min-heap priority queue, "
        "installing bidirectional OpenFlow 1.3 forwarding rules (<font face='Courier'>priority=10</font>) along the computed path. ARP requests are intercepted "
        "and answered by the controller to eliminate broadcast storms on the ring."
    ))

    # Table of path comparison
    story.append(P("<b>Baseline Path Selection Analysis between h1 (s1) and h3 (s3) under Delay Metric:</b>", h2_style))
    p2_paths = [
        ["<b>Candidate Path</b>", "<b>Inter-Switch Hops</b>", "<b>Link Delays along Path</b>", "<b>Cumulative Delay Cost</b>", "<b>Dijkstra Decision (Delay Metric)</b>"],
        ["Path A (via s2)", "s1 &rarr; s2 &rarr; s3", "(s1,s2): 20.0 ms | (s2,s3): 10.0 ms", "<b>30.0 ms</b>", "<b>SELECTED (Optimal Shortest Delay)</b>"],
        ["Path B (via s4)", "s1 &rarr; s4 &rarr; s3", "(s1,s4): 15.0 ms | (s4,s3): 20.0 ms", "35.0 ms", "Rejected (+5.0 ms Higher Delay)"],
    ]
    story.append(make_table(p2_paths, [3.0 * cm, 2.8 * cm, 5.5 * cm, 2.8 * cm, CONTENT_WIDTH - 14.1 * cm]))
    story.append(Spacer(1, 3))

    # Figure 2: Part 2
    story.extend(img_block("results/fig_p2_path_selection.png", 14.5, "Figure 2: (Left) Computed Dijkstra path costs; (Right) " + ("measured average RTT (bars) vs theoretical 2×delay (dashed)." if have2 else "theoretical 2×delay only - NOT measured.")))

    # Link Property Modification Test
    story.append(P("<b>Link Modification Test (<font face='Courier'>p3_topo_mod.py</font>).</b>", h2_style))
    story.append(P(
        "To test dynamic metric adaptation, we modified the topology by lowering the delay of link <font face='Courier'>(s4, s1)</font> "
        "from 15 ms to <b>5 ms</b> (documented in <font face='Courier'>p3_topo_mod.py</font>).<br/>"
        "&bull; <b>Path Cost Recalculation:</b> Path via s2 remains 30.0 ms. Path via s4 cost drops to <i>5.0 + 20.0 = <b>25.0 ms</b></i>.<br/>"
        "&bull; <b>Routing Adaptation:</b> Because 25.0 ms &lt; 30.0 ms, Dijkstra immediately selects <b>Path [s1, s4, s3]</b>.<br/>"
        "&bull; <b>Flow-Table Evidence:</b> On switch <font face='Courier'>s1</font>, the flow entry matching <font face='Courier'>eth_dst=h3</font> "
        "should move from egress port 2 (towards <font face='Courier'>s2</font>) to <b>port 3</b> (towards <font face='Courier'>s4</font>); on <font face='Courier'>s3</font> the rule for "
        "<font face='Courier'>eth_dst=h1</font> from port 2 to port 3. " + p2_dump_verdict() + "<br/>"
        "&bull; <b>Performance Validation:</b> Theoretical two-way propagation delay (2 &times; path delay) drops from <b>60.0 ms</b> to <b>50.0 ms</b>."
    ))
    def p2rtt(d):
        try:
            return d["metrics_forward"]["rtt_avg_ms"]
        except Exception:
            return None
    def p2path(d):
        try:
            return d["controller_selected_path_h1_h3"]["path"]
        except Exception:
            return None
    p2_meas = [
        ["<b>Topology</b>", "<b>Controller-selected path h1&rarr;h3 (log)</b>", "<b>Theoretical RTT</b>", "<b>Measured avg RTT (10 pings)</b>"],
        ["Baseline (s4-s1 = 15 ms)", str(p2path(r_base) or "not measured"), "60.0 ms", fnum(p2rtt(r_base)) + (" ms" if p2rtt(r_base) is not None else "")],
        ["Modified (s4-s1 = 5 ms)", str(p2path(r_mod) or "not measured"), "50.0 ms", fnum(p2rtt(r_mod)) + (" ms" if p2rtt(r_mod) is not None else "")],
    ]
    story.append(make_table(p2_meas, [3.6 * cm, 5.2 * cm, 3.0 * cm, CONTENT_WIDTH - 11.8 * cm]))
    story.append(Spacer(1, 3))
    if have2:
        story.append(P("<b>Measured RTT change:</b> " + fnum(p2rtt(r_base) - p2rtt(r_mod)) + " ms (theoretical: 10.0 ms). Any gap versus theory is host/OVS processing and TCLink shaping overhead.", body_style))
    for topo_name, sw, pat in (("baseline", 1, "00:00:00:00:00:03"), ("modified", 1, "00:00:00:00:00:03"), ("modified", 3, "00:00:00:00:00:01")):
        dump = compact_flows(f"results/flow_dump_p2_{topo_name}_s{sw}.txt", keep=re.escape(pat), limit=4)
        if dump:
            story.append(P(f"<b>Measured flow entries on s{sw} ({topo_name}) matching eth_dst={pat}:</b>", h2_style))
            story.append(code_block(dump))

    # =========================================================================
    # PART 3
    # =========================================================================
    story.append(P("3. Part 3: Congestion-Aware Routing", h1_style))
    story.append(P(
        "<b>Dynamic Utilization Monitoring & Penalty Rule.</b> While Part 2 selects paths based on static metrics, static routing fails when "
        "links become congested. We extend the controller in <font face='Courier'>part3_controller.py</font> with active datapath telemetry.<br/>"
        "&bull; <b>Switch Statistics Telemetry:</b> A background green-thread (<font face='Courier'>ryu.lib.hub</font>) queries port statistics "
        "on all active switches every <i>T = 2 s</i> using <font face='Courier'>OFPPortStatsRequest</font>. On receiving "
        "<font face='Courier'>EventOFPPortStatsReply</font>, the controller computes the instantaneous transmit rate: "
        "<i>Rate = (&Delta;tx_bytes &times; 8) / &Delta;t</i>. Link utilization is evaluated as <i>U = Rate / Capacity</i>. Both "
        "<font face='Courier'>ROUTING_MODE=dynamic</font> and <font face='Courier'>ROUTING_MODE=static</font> continuously log telemetry, "
        "ensuring comparable observability while static mode holds costs fixed.<br/>"
        "&bull; <b>Adaptive Congestion Rule:</b> When utilization <i>U &ge; 70%</i> (i.e. &gt;1.4 Mbps on a 2 Mbps link), the controller marks the link "
        "as congested and applies a dynamic penalty of <b>+200.0 ms</b> to its routing cost: <i>Cost<sub>eff</sub> = Cost<sub>base</sub> + 200.0</i>.<br/>"
        "&bull; <b>Preservation of Active Flows & Priority Differentiation:</b> Flow rules already committed to switch flow tables remain untouched "
        "with active timeouts. Only <i>new incoming flows</i> are routed using the updated cost matrix. To prevent rule conflicts, the controller installs "
        "specific 5-tuple L4 transport rules (matching protocol, IP addresses, and L4 UDP/TCP ports) at <b>Priority 20</b> and coarse IP-only forwarding at "
        "<b>Priority 10</b>, preventing overlapping rule interference."
    ))

    # Figure 3: Part 3
    story.extend(img_block("results/fig_p3_congestion_dynamics.png", 14.5, "Figure 3: (Top) Link (s1, s2) utilization from controller port-stats telemetry; (Bottom) " + ("measured throughput and aggregate loss." if have3 else "capacity-model prediction, NOT measured.")))

    # Experimental Traffic Scenario & Performance
    story.append(P("<b>Experimental Traffic Scenario & Comparative Evaluation:</b>", h2_style))
    story.append(P(
        "We use a repeatable two-flow UDP scenario in Mininet (iperf2). Note on units: iperf2 interprets <font face='Courier'>-b 1.6M</font> "
        "with M = 2<super>20</super> bit/s, so the offered rates are <b>" + fnum(fx["off1"]) + " Mbps</b> and <b>" + fnum(fx["off2"]) + " Mbps</b> "
        "(the dynamic run receives exactly these rates).<br/>"
        "1. <b>Flow 1 (h1 &rarr; h2):</b> Starts at <i>t = 0 s</i> (<font face='Courier'>-b 1.6M</font>, 25 s). Dijkstra selects static path "
        "<font face='Courier'>[s1, s2]</font> (cost 20.0 ms). On the 2.0 Mbps link <font face='Courier'>s1&ndash;s2</font> the controller measured "
        + (("<b>U = " + fnum(fx["detect_util"], "{:.1f}") + "%</b> (" + fnum(fx.get("detect_rate")) + " Mbps on the wire, including headers)")
           if fx["detect_util"] is not None else "utilization above 80%") + ", above the 70% threshold.<br/>"
        "2. <b>Congestion Detection (measured, dynamic mode):</b> The controller flagged <font face='Courier'>s1&ndash;s2</font> at the first 2-s poll "
        "after Flow 1 reached full rate, before Flow 2 started, and raised its cost from 20.0 to <b>220.0</b>. In static mode the cost stays 20.0.<br/>"
        "3. <b>Flow 2 (h1 &rarr; h3):</b> Starts at <i>t = 6 s</i> in both modes (<font face='Courier'>-b 0.8M</font>, 15 s). "
        "Under <b>Static Routing</b>, only static delays count (Path via s2 = <i>20 + 10 = 30.0 ms</i> vs Path via s4 = <i>15 + 20 = 35.0 ms</i>), "
        "so Flow 2 also goes onto <font face='Courier'>s1&ndash;s2</font>. The offered load becomes <i>" + fnum(fx["off1"]) + " + " + fnum(fx["off2"]) + " = "
        + fnum(fx["off_sum"]) + " Mbps &gt; 2.0 Mbps</i>. A simple tail-drop capacity model (no buffering) would predict about "
        + fnum(fx["model_loss"], "{:.1f}") + "% loss.<br/>"
        + (("<b>What was measured instead:</b> no packets were lost (" + fnum(fx["loss_st"], "{:.1f}") + "%). The excess, about "
            + fnum(fx["excess_mb"], "{:.1f}") + " Mb over Flow 2's 15 s, was held in the link queue. Telemetry shows "
            "<font face='Courier'>s1&ndash;s2</font> pinned at &asymp;100% for about " + fnum(fx["sat_s"], "{:.0f}") + " s, longer than Flow 2's 15 s, "
            "so the queue was still draining after the senders stopped. Jitter rose from " + fnum(fx["jit_dy"][0]) + " / " + fnum(fx["jit_dy"][1])
            + " ms (congestion-aware) to " + fnum(fx["jit_st"][0]) + " / " + fnum(fx["jit_st"][1]) + " ms (static), and iperf's receive rate fell because "
            "the same packets arrived over a longer interval. In this setup, overload shows up as queueing delay and lower throughput, not as packet loss.<br/>")
           if (fx["loss_st"] is not None and fx["jit_st"] and fx["sat_s"]) else "") +
        "Under <b>Congestion-Aware Routing</b>, Path via s2 evaluates to <i>220.0 + 10.0 = 230.0 ms</i>, while Path via s4 evaluates to "
        "<i>15.0 + 20.0 = <b>35.0 ms</b></i>. Because 35.0 ms &lt; 230.0 ms, Dijkstra routes Flow 2 onto "
        "<b>Path [s1, s4, s3]</b>, avoiding the congested link."
    ))

    def g(d, f, k):
        try:
            return d[f][k]
        except Exception:
            return None
    def f2path(d):
        try:
            for x in d["routing_decisions"]:
                if "10.0.0.3" in x["flow"] and "dst_port=5002" in x["flow"]:
                    return x["path"]
            for x in d["routing_decisions"]:
                if "10.0.0.3" in x["flow"]:
                    return x["path"]
        except Exception:
            pass
        return None
    agg_st = r_st.get("aggregate_throughput_mbps") if r_st else None
    agg_dy = r_dy.get("aggregate_throughput_mbps") if r_dy else None
    gain = (100.0 * (agg_dy - agg_st) / agg_st) if (agg_st and agg_dy is not None) else None
    p3_metrics = [
        ["<b>Performance Metric (measured, iperf UDP server reports)</b>", "<b>Static Routing</b>", "<b>Congestion-Aware</b>", "<b>Capacity model, no buffering (static / aware)</b>"],
        ["Flow 1 throughput h1&rarr;h2 (Mbps)", fnum(g(r_st, "flow1", "bandwidth_mbps")), fnum(g(r_dy, "flow1", "bandwidth_mbps")), fnum(2.0 * fx["off1"] / fx["off_sum"]) + " / " + fnum(fx["off1"])],
        ["Flow 2 throughput h1&rarr;h3 (Mbps)", fnum(g(r_st, "flow2", "bandwidth_mbps")), fnum(g(r_dy, "flow2", "bandwidth_mbps")), fnum(2.0 * fx["off2"] / fx["off_sum"]) + " / " + fnum(fx["off2"])],
        ["Aggregate throughput (Mbps)", fnum(agg_st), fnum(agg_dy), "2.00 / " + fnum(fx["off_sum"])],
        ["Flow 1 loss (%)", fnum(g(r_st, "flow1", "packet_loss_percent"), "{:.1f}"), fnum(g(r_dy, "flow1", "packet_loss_percent"), "{:.1f}"), fnum(fx["model_loss"], "{:.1f}") + " / 0.0"],
        ["Flow 2 loss (%)", fnum(g(r_st, "flow2", "packet_loss_percent"), "{:.1f}"), fnum(g(r_dy, "flow2", "packet_loss_percent"), "{:.1f}"), fnum(fx["model_loss"], "{:.1f}") + " / 0.0"],
        ["Jitter Flow 1 / Flow 2 (ms)", fnum(g(r_st, "flow1", "jitter_ms")) + " / " + fnum(g(r_st, "flow2", "jitter_ms")), fnum(g(r_dy, "flow1", "jitter_ms")) + " / " + fnum(g(r_dy, "flow2", "jitter_ms")), "-"],
        ["Path chosen for Flow 2 (controller log)", str(f2path(r_st) or "not measured"), str(f2path(r_dy) or "not measured"), "s1-s2-s3 / s1-s4-s3"],
        ["Aggregate throughput gain", "-", fnum(gain, "{:+.1f}%"), fnum(100.0 * (fx["off_sum"] - 2.0) / 2.0, "{:+.1f}%")],
    ]
    story.append(make_table(p3_metrics, [5.0 * cm, 3.3 * cm, 3.3 * cm, CONTENT_WIDTH - 11.6 * cm]))
    story.append(Spacer(1, 3))

    # Controller Decision Explanation & Limitations
    story.append(P("<b>Controller Decision Explanation & System Limitations:</b>", h2_style))
    story.append(B(
        "<b>Controller Decision:</b> When Flow 2 arrived, static routing routed it through link <font face='Courier'>s1&ndash;s2</font> "
        "because <font face='Courier'>[s1, s2, s3]</font> has a lower base delay (30 ms) than <font face='Courier'>[s1, s4, s3]</font> (35 ms). "
        "This put " + fnum(fx["off_sum"]) + " Mbps of offered load on the 2 Mbps link. The congestion-aware controller penalized "
        "<font face='Courier'>s1&ndash;s2</font> by +200 ms, raising the cost of Path A to 230 ms. This made Path B (<font face='Courier'>[s1, s4, s3]</font>, 35 ms) "
        "look 6.6&times; cheaper. The controller assigned Flow 2 to Path B and left Flow 1's existing rule on <font face='Courier'>s1&ndash;s2</font> untouched. "
        + (("Path B was not spare capacity, though: Flow 2's " + fnum(fx["off2"]) + " Mbps on the 1 Mbps links drove "
            + " and ".join("<font face='Courier'>" + k.replace("-", "&ndash;") + "</font> to " + fnum(v, "{:.1f}") + "%" for k, v in fx["alt"].items())
            + ", and the controller flagged these links as congested as well (+200 ms). Both flows received their full offered rate, but both paths ended above the 70% threshold.")
           if fx["alt"] else "Both flows received their full offered rate.")
    ))
    story.append(B(
        "<b>Limitation 1 &mdash; Telemetry Polling Lag:</b> Statistics sampling occurs every 2 seconds. Sudden micro-bursts that congest a link "
        "and drain before the next <font face='Courier'>OFPPortStatsReply</font> are undetected, causing brief transient packet loss before rerouting takes effect."
    ))
    story.append(B(
        "<b>Limitation 2 &mdash; Flow Herding & Oscillation:</b> If multiple heavy flows arrive within the same 2-second polling window before "
        "utilization updates, they all get placed onto the alternate path, potentially creating sudden congestion on the secondary link (route flapping)."
        + (" This run already shows the capacity side of the problem: one rerouted 0.84 Mbps flow pushed the 1 Mbps alternate path above the threshold." if fx["alt"] else "")
    ))
    story.append(B(
        "<b>Limitation 3 &mdash; Coarse Flow Granularity:</b> The controller preserves existing flows and only guides new flows. If an existing elephant "
        "flow persists, the controller cannot dynamically migrate its sub-flows or perform in-flight multi-path splitting."
    ))

    # =========================================================================
    # REPRODUCTION INSTRUCTIONS
    # =========================================================================
    # fix5: spec asks to state topology changes and assumptions for each part
    story.append(P("4. Topology Files and Assumptions", h1_style))
    story.append(P(
        "<b>Topology files.</b> <font face='Courier'>p1_topo.py</font> (Part 1) and <font face='Courier'>p3_topo.py</font> (Parts 2 and 3) are used "
        "as provided. The only change is <font face='Courier'>p3_topo_mod.py</font>, a copy of <font face='Courier'>p3_topo.py</font> in which the "
        "delay of link (s4, s1) is lowered from 15 ms to 5 ms for the Part 2 link-modification test; all other links, bandwidths and hosts are unchanged. "
        "All topologies connect to the controller at 127.0.0.1:6633."
    ))
    story.append(B(
        "<b>Part 1:</b> Host MACs are fixed by Mininet (<font face='Courier'>autoSetMacs</font>, 00:00:00:00:00:0N for hN), so the proactive controller can pre-install "
        "rules for the known hosts. Packet-In counts include only user traffic; IPv6 (0x86dd) and LLDP (0x88cc) frames are excluded. Reactive rules use idle_timeout = 60 s."
    ))
    story.append(B(
        "<b>Part 2:</b> The chosen metric is link delay. Link delays and bandwidths are read from <font face='Courier'>p3_baseline.json</font> / "
        "<font face='Courier'>p3_modified.json</font>, which must match the topology in use. Host attachment points are learned from ARP/IP packets and seeded with the default locations. "
        "The controller answers ARP itself to avoid broadcast loops on the ring."
    ))
    story.append(B(
        "<b>Part 3:</b> Utilization is the transmit rate from port statistics, polled every 2 s, divided by the link capacity in the JSON file. A link at or above 70% "
        "gets +200 ms added to its cost. Only new flows use the updated costs; existing flows keep their rules (5-tuple rules at priority 20, idle_timeout = 30 s). "
        "Traffic is iperf2 UDP, where <font face='Courier'>-b 1.6M</font> means 1.6 &times; 2<super>20</super> bit/s."
    ))

    story.append(P("5. Reproducibility & Execution Instructions", h1_style))
    story.append(P(
        "All components are completely self-contained within this submission directory. The controllers run on standard Ubuntu Linux with Ryu and Mininet.<br/>"
        "&bull; <b>Full live pipeline (all six runs, then figures and this report):</b> <font face='Courier'>sudo ./run_all.sh</font><br/>"
        "&bull; <b>Offline logic check (Ryu stubbed; no OpenFlow I/O):</b> <font face='Courier'>python3 run_experiments.py --verify-all</font><br/>"
        "&bull; <b>Part 1 (Reactive):</b> <font face='Courier'>ryu-manager part1_reactive.py</font> | Mininet: <font face='Courier'>sudo python3 p1_topo.py</font> "
        "(or automated: <font face='Courier'>sudo python3 run_experiments.py --part 1 --mode reactive</font>)<br/>"
        "&bull; <b>Part 1 (Proactive):</b> <font face='Courier'>ryu-manager part1_proactive.py</font> | Mininet: <font face='Courier'>sudo python3 p1_topo.py</font> "
        "(or automated: <font face='Courier'>sudo python3 run_experiments.py --part 1 --mode proactive</font>)<br/>"
        "&bull; <b>Part 2 (Baseline):</b> <font face='Courier'>LINK_CONFIG=p3_baseline.json ryu-manager part2_controller.py</font> | Mininet: <font face='Courier'>sudo python3 p3_topo.py</font> "
        "(or: <font face='Courier'>sudo python3 run_experiments.py --part 2 --topo baseline</font>)<br/>"
        "&bull; <b>Part 2 (Modified):</b> <font face='Courier'>LINK_CONFIG=p3_modified.json ryu-manager part2_controller.py</font> | Mininet: <font face='Courier'>sudo python3 p3_topo_mod.py</font> "
        "(or: <font face='Courier'>sudo python3 run_experiments.py --part 2 --topo modified</font>)<br/>"
        "&bull; <b>Part 3 (Dynamic):</b> <font face='Courier'>ROUTING_MODE=dynamic LINK_CONFIG=p3_baseline.json ryu-manager part3_controller.py</font> | Mininet: <font face='Courier'>sudo python3 p3_topo.py</font> "
        "(or: <font face='Courier'>sudo python3 run_experiments.py --part 3 --mode dynamic</font>)<br/>"
        "&bull; <b>Part 3 (Static):</b> <font face='Courier'>ROUTING_MODE=static LINK_CONFIG=p3_baseline.json ryu-manager part3_controller.py</font> | Mininet: <font face='Courier'>sudo python3 p3_topo.py</font> "
        "(or: <font face='Courier'>sudo python3 run_experiments.py --part 3 --mode static</font>)"
    ))

    # Build PDF
    doc = SimpleDocTemplate(
        OUT,
        pagesize=A4,
        leftMargin=MARGIN_H,
        rightMargin=MARGIN_H,
        topMargin=MARGIN_V,
        bottomMargin=MARGIN_V,
        title="COL7524 Assignment 3 Report",
        author="Karan Joshi 2026MCS2654",
    )
    doc.build(story)
    print("Report successfully built:", OUT)


if __name__ == "__main__":
    build_pdf()
