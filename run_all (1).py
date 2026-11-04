#!/usr/bin/env python3
"""
Runs the full experiment matrix (must be run with sudo):
   mode      : baseline | sdn
   condition : idle | congested (UDP overload to the server) | flood (abusive chat client)
   clients   : 2 5 10 20

Output: results/summary.csv and results/raw_<mode>_<cond>_<n>.csv

  sudo python3 experiments/run_all.py --pox-dir ~/pox
"""
import argparse
import csv
import json
import math
import os
import socket
import statistics
import subprocess
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(ROOT, 'topology'))
import topo  # noqa: E402

CTRL_SOCK = '/tmp/chat_ctrl.sock'
EVENT_LOG = '/tmp/sdn_events.csv'
STAMP = '/tmp/flood_start'
FLOODER_IP = '10.0.0.101'
SERVER_IP = '10.0.0.1'


def start_controller(pox_dir, mode, out_dir, extra):
    env = dict(os.environ, PYTHONPATH=os.path.join(ROOT, 'controller'))
    logf = open(os.path.join(out_dir, f'controller_{mode}.log'), 'w')
    p = subprocess.Popen(['python3', 'pox.py', 'log.level', '--INFO', 'openflow.of_01',
                          'chat_controller', f'--mode={mode}'] + extra,
                         cwd=pox_dir, env=env, stdout=logf, stderr=subprocess.STDOUT)
    time.sleep(4)
    return p


def ctrl_reset():
    s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
    s.sendto(b'{"event":"RESET"}', CTRL_SOCK)
    s.close()
    time.sleep(1.5)


def pct(vals, p):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, int(round(p / 100 * (len(vals) - 1))))]


def flow_count():
    out = subprocess.run('ovs-ofctl -O OpenFlow10 dump-flows s1', shell=True,
                         capture_output=True, text=True).stdout
    return sum(1 for l in out.splitlines() if 'cookie=' in l)


def reaction_time():
    try:
        t0 = float(open(STAMP).read())
        with open(EVENT_LOG) as f:
            for row in csv.DictReader(f):
                if row['event'] == 'BLOCK' and row['ip'] == FLOODER_IP and float(row['ts']) >= t0:
                    return float(row['ts']) - t0
    except (OSError, ValueError):
        pass
    return None


def run_case(net, mode, cond, n, pings, out_dir):
    hosts = [h for h in net.hosts if h.name not in ('h1', 'hbg', 'hf')]
    hbg, hf = net.get('hbg'), net.get('hf')
    ctrl_reset()
    tag = f'{mode}_{cond}_{n}'
    raw = os.path.join(out_dir, f'raw_{tag}.csv')
    if os.path.exists(raw):
        os.remove(raw)
    if os.path.exists(STAMP):
        os.remove(STAMP)

    if cond == 'congested':
        hbg.sendCmd(f'iperf -c {SERVER_IP} -u -b 15M -t 300')      # 15M into a 10M link
        time.sleep(3)
    elif cond == 'flood':
        hf.sendCmd(f'python3 {ROOT}/client/flood_client.py {SERVER_IP} --duration 300 --stamp {STAMP}')
        time.sleep(1)

    k = min(n, len(hosts))
    per = [n // k + (1 if i < n % k else 0) for i in range(k)]
    t0 = time.time()
    for h, cnt in zip(hosts[:k], per):
        h.sendCmd(f'python3 {ROOT}/client/bench_client.py {SERVER_IP} --clients {cnt} '
                  f'--pings {pings} --interval 0.1 --prefix {tag}_{h.name} --label {tag} --out {raw}')
    for h in hosts[:k]:
        h.waitOutput()
    dur = time.time() - t0
    flows = flow_count()
    react = reaction_time() if cond == 'flood' else None

    for h in (hbg, hf):
        if h.waiting:
            h.sendInt()
            h.waitOutput()

    rtts, lost, setup = [], 0, []
    with open(raw) as f:
        for row in csv.DictReader(f, fieldnames=['kind', 'host', 'client', 'seq', 'value']):
            v = float(row['value'])
            if row['kind'] == 'ping':
                if v < 0:
                    lost += 1
                else:
                    rtts.append(v)
            elif v >= 0:
                setup.append(v)
    nan = float('nan')
    return {
        'mode': mode, 'condition': cond, 'clients': n,
        'mean_ms': round(statistics.mean(rtts), 3) if rtts else nan,
        'p95_ms': round(pct(rtts, 95), 3) if rtts else nan,
        'max_ms': round(max(rtts), 3) if rtts else nan,
        'lost': lost,
        'msgs_per_s': round(len(rtts) / dur, 2),
        'setup_ms': round(statistics.mean(setup), 3) if setup else nan,
        'flows': flows,
        'reaction_s': round(react, 3) if react is not None else nan,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pox-dir', required=True)
    ap.add_argument('--pings', type=int, default=40)
    ap.add_argument('--clients', type=int, nargs='+', default=[2, 5, 10, 20])
    ap.add_argument('--modes', nargs='+', default=['baseline', 'sdn'])
    ap.add_argument('--conditions', nargs='+', default=['idle', 'congested', 'flood'])
    ap.add_argument('--out', default=os.path.join(ROOT, 'experiments', 'results'))
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    fields = ['mode', 'condition', 'clients', 'mean_ms', 'p95_ms', 'max_ms', 'lost',
              'msgs_per_s', 'setup_ms', 'flows', 'reaction_s']
    summary = open(os.path.join(a.out, 'summary.csv'), 'w', newline='')
    writer = csv.DictWriter(summary, fieldnames=fields)
    writer.writeheader()

    for mode in a.modes:
        subprocess.run('mn -c', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        ctrl = start_controller(a.pox_dir, mode, a.out, [])
        net = topo.build_network(min(max(a.clients), 10))
        h1 = net.get('h1')
        h1.cmd('iperf -s -u > /dev/null 2>&1 &')
        topo.start_server(net)
        time.sleep(2)
        net.pingAll(timeout=1)
        try:
            for cond in a.conditions:
                for n in a.clients:
                    print(f'=== {mode} / {cond} / {n} clients ===', flush=True)
                    row = run_case(net, mode, cond, n, a.pings, a.out)
                    print(row, flush=True)
                    writer.writerow(row)
                    summary.flush()
        finally:
            h1.cmd('pkill -f chat_server.py; pkill iperf')
            net.stop()
            topo.clear_qos()
            ctrl.terminate()
            ctrl.wait()
    summary.close()
    print('done -> results/summary.csv ; now run experiments/plot.py')


if __name__ == '__main__':
    main()
