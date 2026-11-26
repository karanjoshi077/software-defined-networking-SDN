#!/usr/bin/env bash
# Runs all six live Mininet+Ryu experiments, then regenerates figures and report.pdf.
# Usage:  sudo ./run_all.sh
# Optional: PY_RUN=/path/to/python (for run_experiments.py, needs mininet)
#           PY_DOC=/path/to/python (for plots/report, needs matplotlib, numpy, reportlab, pillow)
set -euo pipefail
cd "$(dirname "$0")"
PY_RUN="${PY_RUN:-python3}"
PY_DOC="${PY_DOC:-python3}"

if [ "$(id -u)" -ne 0 ]; then echo "Run with sudo: sudo ./run_all.sh"; exit 1; fi
command -v iperf >/dev/null || { echo "iperf (v2) not found: sudo apt install iperf"; exit 1; }
command -v ovs-ofctl >/dev/null || { echo "ovs-ofctl not found (openvswitch-switch)"; exit 1; }

trap 'mn -c >/dev/null 2>&1 || true' EXIT
mkdir -p results
rm -f results/*_live.json results/part3_*_telemetry.csv results/flow_dump_*.txt

"$PY_RUN" run_experiments.py --part 1 --mode reactive
"$PY_RUN" run_experiments.py --part 1 --mode proactive
"$PY_RUN" run_experiments.py --part 2 --topo baseline
"$PY_RUN" run_experiments.py --part 2 --topo modified
"$PY_RUN" run_experiments.py --part 3 --mode static
"$PY_RUN" run_experiments.py --part 3 --mode dynamic
mn -c >/dev/null 2>&1 || true

PYTHONPATH=. "$PY_RUN" run_experiments.py --verify-all || true

# plots + report as the invoking user's python (root's python may lack matplotlib/reportlab)
"$PY_DOC" scripts/generate_plots.py
"$PY_DOC" scripts/build_report.py

if [ -n "${SUDO_USER:-}" ]; then chown -R "$SUDO_USER":"$SUDO_USER" results report.pdf 2>/dev/null || true; fi
echo "Done. Check results/*.json, results/*telemetry.csv and report.pdf"
