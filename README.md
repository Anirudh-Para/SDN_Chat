# SDN-Managed TCP Chat Application & Evaluation Suite

A production-grade, multi-client chat system built on **Mininet**, the **POX SDN Controller**, **Open vSwitch (OVS)**, and **raw Python TCP sockets**, featuring a multi-IP web-to-TCP gateway, live QoS queue management, runtime packet-loss injection, and automated stress testing.

---

## 🏗️ System Architecture

1. **TCP Chat Backend (`server/chat_server.py`)**: A multi-threaded raw TCP server (`AF_INET`, `SOCK_STREAM` on port `6666`) managing rooms, private messaging, and newline-delimited framing. It communicates out-of-band with the POX controller via a Unix datagram socket (`/tmp/chat_ctrl.sock`).
2. **Mininet Topology & QoS (`topology/topo.py`)**: Builds an OpenFlow 1.0 network with switch `s1` and configures **3 Linux-HTB QoS priority queues** per port (Queue 0: Background/Default, Queue 1: Standard Chat, Queue 2: VIP Room Chat).
3. **Application-Aware POX Controller (`chat_controller.py`)**: Monitors chat traffic dynamically. Users who join the `vip` room are upgraded to high-priority Queue 2. A rolling rate monitor detects floods (`> 1 MB / 2s`) and pushes OpenFlow drop rules to block abusive hosts for 30 seconds.
4. **Web-to-TCP Gateway (`web/gateway.py`)**: A zero-dependency `asyncio` HTTP and RFC 6455 WebSocket server on port `8080`. It allocates a unique virtual IP from a pool (`10.0.0.200–249`) to every open browser tab, binding each tab to an independent TCP connection so the SDN controller tracks every tab as a distinct host.
5. **Automated Testing & Benchmarking**: Includes headless benchmark clients (`bench_client.py`), a DoS flood attacker (`flood_client.py`), an experiment runner (`run_all.py`), and a matplotlib plotting script (`plot.py`).

---

## 📂 Project Directory Structure

```text
sdn_chatbox/
├── server/
│   └── chat_server.py       # Multi-threaded raw TCP chat server
├── topology/
│   ├── topo.py              # Mininet topology, HTB QoS, and Netem loss engine
│   ├── loss_control.py      # Unix stream socket daemon for runtime loss injection
│   └── set_loss.py          # CLI helper to change packet loss on the fly
├── web/
│   ├── gateway.py           # Multi-IP WebSocket-to-TCP gateway
│   └── index.html           # Single-page frontend (UI, RTT monitor, loss slider)
├── client/
│   ├── bench_client.py      # Automated RTT measurement and benchmarking tool
│   └── flood_client.py      # DoS traffic generator for SDN flood mitigation tests
├── experiments/
│   ├── run_all.py           # Automated test matrix runner (24 scenarios)
│   └── plot.py              # Matplotlib chart generator (RTT, QoS, Reaction Time)
└── README.md
```

---

## ⚙️ Prerequisites & Dependencies

* Ubuntu 20.04 / 22.04 LTS (VirtualBox or Native VM)
* Mininet & Open vSwitch
* POX SDN Controller
* Python 3.10+ with `matplotlib`, `numpy`, and `requests`

---

## 🚀 Step-by-Step Execution Guide

### 0. Pre-Flight Cleanup
Before starting the network, clear any stale OVS state or lingering background processes:
```bash
sudo mn -c
sudo pkill -f chat_server.py
sudo pkill -9 -f pox.py
```

### 1. Terminal 1: Start the POX SDN Controller
Copy the custom application-aware controller into POX and launch it:
```bash
cp chat_controller.py ~/pox/ext/
cd ~/pox
sudo ./pox.py log.level --DEBUG forwarding.l2_learning chat_controller
```

### 2. Terminal 2: Launch Mininet & the TCP Chat Server
Build the virtual network, configure HTB QoS queues, and start `chat_server.py` on host `h1`:
```bash
cd ~/sdn_chatbox
sudo python3 topology/topo.py --web --auto-server
```

### 3. Terminal 3: Start the Web-to-TCP Gateway
Bridge browser tabs into independent TCP sockets mapped to the IP pool (`10.0.0.200–249`):
```bash
cd ~/sdn_chatbox
python3 web/gateway.py --server 10.0.0.1 --pool 10.0.0.200-10.0.0.249
```

### 4. Open the UI in Firefox
Navigate to:
```text
http://localhost:8080
```
* Enter different usernames in separate tabs (e.g., **Alice**, **Bob**).
* Try joining the VIP room (`/join vip`) to test queue priority.
* Test live packet loss using the sidebar slider or quick preset buttons (`0%`, `5%`, `10%`, `25%`, `50%`, `100%`).

---

## 📊 Running Automated Benchmarks & Generating Plots

To execute the full test matrix (evaluating baseline vs. sdn modes across idle, congested, and flood conditions for 2, 5, 10, and 20 clients) and generate evaluation charts:

```bash
cd ~/sdn_chatbox
sudo python3 experiments/run_all.py --pox-dir ~/pox
python3 experiments/plot.py
```

Generated PNG charts will be saved in `experiments/plots/`:
* `rtt_vs_clients.png` — Mean latency across conditions.
* `congestion_rtt.png` — 95th-percentile tail latency under 15 Mbps UDP congestion.
* `reaction_time.png` — SDN controller flood reaction speed.

---

## 🛑 Clean Teardown Protocol

1. **Terminal 3:** Press `Ctrl + C` to stop the web gateway.
2. **Terminal 2:** Type `exit` to close the Mininet CLI.
3. **Terminal 1:** Press `Ctrl + C` to stop the POX controller.
4. **Final Cleanup:**
   ```bash
   sudo mn -c && sudo pkill -f chat_server.py && sudo pkill -9 -f pox.py
   ```
