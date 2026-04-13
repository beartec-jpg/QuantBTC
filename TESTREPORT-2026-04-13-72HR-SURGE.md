# QuantumBTC Testnet 72-Hour Surge Endurance Report (Continuation)

**Date:** 2026-04-13 05:32 UTC snapshot  
**Chain:** `qbtctestnet` (GHOSTDAG K=32, PQC ALWAYS_ACTIVE)  
**Continuation from:** `TESTREPORT-2026-04-10-CHAIN-FINAL.md`  
**Test script:** `contrib/qbtc-testnet/surge_test_72hr.sh`  
**Status:** In progress at snapshot time (`58.4h / 72h`, 13/18 surges completed per node)

---

## 1. Executive Summary

This report continues from the pre-wipe snapshot documented on 2026-04-10 and captures live results from the 72-hour baseline+surge stress campaign running on all 3 testnet nodes.

At the 2026-04-13 05:32 UTC snapshot:

- All 3 nodes are synchronized at height **23,813** with identical best block hash.
- No consensus split observed (same `bestblockhash`, `chainwork`, txoutset hash, and total supply on all nodes).
- Surge framework is active on all nodes with **13 completed surges** each.
- Cumulative generated load from local send loops: **387,436 successful tx submissions** across 3 nodes.
- Cumulative local mined blocks during this campaign: **3,786** across 3 nodes.
- DAG remained stable under repeated surge intervals; `dag_tips` stayed low on live chain (1-2 at snapshot).

---

## 2. Test Design (from `surge_test_72hr.sh`)

### Baseline mode
- Mining sleep: `1.5s`
- TX spray: `5 tx / round`, round sleep `3s`

### Surge mode
- Mining sleep: `0.1s`
- TX spray: `50 tx / round`, round sleep `0.5s`

### Surge cadence
- Every `4h`
- Duration `20m`
- Planned: `18` surges over 72h

### Telemetry
- `/tmp/surge_metrics.csv` sampled every `60s`
- `/tmp/surge_test.log` event log and surge boundaries

---

## 3. Network Topology and Live Sync State

| Node | Hostname | IP | Height | Best Block Hash | Peers | DAG Tips | Pruned |
|------|----------|----|--------|------------------|-------|----------|--------|
| N1 | ubuntu-4gb-hel1-2 | 46.62.156.169 | 23,813 | 00000029f3cf63d346a63769a3b5745d8a3933358a47c65e721009bc4c3fff9b | 4 | 2 | Yes |
| N2 | ubuntu-4gb-hel1-3 | 37.27.47.236 | 23,813 | 00000029f3cf63d346a63769a3b5745d8a3933358a47c65e721009bc4c3fff9b | 6 | 1 | Yes |
| N3 | ubuntu-4gb-hel1-4 | 89.167.109.241 | 23,813 | 00000029f3cf63d346a63769a3b5745d8a3933358a47c65e721009bc4c3fff9b | 4 | 1 | No |

Consensus health indicators at snapshot:
- `verificationprogress = 1` on all nodes
- identical `chainwork = 0x...e268f36d34`
- identical txoutset summary (`txouts=26,017`, `total_amount=19,844.16658729`)

---

## 4. 72-Hour Campaign Progress at Snapshot

| Node | Metrics Rows | Elapsed Hours | Mode at Snapshot | Session Mined | Session TX Sent |
|------|--------------|---------------|------------------|---------------|-----------------|
| N1 | 3,467 | 58.41h | baseline | 1,212 | 141,151 |
| N2 | 3,224 | 58.41h | baseline | 1,154 | 122,386 |
| N3 | 3,443 | 58.43h | baseline | 1,420 | 123,899 |
| **Total** | — | ~58.4h | — | **3,786** | **387,436** |

Derived rate (campaign to snapshot):
- Aggregate generated send rate: ~`1.84 tx/s` (submission-side, successful local RPC sends)
- Aggregate mined rate: ~`64.8 blocks/hour` counted per-node local mining loop

Notes:
- Session counters are per-node local loop counters and can include overlapping block attempts among miners.
- Consensus truth remains chain height and canonical block history.

---

## 5. Surge Event Accounting (Deduplicated)

Raw logs contain duplicate printed lines in places; surge counts below are deduplicated by surge number.

