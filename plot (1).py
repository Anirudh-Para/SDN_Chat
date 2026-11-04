#!/usr/bin/env python3
"""Creates plots/*.png from results/summary.csv   (pip install matplotlib)"""
import csv
import os

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
rows = list(csv.DictReader(open(os.path.join(HERE, 'results', 'summary.csv'))))
os.makedirs(os.path.join(HERE, 'plots'), exist_ok=True)


def series(mode, cond, key):
    r = sorted([x for x in rows if x['mode'] == mode and x['condition'] == cond],
               key=lambda x: int(x['clients']))
    return [int(x['clients']) for x in r], [float(x[key]) for x in r]


# 1. Mean RTT vs number of clients, one subplot per condition
conds = ['idle', 'congested', 'flood']
fig, axes = plt.subplots(1, 3, figsize=(15, 4), sharey=False)
for ax, cond in zip(axes, conds):
    for mode, style in (('baseline', 'o--'), ('sdn', 's-')):
        x, y = series(mode, cond, 'mean_ms')
        ax.plot(x, y, style, label=mode)
    ax.set_title(f'{cond}')
    ax.set_xlabel('concurrent clients')
    ax.set_ylabel('mean RTT (ms)')
    ax.set_yscale('log')
    ax.grid(True, alpha=.3)
    ax.legend()
fig.suptitle('Chat RTT vs number of clients: baseline L2 vs SDN priority/policy')
fig.tight_layout()
fig.savefig(os.path.join(HERE, 'plots', 'rtt_vs_clients.png'), dpi=150)

# 2. Congested: mean and p95 bars
fig, ax = plt.subplots(figsize=(8, 4))
xs, base = series('baseline', 'congested', 'p95_ms')
_, sdn = series('sdn', 'congested', 'p95_ms')
w = 0.38
ax.bar([i - w / 2 for i in range(len(xs))], base, w, label='baseline p95')
ax.bar([i + w / 2 for i in range(len(xs))], sdn, w, label='sdn p95')
ax.set_xticks(range(len(xs)))
ax.set_xticklabels(xs)
ax.set_xlabel('concurrent clients')
ax.set_ylabel('p95 RTT (ms)')
ax.set_yscale('log')
ax.set_title('RTT under UDP congestion (15 Mbps into 10 Mbps link)')
ax.legend()
fig.tight_layout()
fig.savefig(os.path.join(HERE, 'plots', 'congestion_rtt.png'), dpi=150)

# 3. Controller reaction time to flooding client
xs, react = series('sdn', 'flood', 'reaction_s')
fig, ax = plt.subplots(figsize=(6, 4))
ax.bar([str(x) for x in xs], react)
ax.set_xlabel('concurrent clients')
ax.set_ylabel('flood start -> drop rule (s)')
ax.set_title('SDN reaction time to flooding client')
fig.tight_layout()
fig.savefig(os.path.join(HERE, 'plots', 'reaction_time.png'), dpi=150)
print('plots written to experiments/plots/')
