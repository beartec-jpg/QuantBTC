# QuantumBTC Testnet v2 — 10-Second Block Migration Report

**Date:** April 9, 2026
**Chain:** `qbtctestnet` (GHOSTDAG K=32, 10-second block targets)
**Network:** 3 seed nodes (S1, S2, S3)
**Commits:** `8264fa0` (1s difficulty regulation) → `1f9a422` (10s block migration)
**Outcome:** Successful migration from 1-second to 10-second blocks with updated tokenomics

---

## 1. Executive Summary

The original QuantumBTC testnet (v1) ran 1-second blocks for extended operation. While functionally correct, real-world analysis revealed that 1-second blocks with PQC signatures (20× larger than ECDSA) created unsustainable storage, bandwidth, and IBD (Initial Block Download) costs. The network was migrated to 10-second blocks — a middle ground that preserves DAG utility while keeping infrastructure costs manageable.

---

## 2. Original Testnet v1 — Issues Discovered

### 2.1 Memory & UTXO Growth (Chain Height ~10,600)

After ~3 hours of continuous operation with 3 miners and traffic simulation:

| Metric | Value | Concern |
|--------|-------|---------|
| Blocks produced | ~10,600 | 31.5M blocks/year projected |
| UTXO set size | 35,256 outputs | Growing ~200/min from mining |
| Node 1 UTXOs | 6,684 | Fragmented from 1-block-per-second coinbases |
| Coinbase UTXO value | ~0.083 QBTC each | Too small for efficient consolidation |
| Disk growth rate | ~1.5 GB/day (light traffic) | 533 GB/year minimum |
| Debug log growth | ~2 GB/day | Before log pruning fixes |

### 2.2 UTXO Consolidation Failure

Mining at 1 block/second created ~3,600 tiny coinbase UTXOs per hour per miner. Consolidating these hit fundamental limits:

- **PQC witness size**: 3,836 bytes per input means a consolidation tx with 20 inputs weighs ~76,720 bytes
- **CLI argument limit**: Signed PQC transactions exceeded the OS 128KB argument length limit, crashing `sendrawtransaction` via subprocess
- **Net UTXO growth**: Even with aggressive consolidation (10 rounds × 20 inputs per mining cycle), the system barely kept pace

**Solution applied (v1):** Python JSON-RPC consolidation bypassing the CLI entirely — reduced UTXOs from 6,684 to ~10 in 35 minutes.

### 2.3 PQC Bandwidth & Storage Analysis

Measured from the live v1 chain:

| Metric | Value |
|--------|-------|
| Avg block size (light traffic) | 16,910 bytes |
| Avg tx-bearing block size | 238,091 bytes |
| Single PQC tx (2-in/2-out) | 7,846 bytes (97% witness data) |
| PQC size multiplier vs Bitcoin | 20.2× |
| Bandwidth at full blocks | 326 GB/day (119 TB/year) |
| IBD: 1 year of chain @100Mbps | ~12 hours |
| IBD: blocks to process per year | 31.5 million (38× Bitcoin's entire 16-year history) |

### 2.4 DAG Utilization at 1-Second Blocks

Despite 1-second block targets, the DAG was in use:

| Metric | Value |
|--------|-------|
| Height / Blue score ratio | 1.423 |
| Parallel blocks (not on selected-parent chain) | 29.7% |
| Blocks with >1 parent (last 1000) | 5.1% |
| Max parents observed on single block | 3 |
| Mergeset reds (orphaned blocks) | 0 |

With only 3 miners, ~30% of blocks were produced in parallel — the DAG was functional but the collision rate was artificially high due to fast blocks, not miner count.

---

## 3. Block Time Analysis

The core question: what block time balances DAG utility against PQC storage costs?

### 3.1 Collision Rate Model

Block collisions (parallel blocks) occur when a miner finds a block during the propagation delay window. The collision rate depends on `propagation_delay / block_time`, not on the number of miners:

| Block Time | Propagation / Block Time | Collision Rate (100 miners) | DAG Parallel % |
|-----------|--------------------------|----------------------------|----------------|
| 1s | 50% | Very high | ~95%+ |
| 5s | 10% | High | ~60% |
| **10s** | **5%** | **Moderate** | **~40%** |
| 30s | 1.7% | Low | ~12% |
| 60s | 0.8% | Very low | ~3% |
| 600s (BTC) | 0.08% | Near zero | ~0.3% |

### 3.2 Storage & IBD Projections

| Block Time | Blocks/Year | IBD (1yr light, @100Mbps) | Confirmation Time |
|-----------|-------------|--------------------------|-------------------|
| 1s | 31.5M | ~12 hours | ~3s |
| **10s** | **3.15M** | **~1.2 hours** | **~30s** |
| 60s | 525K | ~12 min | ~3 min |
| 600s | 52.6K | ~1 min | ~30 min |

### 3.3 Decision: 10-Second Blocks

10 seconds was chosen because:

1. **DAG matters**: With 100+ miners, ~40% of blocks would be parallel — real throughput gains from the DAG
2. **IBD manageable**: Syncing 1 year takes ~1.2h @100Mbps (vs 12h at 1s)
3. **60× faster than Bitcoin**: 30-second confirmations vs 30 minutes
4. **PQC bloat tolerable**: Full-block bandwidth ~32 GB/day (vs 326 GB/day at 1s)
5. **Proven ground**: Similar to Ethereum's ~13s block time that ran successfully for 7 years

---

## 4. Consensus Changes Applied

### 4.1 Chain Parameters (commit `1f9a422`)

| Parameter | v1 (1-second) | v2 (10-second) | Rationale |
|-----------|---------------|----------------|-----------|
| `nPowTargetSpacing` | 1 | 10 | 10-second block target |
| `nDagTargetSpacingMs` | 1000 | 10000 | DAG target in milliseconds |
| `nPowTargetTimespan` | 128 | 1280 | 128-block window × 10s |
| `nSubsidyHalvingInterval` | 126,000,000 | 12,600,000 | ~4-year halving preserved |
| `DAG_INITIAL_BLOCK_REWARD` | 8,333,333 sat | 83,333,333 sat | 50 BTC / 60 (not /600) |

### 4.2 Unchanged Parameters

| Parameter | Value | Notes |
|-----------|-------|-------|
| `ghostdag_k` | 32 | Same DAG width tolerance |
| `nDagDiffWindowSize` | 128 | ~21 min at 10s (was ~2 min at 1s) |
| `nMaxDagParents` | 64 | Same max parent references |
| `nMaxBlockWeightPQC` | 16 MW | Same PQC block weight limit |
| Genesis block | Unchanged | Same nonce, nBits, hash |
| Total supply | ~21,000,000 QBTC | Preserved exactly |
| PQC deployment | Always active | No change |

### 4.3 Tokenomics Comparison

| Parameter | Bitcoin | QBTC v1 (1s) | QBTC v2 (10s) |
|-----------|---------|-------------|---------------|
| Block interval | 600s | 1s | 10s |
| Block reward | 50 BTC | 0.0833 QBTC | 0.8333 QBTC |
| Reward (satoshis/qSats) | 5,000,000,000 | 8,333,333 | 83,333,333 |
| Halving interval | 210,000 | 126,000,000 | 12,600,000 |
| Halving period | ~4 years | ~4 years | ~4 years |
| Total supply | ~21M BTC | ~21M QBTC | ~21M QBTC |
| Phase 1 emission | 50% | 50% | 50% |
| Blocks/year | 52,560 | 31,536,000 | 3,153,600 |

The smallest unit of QBTC (1 satoshi = 0.00000001 QBTC) is referred to as a **qSat** in QBTC documentation.

---

## 5. Migration Procedure

### 5.1 Steps Performed

1. Updated `src/kernel/chainparams.cpp` — all timing and reward parameters
2. Updated `src/validation.cpp` — `DAG_INITIAL_BLOCK_REWARD` from 8,333,333 to 83,333,333
3. Built on all 3 nodes (incremental rebuild, ~2 minutes each)
4. Stopped all daemons, killed miners and traffic simulators
5. Wiped chain data (`blocks/`, `chainstate/`, `peers.dat`) on all 3 nodes
6. Restarted fresh — genesis block accepted (hash unchanged)
7. Started throttled miners on all 3 nodes
8. Waited for difficulty convergence (~4 retarget windows)

### 5.2 Difficulty Convergence

The first 128 blocks mine at minimum difficulty (1-second pace). The difficulty retarget algorithm adjusts by up to 4× per window (128 blocks), converging to the 10-second target:

| Window | Blocks | Avg Block Time | Notes |
|--------|--------|----------------|-------|
| 0–127 | 128 | ~1s | Minimum difficulty bootstrap |
| 128–255 | 128 | ~1s | First retarget: 4× harder |
| 256–383 | 128 | ~2s | Second retarget: 4× harder |
| 384–511 | 128 | ~5.8s | Third retarget: approaching target |
| 512+ | ongoing | **~7–10s** | **Converging to 10s target** |

### 5.3 Post-Migration Status (Block 535)

| Metric | Value |
|--------|-------|
| Height | 535 |
| Average block time (last 20) | 7.0 seconds |
| Min / Max interval | 4s / 12s |
| Difficulty | 0.00824 |
| Connections per node | 4 |
| Block reward | 0.83333333 QBTC |
| Miners active | 3 |

---

## 6. Projected Network Characteristics (10-Second Blocks)

### 6.1 Storage & Bandwidth

| Scenario | Daily | Yearly |
|----------|-------|--------|
| Light (current, ~1 tx/block) | 146 MB/day | 53 GB/year |
| Moderate (5 tx, 50% of blocks) | 170 MB/day | 62 GB/year |
| Full blocks (481 tx/block) | 32 GB/day | 11.9 TB/year |
| Bitcoin (for comparison) | 220 MB/day | 79 GB/year |

### 6.2 IBD Projections

| Duration | Blocks | Size (light) | Sync @100Mbps | Sync @10Mbps |
|----------|--------|-------------|--------------|-------------|
| 1 year | 3.15M | 53 GB | 1.2 hours | 12 hours |
| 4 years | 12.6M | 212 GB | 4.7 hours | 2 days |
| Bitcoin (16 years) | 840K | ~600 GB | 6–24 hours | 2–10 days |

### 6.3 DAG Utilization Projections

| Miner Count | Est. Collision Rate | Parallel Block % | DAG Value |
|-------------|--------------------|--------------------|-----------|
| 3 (current) | ~1.5% | ~2% | Minimal |
| 10 | ~5% | ~8% | Noticeable |
| 50 | ~24% | ~30% | Significant |
| 100 | ~40% | ~45% | High |
| 500+ | ~75%+ | ~80%+ | Very high |

---

## 7. Sustainability Fixes Applied (v1 → v2)

These fixes were applied during v1 operation and carried forward:

| Fix | Problem | Solution |
|-----|---------|----------|
| Log reduction | Debug logs growing 2 GB/day | Removed `debug=net`, `debug=validation`; added `shrinkdebugfile=1` |
| Pruning | Disk filling in ~17 days | Enabled `prune=10000` (10 GB) |
| Memory caps | Unbounded cache growth | `dbcache=150`, `maxmempool=300` |
| UTXO consolidation | Mining fragments UTXOs | JSON-RPC consolidation in miner script |
| jemalloc | glibc fragmentation under churn | Built with `--with-jemalloc` |
| m_known_scores | DAG tip scores growing 82 MB/day | Pruned entries >1000 behind best tip |
| Mergeset pruning | Vectors never freed | Cleared for blocks >1000 deep |
| PQC sig cache | Redundant Dilithium verification | CuckooCache integration |

---

## 8. Files Changed

| File | Changes |
|------|---------|
| `src/kernel/chainparams.cpp` | Block time, reward interval, DAG spacing, comments |
| `src/validation.cpp` | `DAG_INITIAL_BLOCK_REWARD`: 8,333,333 → 83,333,333 |

**Commit:** `1f9a422` — "consensus: switch qbtctestnet to 10-second blocks"

---

## 9. Conclusion

The migration to 10-second blocks resolves the primary scalability concerns of the 1-second chain while preserving the QBTC value proposition:

- **21M supply cap maintained** — identical emission schedule, just larger per-block rewards with fewer blocks
- **DAG remains meaningful** — at 10s with 100+ miners, ~40% of blocks are parallel
- **60× faster than Bitcoin** — 30-second confirmations vs 30 minutes
- **IBD practical** — 1.2 hours to sync 1 year vs 12 hours at 1-second blocks
- **PQC overhead manageable** — 32 GB/day at full blocks vs 326 GB/day

The 10-second block time is comparable to Ethereum's proven 13-second block time and represents the optimal balance between speed, DAG utility, and PQC storage overhead.

---

*QuantumBTC — Quantum-safe BlockDAG for a post-quantum world*
