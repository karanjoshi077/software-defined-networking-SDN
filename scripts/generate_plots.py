#!/usr/bin/env python3
"""
Software-Defined Networking

Generates publication-quality figures for the SDN technical report.
Loads data directly from results/offline_verification.json or live measurement files if present.
Figures illustrate:
1. Part 1: Controller workload (Packet-Ins) and initial packet latency (Reactive vs Proactive).
2. Part 2: Computed Dijkstra path costs and theoretical/measured propagation RTT before and after link modification.
3. Part 3: Link (s1, s2) utilization timeline and bandwidth allocation under Static vs Congestion-Aware routing.
"""

import os
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def ensure_dir(d):
    os.makedirs(d, exist_ok=True)


def load_verification_data():
    """Loads offline verification or live measurement JSON."""
    json_path = os.path.join("results", "offline_verification.json")
    if os.path.exists(json_path):
        with open(json_path) as f:
            return json.load(f)
    return {}


def plot_part1(out_dir, vdata):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.5, 3.2), dpi=250)

    # Measured cumulative user Packet-Ins (parsed from Ryu logs by run_experiments.py)
    def _load(path):
        return json.load(open(path)) if os.path.exists(path) else None
    r_live = _load(os.path.join("results", "part1_reactive_live.json"))
    p_live = _load(os.path.join("results", "part1_proactive_live.json"))
    if r_live and p_live and "packet_in_curve" in r_live and "packet_in_curve" in p_live:
        flows = np.array(r_live["packet_in_curve"]["host_pairs"])
        reactive_packet_ins = np.array(r_live["packet_in_curve"]["cumulative_user_packet_ins"])
        proactive_packet_ins = np.array(p_live["packet_in_curve"]["cumulative_user_packet_ins"])
        left_suffix = "(Measured)"
    else:
        flows = np.array([0]); reactive_packet_ins = np.array([0]); proactive_packet_ins = np.array([0])
        left_suffix = "(NO LIVE DATA - run run_experiments.py --part 1)"

    # Subplot 1: Controller Workload (Packet-Ins Handled)
    ax1.plot(flows, reactive_packet_ins, marker="o", color="#d95f02", linewidth=2.0, label="Reactive")
    ax1.plot(flows, proactive_packet_ins, marker="s", color="#1b9e77", linewidth=2.0, label="Proactive")
    ax1.set_title(f"Controller Workload: user Packet-Ins {left_suffix}", fontsize=8.6, fontweight="bold", pad=8)
    ax1.set_xlabel("Host pairs that have communicated (cumulative)", fontsize=8.5)
    ax1.set_ylabel("Cumulative user Packet-Ins", fontsize=8.5)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(fontsize=7.8, frameon=True, loc="upper left")
    ax1.tick_params(labelsize=8)

    # Subplot 2: Forwarding Latency Breakdown (Live or Analytical Model)
    categories = ["1st Packet (Setup)", "Steady-State"]
    live_react_path = os.path.join("results", "part1_reactive_live.json")
    live_pro_path = os.path.join("results", "part1_proactive_live.json")

    if os.path.exists(live_react_path) and os.path.exists(live_pro_path):
        with open(live_react_path) as f: lr = json.load(f)["metrics"]
        with open(live_pro_path) as f: lp = json.load(f)["metrics"]
        reactive_rtt = [lr["first_packet_rtt_ms"], lr["steady_state_rtt_ms"]]
        proactive_rtt = [lp["first_packet_rtt_ms"], lp["steady_state_rtt_ms"]]
        title_suffix = "(Measured Live in Mininet)"
    else:
        # Analytical latency model: base propagation = 10.0 ms; reactive setup incurs ~4.5 ms controller roundtrip stall
        reactive_rtt = [0.0, 0.0]
        proactive_rtt = [0.0, 0.0]
        title_suffix = "(NO LIVE DATA)"

    x = np.arange(len(categories))
    width = 0.32

    rects1 = ax2.bar(x - width/2, reactive_rtt, width, label="Reactive", color="#d95f02", alpha=0.85, edgecolor="black", linewidth=0.6)
    rects2 = ax2.bar(x + width/2, proactive_rtt, width, label="Proactive", color="#1b9e77", alpha=0.85, edgecolor="black", linewidth=0.6)

    ax2.set_title(f"Forwarding Latency {title_suffix}", fontsize=9.2, fontweight="bold", pad=8)
    ax2.set_ylabel("Round Trip Time (ms)", fontsize=8.5)
    ax2.set_xticks(x)
    ax2.set_xticklabels(categories, fontsize=8.5)
    ax2.set_ylim(0, max(18, 1.25 * max(reactive_rtt + proactive_rtt)))
    ax2.grid(True, axis="y", linestyle="--", alpha=0.5)
    ax2.legend(fontsize=7.8, frameon=True, loc="upper right")
    ax2.tick_params(labelsize=8)

    for r in rects1:
        h = r.get_height()
        ax2.annotate(f"{h:.1f}ms", xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 2),
                     textcoords="offset points", ha="center", va="bottom", fontsize=7.5, fontweight="bold")
    for r in rects2:
        h = r.get_height()
        ax2.annotate(f"{h:.1f}ms", xy=(r.get_x() + r.get_width()/2, h), xytext=(0, 2),
                     textcoords="offset points", ha="center", va="bottom", fontsize=7.5, fontweight="bold")

    plt.tight_layout()
    out_path = os.path.join(out_dir, "fig_p1_packet_ins_rtt.png")
    fig.savefig(out_path)
    plt.close(fig)
    print("Generated:", out_path)


