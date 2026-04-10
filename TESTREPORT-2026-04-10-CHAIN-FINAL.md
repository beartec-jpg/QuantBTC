# QuantumBTC Testnet Chain Report — Pre-Wipe Snapshot

**Date:** 2026-04-10 09:50 UTC  
**Version:** QuantumBTC v28.0.0 (pre-security-patch binary)  
**Chain:** qbtctestnet | GHOSTDAG K=32 | PQC: ALWAYS_ACTIVE  
**Reason for Wipe:** Consensus rule changes (hybrid addresses, HYBRID_SIG enforcement) break backward compatibility. Fresh genesis required.

---

## Network Topology

| Server | Hostname | IP | Hetzner ID | Type |
|--------|----------|----|------------|------|
| Node 1 | ubuntu-4gb-hel1-4 | 89.167.109.241 | #125858970 | CX23 (4GB) |
| Node 2 | ubuntu-4gb-hel1-2 | 46.62.156.169 | #125815914 | CX23 (4GB) |
| Node 3 | ubuntu-4gb-hel1-3 | 37.27.47.236 | #125815915 | CX23 (4GB) |

All nodes peered in full mesh (4 connections each). Running `/QuantumBTC:28.0.0/` protocol version 70016.

---

## Chain Summary

| Metric | Value |
|--------|-------|
| **Final Height** | 7,484 |
| **Chain Duration** | 71,771 seconds (~19.9 hours active mining) |
| **Genesis Time** | 2026-03-30 00:00:00 UTC (epoch 1743379200) |
| **Final Block Time** | 2026-04-10 09:49:31 UTC (epoch 1775814571) |
| **Total Difficulty** | 0.01038 |
| **Chainwork** | 0x496a760ea1 |
| **Data on Disk** | 597 MB (node 1), 656 MB (node 2), 605 MB (node 3) |
| **DAG Tips (final)** | 2–3 across nodes |
| **Pruning** | Enabled (10 GB target) |

---

## Transaction Volume

| Metric | Value |
|--------|-------|
| **Total Wallet Txcount (all 21 wallets, node 1)** | **191,158** |
| **TPS (last 100 blocks)** | **4.35 tx/s** |
| **Last 100 blocks tx count** | 4,809 txs in 1,105 seconds |
| **Mempool at snapshot** | 58 txs (node 1), 45 (node 2), 20 (node 3) |
| **Average block tx count (last 5)** | ~52 txs/block |

### Block Timing Milestones

| Height | Timestamp (UTC) | Elapsed (from H100) | Blocks/hr |
|--------|-----------------|---------------------|-----------|
| 0 | 2026-03-30 00:00:00 | — (genesis, pre-mine) | — |
| 100 | 2026-04-09 14:00:11 | 0 (mining start) | — |
| 1,000 | 2026-04-09 15:38:48 | 5,917s | ~548 |
| 2,000 | 2026-04-09 18:29:45 | 16,174s | ~353 |
| 3,000 | 2026-04-09 21:20:02 | 26,391s | ~341 |
| 4,000 | 2026-04-10 00:01:35 | 36,084s | ~373 |
| 5,000 | 2026-04-10 02:56:24 | 46,573s | ~381 |
| 6,000 | 2026-04-10 05:45:06 | 56,695s | ~356 |
| 7,000 | 2026-04-10 08:32:48 | 66,757s | ~356 |
| 7,484 | 2026-04-10 09:49:31 | 71,760s | ~359 |

**Sustained block rate: ~350-380 blocks/hour (~6 blocks/min, ~10s avg block time)**

---

## Wallet Activity

### Test Wallets (8)

| Wallet | Balance (QBTC) | Tx Count |
|--------|---------------|----------|
| txtest_1 | 2.88 | 467 |
| txtest_2 | 2.82 | 496 |
| txtest_3 | 2.71 | 448 |
| txtest_4 | 1.97 | 479 |
| txtest_5 | 3.60 | 412 |
| txtest_6 | 4.16 | 449 |
| txtest_7 | 3.83 | 523 |
| txtest_8 | 3.65 | 476 |
| **Subtotal** | **25.62** | **3,750** |

### Surge Wallets (12)

