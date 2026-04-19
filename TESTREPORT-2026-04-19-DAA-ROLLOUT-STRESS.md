# QuantBTC DAA Rollout and Live Stress Validation Report

**Date:** 2026-04-19  
**Network:** qbtctestnet  
**Scope:** Pre-rollout baseline capture, live 3-node DAA deployment, progressive spam-pressure validation, and observed recovery behavior.

---

## 1. Executive Summary

On 2026-04-19, the live 3-node qBTC testnet was:

1. measured in a clean post-genesis baseline state,
2. shut down and upgraded to the newer load-aware DAA code,
3. restarted and re-peered,
4. then exercised with progressively stronger transaction-pressure tests.

### High-level outcome

- the cluster stayed online and continued advancing during all observed load phases,
- the new DAA hardened upward under pressure,
- mempool congestion became visible once the test was escalated,
- fee pressure increased during burst windows and eased during clearance windows,
- no consensus split or permanent stall was observed during the live validation window.

---

## 2. Pre-Rollout Baseline

Immediately before rollout, the cluster was still on the older pre-upgrade commit family around **51eb804** and was lightly loaded.

| Node | Host | Height | Difficulty | Peers | Mempool | RSS Memory | CPU | Datadir |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| hel1-2 | 46.62.156.169 | 8549 | 0.0021650 | 4 | 5 | 628 MB | 76.3% | 11.2 GB |
| hel1-3 | 37.27.47.236 | 8554 | 0.0017973 | 4 | 0 | 498 MB | 78.4% | 6.8 GB |
| hel1-4 | 89.167.109.241 | 8535 | 0.0022067 | 4 | 7 | 570 MB | 76.6% | 6.2 GB |

### Baseline interpretation

- all 3 nodes were healthy and peered,
- mempool activity was minimal,
- memory use was far below the earlier 72-hour endurance runs,
- the refreshed-from-genesis chain provided a clean reference point for the DAA rollout.

---

## 3. Upgrade / Rollout

The network was stopped and upgraded to the newer DAA code path now deployed on the live servers.

### Rollout actions completed

- cluster shut down cleanly,
- servers pulled the newer code revision,
- nodes rebuilt and restarted,
- manual re-peering was used where needed to restore the mesh.

### Deployed revision on the live nodes

- upgraded live nodes pulled to commit family around **9eed786** during rollout.

---

## 4. Stress Method Used

The live validation intentionally used **transaction-pressure simulation**, not exploit tooling.

### Mechanisms used

- repeated bursts of small valid transfers,
- many fresh destination addresses,
- sustained submission over time,
- reduced mining cadence so backlog could accumulate,
- pressure applied from all 3 nodes rather than a single host.

### Not used

- no invalid-block attack,
- no consensus exploit attempt,
- no peer-ban abuse,
- no crash/corruption attack,
- no network-layer DDoS tooling.

---

## 5. Observed Load Phases

### Phase A — Initial lighter attack

The first live pressure test was real, but the network absorbed much of it quickly.

#### Representative observations

| Node | Observation |
|---|---|
| hel1-2 | reached about **round=30 / sent=600**, mempool often returned to **0**, difficulty climbed as high as about **0.0095389** before easing |
| hel1-3 | reached about **round=77 / sent=1540**, mempool spikes such as **13–18**, difficulty around **0.00334596** |
| hel1-4 | reached about **round=82 / sent=1640**, difficulty moved through roughly **0.00024–0.008+**, mempool usually low |

### Interpretation

The first attack profile proved that the chain was under load, but it was still clearing bursts rapidly enough that the scan page did not look heavily congested for long.

---

### Phase B — Heavier attack

The load was then increased to produce more visible backlog.

#### Early heavy-start snapshot

| Node | Height | Mempool | Difficulty |
|---|---:|---:|---:|
| hel1-2 | 9008 | 0 | 0.00205555 |
| hel1-3 | 9082 | 33 | 0.00334596 |
| hel1-4 | 8973 | 13 | 0.00024414 |

This confirmed that congestion was now starting to build.

---

### Phase C — Saturation-style attack

A stronger saturation profile was deployed with larger bursts and less frequent mining.

#### Verified live snapshots during saturation

| Node | Representative round | Height | Mempool | Difficulty |
|---|---:|---:|---:|---:|
| hel1-2 | heavy_round=8 | 9095 | 24 | 0.00772725 |
| hel1-3 | heavy_round=22 | 9143 | 61 | 0.00311253 |
| hel1-4 | heavy_round=15 | 9038 | 38 | 0.00248707 |

Additional confirmed observations:

- hel1-3 also showed intermediate mempool levels of **16, 24, 40, 52, 62**, then later dropped back down,
- hel1-4 showed visible backlog windows such as **13, 20, 28, 36, 38**, then partially cleared,
- hel1-2 remained the strongest clearer, but still climbed to roughly **0.0077** difficulty under the heavier phase.

---

## 6. Recovery / Deterrent Behavior

The observed pattern was:

- transaction bursts increased backlog,
- fee pressure rose,
- difficulty hardened upward,
- the network then cleared part of the backlog and difficulty relaxed.

### Operator-observed fee behavior

During the stronger bursts, the explorer view showed average fee spikes up to roughly **900 sat/vB**, followed by declines after clearance windows.

### Effective deterrent behavior

This indicates the new system is working in the intended direction:

- more spam pressure increases the work needed to sustain the attack,
- higher congestion makes fee pressure visible,
- the chain did not remain permanently jammed in the observed window.

---

## 7. Peak Metrics Observed During This Session

| Metric | Verified observation |
|---|---|
| Highest difficulty seen in-session | about **0.0095389** on hel1-2 during the earlier live pressure phase |
| Strongest sustained heavy-phase diff | about **0.00772725** on hel1-2 |
| Highest mempool seen in heavy escalation | about **61–62** pending tx on hel1-3 |
| Additional visible backlog | about **38** pending tx on hel1-4 |
| Baseline pre-rollout peer health | **4 peers each** on the clean snapshot |
| Later peer health under load | fluctuated to roughly **1–3 peers** on some nodes |

---

## 8. Mesh / Propagation Notes

The main infrastructure weakness observed during the live phase was not consensus instability but **thin peering** after restart.

### Recommendation

For a healthier permanent 3-node mesh:

- each node should persistently know the other two,
- peer entries should be stored in config rather than relying only on manual one-shot reconnection,
- this will improve propagation consistency during stress windows.

---

## 9. Conclusion

The 2026-04-19 rollout achieved its primary goals.

### Verified outcomes

- the new DAA code was deployed to the live testnet,
- the network stayed up under progressively stronger transaction-pressure tests,
- difficulty responded upward under load,
- congestion and fee spikes became visible once the attack profile was intensified,
- the chain continued advancing and showed recovery between waves.

### Overall assessment

**Result:** the upgraded qBTC testnet demonstrated meaningful resistance to live spam-pressure and behaved consistently with a load-aware DAA that hardens under stress while remaining operational.
