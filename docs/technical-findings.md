# Technical findings

## Flow management

Reactive forwarding installs rules on demand after Packet-In events. Proactive forwarding pre-installs rules at switch connection. The recorded offline verification reports 10 rules on switch s1 and 9 on s2 for proactive initialization. Live RTT and Packet-In measurements are stored separately.

## Link-metric routing

Dijkstra's algorithm uses delay or inverse bandwidth as link cost. In the baseline delay configuration the h1-to-h3 switch path is 1–2–3 (30 ms). Reducing the s4–s1 delay from 15 ms to 5 ms changes the optimal path to 1–4–3 (25 ms). The corresponding theoretical propagation RTT changes from 60 ms to 50 ms.

## Congestion-aware routing

The controller polls port statistics every two seconds, estimates utilization from byte-counter changes, and adds a 200 ms cost penalty when utilization exceeds 70%. In the recorded offline handler test, a 20 ms link cost rose to 220 ms, a new flow was steered via switches 1–4–3, and the cost was restored after congestion cleared. Existing flows are preserved.

The recorded experiment artifacts include static and dynamic routing telemetry, iperf measurements, and switch flow dumps. The capacity model and live measurements are distinct; see the JSON results for their respective values.

## Reproducibility

The offline verification summary records six algorithmic checks and the presence of six live experiment result files. These are historical results, not a fresh independent integration test.