| Wallet | Balance (QBTC) | Tx Count |
|--------|---------------|----------|
| surge_w1 | 4.22 | 15,369 |
| surge_w2 | 9.05 | 15,519 |
| surge_w3 | 4.63 | 15,045 |
| surge_w4 | 3.05 | 15,296 |
| surge_w5 | 10.18 | 15,059 |
| surge_w6 | 13.64 | 15,239 |
| surge_w7 | 18.59 | 15,425 |
| surge_w8 | 3.71 | 15,335 |
| surge_w9 | 6.46 | 15,281 |
| surge_w10 | 9.13 | 15,388 |
| surge_w11 | 6.74 | 15,495 |
| surge_w12 | 11.09 | 15,325 |
| **Subtotal** | **100.49** | **183,776** |

### Miner Wallet

| Wallet | Balance (QBTC) | Immature (QBTC) | Tx Count |
|--------|---------------|-----------------|----------|
| miner | 379.03 | 31.12 | 3,400 |

**Total supply mined: ~510 QBTC** (379 + 100.5 + 25.6 + 31.1 immature — approximate, includes fees)

---

## Active Processes at Snapshot

| Server | Process | Details |
|--------|---------|---------|
| Node 1 | `bitcoind` | Running 12.8 hrs, 44.6% RAM (1.7 GB) |
| Node 1 | `mine_v4.sh` | Mining every 5s, consolidate every 30 blocks |
| Node 1 | `traffic_sim_v3.py` | 3-node cross-traffic, 20s interval, 0.0005 QBTC amounts |
| Node 2 | `bitcoind` | Running 12.6 hrs |
| Node 3 | `bitcoind` | Running 12.2 hrs |

---

## Configuration (all nodes)

```ini
chain=qbtctestnet
[qbtctestnet]
listen=1
port=28333
maxconnections=125
server=1
rpcport=28332
rpcworkqueue=64
dbcache=150
maxsigcachesize=32
maxmempool=300
prune=10000
fallbackfee=0.0001
```

---

## Sample Blocks (final 5)

| Height | Txs | Timestamp | Parents |
|--------|-----|-----------|---------|
| 7,474 | 90 | 09:47:45 | 1 |
| 7,475 | 118 | 09:48:12 | 1 |
| 7,476 | 9 | 09:48:14 | 1 |
| 7,477 | 31 | 09:48:21 | 1 |
| 7,478 | 11 | 09:48:25 | 1 |

---

## Node Health

| Metric | Node 1 | Node 2 | Node 3 |
|--------|--------|--------|--------|
| Uptime (s) | 46,152 | 45,254 | 44,081 |
| Height | 7,482 | 7,434 | 7,435 |
| Peers | 4 | 4 | 4 |
| Mempool txs | 58 | 45 | 20 |
| Warnings | versionbit 28 | versionbit 28 | versionbit 28 |
| Disk used | 3.3 GB | 3.7 GB | 3.3 GB |

---

## Reason for Chain Reset

The following consensus-breaking changes require a fresh genesis:

1. **Hybrid Addresses** — Wallet now generates `Hash160(ecdsa_pk || pqc_pk)` witness programs instead of `Hash160(ecdsa_pk)`. Old UTXOs have incompatible witness programs.

2. **SCRIPT_VERIFY_HYBRID_SIG Enforcement** — New consensus rule requires 4-element PQC witness for all P2WPKH spends. All existing 2-element ECDSA-only transactions on the old chain would be invalid.

3. **PQC Signature Cache** — New `ComputeEntryDilithiumRaw()` with `'D'` domain separator changes cache behavior.

4. **Genesis nBits** — Changed to `0x1d00ffff` (standard difficulty floor).

**All ~191,000 transactions on the old chain are ECDSA-only (2-element witnesses). None would validate under the new consensus rules.**

---

## Post-Wipe Plan

1. Stop all daemons and kill mining/traffic scripts
2. Delete `/root/.bitcoin/qbtctestnet/` chain data on all 3 servers
3. Pull patched code (commit `dd33a91`) and rebuild
4. Start fresh from genesis with new consensus rules
5. Recreate wallets and resume mining/traffic simulation