def plot_part2(out_dir, vdata):
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.5, 3.2), dpi=250)

    # Subplot 1: Computed Dijkstra Path Costs (Baseline vs Modified Topology)
    scenarios = ["Baseline Topology", "Modified Topology (s4-s1 = 5ms)"]
    cost_via_s2 = [30.0, 30.0]
    cost_via_s4 = [35.0, 25.0]

    p2_data = vdata.get("algorithmic_results", {}).get("part2", {})
    if p2_data:
        cost_via_s2[0] = p2_data.get("baseline_delay_cost_ms", 30.0)
        cost_via_s4[1] = p2_data.get("modified_delay_cost_ms", 25.0)

    x = np.arange(len(scenarios))
    width = 0.32

    r1 = ax1.bar(x - width/2, cost_via_s2, width, label="Path via s2 [s1-s2-s3]", color="#2b83ba", alpha=0.85, edgecolor="black", linewidth=0.6)
    r2 = ax1.bar(x + width/2, cost_via_s4, width, label="Path via s4 [s1-s4-s3]", color="#abdda4", alpha=0.85, edgecolor="black", linewidth=0.6)

    ax1.set_title("Computed Dijkstra Path Costs (h1 to h3)", fontsize=9.2, fontweight="bold", pad=8)
    ax1.set_ylabel("Calculated Delay Cost (ms)", fontsize=8.5)
    ax1.set_xticks(x)
    ax1.set_xticklabels(scenarios, fontsize=8.0)
    ax1.set_ylim(0, 42)
    ax1.grid(True, axis="y", linestyle="--", alpha=0.5)
    ax1.legend(fontsize=7.5, frameon=True, loc="upper right")
    ax1.tick_params(labelsize=8)

    ax1.annotate("SELECTED\n(30.0 ms)", xy=(x[0] - width/2, 30.0), xytext=(0, 3),
                 textcoords="offset points", ha="center", fontsize=7.5, fontweight="bold", color="#1f3a5f")
    ax1.annotate("SELECTED\n(25.0 ms)", xy=(x[1] + width/2, 25.0), xytext=(0, 3),
                 textcoords="offset points", ha="center", fontsize=7.5, fontweight="bold", color="#1f3a5f")

    # Subplot 2: End-to-End Propagation RTT (Theoretical or Measured)
    tests = ["Baseline (via s2: 30ms)", "Modified (via s4: 25ms)"]
    live_base_path = os.path.join("results", "part2_baseline_live.json")
    live_mod_path = os.path.join("results", "part2_modified_live.json")

    if os.path.exists(live_base_path) and os.path.exists(live_mod_path):
        with open(live_base_path) as f: rtt_base = json.load(f)["metrics_forward"]["rtt_avg_ms"]
        with open(live_mod_path) as f: rtt_mod = json.load(f)["metrics_forward"]["rtt_avg_ms"]
        rtts = [rtt_base, rtt_mod]
        title_sub2 = "Measured End-to-End RTT (Live Mininet)"
    else:
        # Theoretical two-way propagation delay: 2 * one-way delay
        rtts = [2.0 * cost_via_s2[0], 2.0 * cost_via_s4[1]]  # [60.0, 50.0]
        title_sub2 = "Theoretical Propagation RTT (2 × Delay) - NOT measured"

    colors = ["#2b83ba", "#fdae61"]
    bars = ax2.bar(tests, rtts, width=0.45, color=colors, alpha=0.9, edgecolor="black", linewidth=0.6)
    ax2.set_title(title_sub2, fontsize=9.2, fontweight="bold", pad=8)
    ax2.set_ylabel("Round Trip Time (ms)", fontsize=8.5)
    ax2.set_ylim(0, 75)
    ax2.grid(True, axis="y", linestyle="--", alpha=0.5)
    ax2.tick_params(labelsize=8)

    # theoretical 2 x one-way delay for comparison with measured RTT
    for xi, th in zip(range(len(bars)), [2.0 * cost_via_s2[0], 2.0 * cost_via_s4[1]]):
        ax2.hlines(th, xi - 0.3, xi + 0.3, colors="black", linestyles="--", linewidth=1.2,
                   label="Theoretical 2×delay" if xi == 0 else None)
    ax2.legend(fontsize=7.5, loc="upper right")
    for b in bars:
        h = b.get_height()
        ax2.annotate(f"{h:.1f} ms", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 3),
                     textcoords="offset points", ha="center", va="bottom", fontsize=8, fontweight="bold")

    plt.tight_layout()
    out_path = os.path.join(out_dir, "fig_p2_path_selection.png")
    fig.savefig(out_path)
    plt.close(fig)
    print("Generated:", out_path)


