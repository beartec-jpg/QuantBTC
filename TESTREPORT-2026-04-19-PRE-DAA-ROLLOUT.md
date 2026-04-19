# QuantBTC Post-Genesis Baseline Snapshot — Pre-DAA v2 Rollout

**Date:** 2026-04-19 10:06 UTC  
**Network:** qbtctestnet  
**Purpose:** Capture the live 3-node cluster state immediately before deploying the new load-aware DAA v2 to all nodes.

---

## 1. Executive Summary

The testnet cluster had already been refreshed from genesis and was running a light-load baseline network, not the old 72-hour stress loop. At the time of capture:

- all 3 nodes were online and peered
- the chain was healthy and advancing near its expected cadence
- background mempool load was very low
- memory usage was far below the earlier 72-hour endurance levels
- all nodes were still on the older pre-DAA-v2 code revision

This made the cluster a good candidate for a clean DAA v2 rollout.

---

## 2. Live Node Snapshot Before Shutdown

| Node | Host | Commit | Height | Difficulty | Peers | Mempool | RSS Memory | CPU | Datadir Size |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| hel1-2 | 46.62.156.169 | 51eb804 | 8549 | 0.0021650 | 4 | 5 | 628 MB | 76.3% | 11.2 GB |
| hel1-3 | 37.27.47.236 | 51eb8048 | 8554 | 0.0017973 | 4 | 0 | 498 MB | 78.4% | 6.8 GB |
| hel1-4 | 89.167.109.241 | 51eb8048 | 8535 | 0.0022067 | 4 | 7 | 570 MB | 76.6% | 6.2 GB |

### Additional consensus/state observations

- DAG mode active on all nodes
- GHOSTDAG K = 32
- all nodes were pruned with 10 GB targets
- DAG tips = 1 on the live snapshot
- supply at snapshot was approximately 7,112–7,128 QBTC depending on node height
- UTXO set size was approximately 10.8k–11.1k outputs

---

## 3. Comparison Against Previous Iterations

### 3.1 Versus the prior 72-hour endurance / surge runs

From the earlier published reports:

- 72-hour final endurance run produced approximately **25,736 blocks** and approximately **417,000 transactions**
- the 72-hour comparative run ended around **67,462–67,463 blocks**
- previous node RSS under sustained stress was roughly:
  - **3.0 GB** on the hybrid node
  - **2.7 GB** on the classical nodes
- sustained CPU during the 72-hour comparison was roughly:
  - **104%** on the hybrid node
  - **86–88%** on the classical nodes
- full chain data at that stage was about **4.23–4.49 GB**

### 3.2 Current baseline versus the previous stressed network

| Metric | Previous 72h iteration | Current refreshed network | Interpretation |
|---|---:|---:|---|
| Height | ~67.5k blocks | ~8.5k blocks | Fresh chain since genesis restart |
| Estimated chain data | ~4.23–4.49 GB | ~110 MB raw chain data | Much smaller due to new chain age |
| RSS memory | ~2.7–3.0 GB | ~498–628 MB | Roughly 77–83% lower memory footprint |
| CPU | ~86–104% | ~76–78% | Lower sustained load, fewer active tx loops |
| Mempool | surge bursts / heavy sustained tx flow | 0–7 tx | Network currently running at light baseline activity |
| Stability | 72h completed, zero consensus splits | healthy live cluster, 4 peers each | Good pre-rollout state |

### 3.3 Performance interpretation

The current cluster is behaving like a healthy low-load production baseline rather than a stress harness:

- **memory pressure is dramatically lower** than during the Dilithium/Falcon comparison runs
- **CPU remains active** because nodes are still mining, but it is below the peak endurance values
- **mempool pressure is minimal**, which gives a clean starting point for evaluating the effect of DAA v2 after rollout
- **block cadence remains healthy**, indicating the network is stable enough to restart on the upgraded code

---

## 4. Why This Snapshot Matters for DAA v2

The new DAA v2 introduces a load-aware square-root hardening curve that is intended to:

1. preserve smooth behavior under normal traffic,
2. harden difficulty under sustained spam or overload,
3. and relax back down toward baseline after the load clears.

Because the cluster was in a low-load, near-baseline condition at the time of shutdown, this snapshot serves as a clean pre-deployment reference for:

- memory usage,
- baseline difficulty,
- mempool occupancy,
- chain growth,
- and peer health.

---

## 5. Rollout Status

At the time this report was written:

- the live qBTC daemons had been shut down cleanly on all three nodes
- the cluster was ready for the DAA v2 binary rollout
- all nodes were still on the older commit family around **51eb804**, which predates the new load-aware DAA v2 work already pushed to the main repository

---

## 6. Conclusion

The refreshed-from-genesis testnet is healthy, lightly loaded, and materially less memory-intensive than the earlier long-duration surge environments. Compared with the previous 72-hour runs, current resource usage is far lower while connectivity and consensus remain intact.

This is the correct moment to deploy the new DAA v2 across all three nodes and then observe whether the network maintains its current stability while gaining improved resistance to spam-driven load spikes.