| Node | Unique Surge Starts | Unique Surge Ends | Surge Blocks (+) | Surge Mined (+) | Surge TX (+) | Max Surge Pool | Max Surge Tips |
|------|---------------------|-------------------|------------------|-----------------|--------------|----------------|----------------|
| N1 | 13 | 13 | 1,371 | 116 | 16,909 | 100 | 2 |
| N2 | 13 | 13 | 1,353 | 109 | 14,483 | 264 | 13 |
| N3 | 13 | 13 | 1,356 | 156 | 17,067 | 57 | 2 |
| **Total** | **39** | **39** | **4,080** | **381** | **48,459** | — | — |

Progress vs planned campaign:
- Planned surges per node: 18
- Completed at snapshot: 13
- Completion: `72.2%`

---

## 6. Chain Progression Milestones (N1 canonical timeline)

| Height | Timestamp (UTC) | nTx in Block |
|--------|------------------|--------------|
| 3,157 | 2026-04-10 19:06:36 | 13 |
| 5,000 | 2026-04-11 00:41:21 | 102 |
| 10,000 | 2026-04-11 14:51:55 | 9 |
| 15,000 | 2026-04-12 04:53:06 | 8 |
| 20,000 | 2026-04-12 18:49:18 | 6 |
| 23,813 | 2026-04-13 05:32:06 | 1 |

From height 3,157 to 23,813:
- Delta: `20,656` blocks over ~`58.43h`
- Effective block production: ~`353.5 blocks/hour` (~`5.9 blocks/min`)

This remains consistent with prior sustained behavior reported on April 9-10.

---

## 7. Mempool, DAG Tip, and Resource Behavior

### Mempool size observed in metrics windows
- N1: min 0, max 359
- N2: min 0, max 261
- N3: min 0, max 522

### DAG tips observed in metrics windows
- N1: min 1, max 3
- N2: min 1, max 74
- N3: min 0, max 3

Interpretation:
- Live chain at snapshot is healthy (`dag_tips` 1-2).
- N2's spike to 74 in sampled metrics indicates a transient backlog/contention episode during heavy load but did not cause persistent divergence or chain split.

### Disk / pruning state (snapshot)
- N1: `size_on_disk` 3,014,726,675 bytes, pruned
- N2: `size_on_disk` 3,011,173,478 bytes, pruned
- N3: `size_on_disk` 3,015,359,743 bytes, not pruned

---

## 8. Wallet Activity Snapshot (Miner wallets)

| Node | Miner Balance | Immature Balance | Miner Tx Count |
|------|---------------|------------------|----------------|
| N1 | 4,767.53312025 | 5.84179691 | 6,200 |
| N2 | 4,259.23719274 | 33.36936200 | 6,539 |
| N3 | 2.09529041 | 5.01119948 | 2,020 |

Additional N1 wallet rollup:
- `surge_w1..surge_w12` subtotal balance: **91.02956680 QBTC**
- `surge_w1..surge_w12` subtotal txcount: **282,218**

---

## 9. Deviations and Issues Observed

1. Campaign not yet complete at snapshot (`58.4h/72h`).
2. Surge logs include duplicate printed event lines in places; deduplication by surge number is required for accurate totals.
3. One parser artifact in script output (`final_report_lines=0` plus an extra `0` line) appears to come from grep fallback behavior, not consensus or node instability.
4. Node 2 showed a transient high `dag_tips` sample (74) during load, but final chain converged cleanly across all nodes.

---

## 10. Conclusion (Interim)

The ongoing 72-hour surge test is tracking healthy at ~58.4 hours:
- synchronized 3-node consensus,
- stable GHOSTDAG operation under periodic high-pressure surges,
- substantial sustained transaction generation,
- no persistent fork or chain split.

At current trajectory, the test is expected to complete the remaining 5 surge windows without requiring topology or parameter changes.

---

## 11. Completion Checklist for Final 72h Closeout

When runtime reaches 72h, append final closeout with:
1. Final `surge_metrics.csv` row counts per node
2. Completed surge count (target 18/18 each)
3. Final block delta and effective blocks/hour over full 72h
4. Final mempool and DAG-tip extrema across full run
5. Final wallet/miner balances and tx counts
6. Confirmation that `FINAL REPORT` sections were emitted in `/tmp/surge_test.log`

---

**Related reports:**
- `TESTREPORT-2026-04-10-CHAIN-FINAL.md`
- `TESTREPORT-2026-04-09-SUSTAINED-GHOSTDAG.md`
- `TESTREPORT-2026-04-09-MAX-TPS.md`
- `TESTREPORT-2026-04-09-STRESS.md`