def plot_part3(out_dir, vdata):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(8.5, 4.4), dpi=250)

    # Subplot 1: Link (s1, s2) Utilization Timeline & Threshold Detection
    # Flow 1 (h1 -> h2) starts at t=0s, demanding 1.6 Mbps (80% of 2.0 Mbps capacity).
    # Congestion detected at t=4s (2 telemetry polling cycles of 2s each).
    # Flow 2 (h1 -> h3, 0.8 Mbps) arrives at t=6s.
    def _telemetry(mode):
        path = os.path.join("results", f"part3_{mode}_telemetry.csv")
        if not os.path.exists(path):
            return None
        import csv
        rows = list(csv.DictReader(open(path)))
        t = np.array([float(r["t_rel_s"]) for r in rows])
        rate = np.array([float(r["rate_mbps"]) for r in rows])
        util = np.array([float(r["util_pct"]) for r in rows])
        active = np.where(rate > 0.2)[0]          # align t=0 with the start of Flow 1
        if len(active):
            t = t - t[active[0]]
        return t, util
    tel_static, tel_dyn = _telemetry("static"), _telemetry("dynamic")
    if tel_static and tel_dyn:
        ax1.plot(tel_static[0], tel_static[1], "r--", marker="x", markersize=4, label="Link s1-s2 (Static) measured")
        ax1.plot(tel_dyn[0], tel_dyn[1], "b-", marker="o", markersize=4, label="Link s1-s2 (Dynamic) measured")
    else:
        ax1.text(0.5, 0.5, "NO LIVE TELEMETRY\nrun run_experiments.py --part 3 (static & dynamic)",
                 transform=ax1.transAxes, ha="center", va="center", fontsize=9, color="red")
    ax1.axhline(70, color="orange", linestyle=":", linewidth=1.5, label="Congestion Threshold (70%)")
    ax1.axvline(6, color="gray", linestyle="-.", alpha=0.7, label="Flow 2 Initiated (t=6s)")
    ax1.set_title("Link (s1, s2) Utilization Timeline & Threshold Trigger", fontsize=9.2, fontweight="bold", pad=6)
    ax1.set_ylabel("Utilization (%)", fontsize=8.5)
    ax1.set_xlabel("Time (seconds)", fontsize=8.0)
    ax1.set_ylim(0, 145)
    ax1.grid(True, linestyle="--", alpha=0.5)
    ax1.legend(fontsize=7.5, frameon=True, loc="upper left", ncol=2)
    ax1.tick_params(labelsize=8)

    # Subplot 2: Capacity Allocation & Theoretical Traffic Delivery
    # Scenario: Flow 1 (h1 -> h2, 1.6 Mbps UDP), Flow 2 (h1 -> h3, 0.8 Mbps UDP)
    modes = ["Static Routing (Collision on s1-s2)", "Congestion-Aware (Flow 2 on s1-s4-s3)"]
    live_p3_static = os.path.join("results", "part3_static_live.json")
    live_p3_dyn = os.path.join("results", "part3_dynamic_live.json")

    if os.path.exists(live_p3_static) and os.path.exists(live_p3_dyn):
        with open(live_p3_static) as f: s_data = json.load(f)
        with open(live_p3_dyn) as f: d_data = json.load(f)
        f1_tp = [s_data["flow1"]["bandwidth_mbps"], d_data["flow1"]["bandwidth_mbps"]]
        f2_tp = [s_data["flow2"]["bandwidth_mbps"], d_data["flow2"]["bandwidth_mbps"]]
        loss = [s_data.get("aggregate_loss_percent", s_data["flow1"]["packet_loss_percent"]),
                d_data.get("aggregate_loss_percent", d_data["flow1"]["packet_loss_percent"])]
        title_sub3 = "Throughput & Aggregate Loss (Measured Live)"
    else:
        # No live data: show the capacity-model prediction, clearly labelled as NOT measured.
        f1_tp = [1.33, 1.60]
        f2_tp = [0.67, 0.80]
        loss = [16.7, 0.0]
        title_sub3 = "Capacity-Model Prediction (NOT measured)"

    x = np.arange(len(modes))
    width = 0.28

    rects1 = ax2.bar(x - width, f1_tp, width, label="Flow 1: h1->h2 (Mbps)", color="#386cb0", edgecolor="black", linewidth=0.6)
    rects2 = ax2.bar(x, f2_tp, width, label="Flow 2: h1->h3 (Mbps)", color="#7fc97f", edgecolor="black", linewidth=0.6)

    ax2_loss = ax2.twinx()
    rects3 = ax2_loss.bar(x + width, loss, width, label="Drop / Loss Rate (%)", color="#e7298a", alpha=0.8, hatch="//", edgecolor="black", linewidth=0.6)

    ax2.set_title(title_sub3, fontsize=9.2, fontweight="bold", pad=6)
    ax2.set_ylabel("Served Throughput (Mbps)", fontsize=8.5)
    ax2_loss.set_ylabel("Drop Rate (%)", fontsize=8.5, color="#e7298a")
    ax2.set_xticks(x)
    ax2.set_xticklabels(modes, fontsize=8.2, fontweight="bold")
    ax2.set_ylim(0, 2.2)
    ax2_loss.set_ylim(0, 30)
    ax2.grid(True, axis="y", linestyle="--", alpha=0.5)
    ax2.tick_params(labelsize=8)
    ax2_loss.tick_params(labelsize=8, colors="#e7298a")

    for r in rects1:
        ax2.annotate(f"{r.get_height():.2f}M", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 2),
                     textcoords="offset points", ha="center", fontsize=7.5, fontweight="bold")
    for r in rects2:
        ax2.annotate(f"{r.get_height():.2f}M", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 2),
                     textcoords="offset points", ha="center", fontsize=7.5, fontweight="bold")
    for r in rects3:
        ax2_loss.annotate(f"{r.get_height():.1f}%", xy=(r.get_x() + r.get_width()/2, r.get_height()), xytext=(0, 2),
                          textcoords="offset points", ha="center", fontsize=7.5, fontweight="bold", color="#e7298a")

    lines1, labels1 = ax2.get_legend_handles_labels()
    lines2, labels2 = ax2_loss.get_legend_handles_labels()
    ax2.legend(lines1 + lines2, labels1 + labels2, fontsize=7.5, frameon=True, loc="upper left", ncol=3)

    plt.tight_layout()
    out_path = os.path.join(out_dir, "fig_p3_congestion_dynamics.png")
    fig.savefig(out_path)
    plt.close(fig)
    print("Generated:", out_path)


def main():
    out_dir = "results"
    ensure_dir(out_dir)
    vdata = load_verification_data()
    print("Generating figures in %s/..." % out_dir)
    plot_part1(out_dir, vdata)
    plot_part2(out_dir, vdata)
    plot_part3(out_dir, vdata)
    print("All figures successfully generated.")


if __name__ == "__main__":
    main()
