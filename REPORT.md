<!-- Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; then MIT. See LICENSE-BUSL and NOTICE. -->
# QuantumBTC — Project Report & Additions Documentation

**Date:** April 9, 2026
**Repository:** [QBlockQ/pqc-bitcoin](https://github.com/QBlockQ/pqc-bitcoin) (branch: `main`)
**Base:** Bitcoin Core v28.0.0 fork
**Latest commit:** `1f9a422`
**Total commits:** 145

---

## 1. Project Overview

QuantumBTC (QBTC) is a Bitcoin Core v28.0.0 fork that adds:
- **Post-Quantum Cryptography (PQC)** — ML-DSA-44 (Dilithium2) hybrid signatures
- **BlockDAG with GHOSTDAG** — parallel block production with K=32
- **10-second block targets** — high-throughput DAG-mode consensus (60× faster than Bitcoin)
- **Custom testnet** — 3-node live network (v2, migrated from 1s to 10s blocks April 9, 2026)

---

## 2. Architecture Additions

### 2.1 Post-Quantum Cryptography (PQC)

| Component | Location | Description |
|-----------|----------|-------------|
| ML-DSA-44 (Dilithium2) | `src/crypto/pqc/ml-dsa/` | Vendored pq-crystals reference implementation (deterministic signing) |
| SPHINCS+ (SLH-DSA) | `src/crypto/pqc/sphincsplus/` | Vendored reference implementation |
| ML-KEM-768 (Kyber) | `src/crypto/pqc/kyber.cpp/h` | Key encapsulation via liboqs |
| NTRU | `src/crypto/pqc/ntru.cpp/h` | With IND-CCA2 Fujisaki-Okamoto transform |
| FrodoKEM | `src/crypto/pqc/frodokem.cpp/h` | With IND-CCA2 FO transform |
| PQC Validation | `src/consensus/pqc_validation.h/cpp` | Consensus-level PQC witness verification |
| PQC Config | `src/crypto/pqc/pqc_config.h/cpp` | Hybrid signature mode configuration |
| Dilithium wrapper | `src/crypto/pqc/dilithium.cpp/h` | High-level keygen/sign/verify API |

**Hybrid Witness Format (P2WPKH):**
```
[ecdsa_sig, ecpubkey, pqc_sig(2420 bytes), pqc_pubkey(1312 bytes)]
```
- 4-element witness stack detected automatically
- PQC verification runs at both mempool acceptance and block connection
- BIP9 deployment bit 3 (`DEPLOYMENT_PQC`), `ALWAYS_ACTIVE` on regtest/qbtcmain
- Script flag: `SCRIPT_VERIFY_PQC` (1U << 21)

**Key Storage:**
- Wallet DB prefix: `walletdescriptorpqckey` keyed by `(desc_id, ecpubkey)`
- ~8000 Dilithium keypairs generated per wallet (8 descriptors × 1000 keys)
- Deterministic key derivation from 32-byte seeds

### 2.2 BlockDAG / GHOSTDAG

| Component | Location | Description |
|-----------|----------|-------------|
| GHOSTDAG engine | `src/dag/ghostdag.cpp/h` | Blue/red set computation, blue_score, selected_parent |
| DAG Tipset | `src/dag/dagtipset.cpp/h` | Tip tracking, mining parent selection (up to 64 parents) |
| Block index ext | `src/dag/ghostdag_blockindex.h` | Per-block DAG metadata (blue_score, mergeset, parents) |

**Consensus Parameters:**

| Parameter | qbtctestnet | qbtcmain | regtest |
|-----------|-------------|----------|---------|
| `ghostdag_k` | 32 | 32 | 32 |
| `nMaxDagParents` | 64 | 64 | 32 |
| `fDagMode` | true | true | false |
| Block target | 10 seconds | 10 seconds | — |
| Halving interval | 12,600,000 | 12,600,000 | 150 |
| Block reward | 0.83333333 QBTC | 0.83333333 QBTC | 50 QBTC |

**DAG Header Extension:**
- `hashParents` vector in `CBlockHeader` — additional parent references beyond `hashPrevBlock`
- Serialized after the standard 80-byte header
- `GetHash()` uses only the canonical 80 bytes (hash-identity invariant)
- `nVersion` bit 0x10000000 signals DAG mode

**DAG Tipset Tracking:**
- Lives in `AcceptBlock()` (not `ConnectTip()`) — tracks ALL accepted blocks including fork branches
- `DagTipSet::BlockConnected` removes parents from tip set, adds new block
- `GetMiningParents()` returns tips sorted by blue_score descending
- Known scores pruned at depth 1000

### 2.3 Early Protection System

- Anti-spam block weight management during network bootstrap
- Activation threshold, throttle factor, ramp-up period
- Per-peer block weight tracking with IP-based identification

### 2.4 Chain Parameters

| Chain | P2P Port | RPC Port | Address Prefix | Magic Bytes |
|-------|----------|----------|----------------|-------------|
| `qbtctestnet` | 28333 | 28332 | `qbtct1` | custom |
| `qbtcmain` | 58333 | 58332 | `qbtc1` | custom |
| `regtest` | 18444 | 18443 | `qbtcrt1` | standard |

---

## 3. Modified Bitcoin Core Files

Key files with PQC/DAG integration points:

| File | Changes |
|------|---------|
| `src/consensus/params.h` | Added `ghostdag_k`, `nMaxDagParents`, `fDagMode`, `DEPLOYMENT_PQC`, PQC weight limits |
| `src/kernel/chainparams.cpp` | Added `CQBTCTestNetParams`, `CQBTCMainParams` chain classes |
| `src/validation.cpp` | DAG parent validation, GHOSTDAG scoring, tipset updates, PQC flag wiring |
| `src/validation.h` | DAG-related validation interfaces |
| `src/node/miner.cpp` | DAG parent selection from tipset, version flag setting |
| `src/primitives/block.h/cpp` | `hashParents` vector, DAG serialization, 80-byte `GetHash()` invariant |
| `src/chain.h/cpp` | Block index DAG metadata, `BuildSkip` guards for stub entries |
| `src/node/blockstorage.cpp` | DAG parent persistence, IBD parent handling |
| `src/rpc/blockchain.cpp` | `dagparents`, `dagblock`, `blue_score` RPC fields, `getpqcinfo`, `getpqcsigcachestats` |
| `src/script/interpreter.cpp` | 4-element PQC witness detection, unconditional PQC verification |
| `src/script/sign.cpp` | Hybrid ECDSA+Dilithium signing, `CreatePQCSig` |
| `src/wallet/scriptpubkeyman.cpp` | PQC key generation in `TopUpWithDB`, wallet DB storage |

---

## 4. New RPC Commands

| RPC | Description |
|-----|-------------|
| `getpqcinfo` | Returns PQC status: enabled, mode, algorithm, key counts per wallet |
| `getpqcsigcachestats` | Returns signature cache hit/miss stats (ECDSA + Dilithium) |
| `getblockheader` (extended) | Added `dagparents` (array) and `dagblock` (bool) fields |
| `getblock` (extended) | Same DAG fields as `getblockheader` |

---

## 5. Test Scripts

### 5.1 Stability Tests (Regtest — All Passing)

| Script | Tests | Result | Description |
|--------|-------|--------|-------------|
| `test_kill9_recovery.sh` | 10 | **10/10 PASS** | SIGKILL crash recovery with `-reindex`, double-crash, post-crash mining |
| `test_restart_10k.sh` | 9 | **9/9 PASS** | Mine 10k blocks, graceful stop, restart, verify chain/tip/hash identity |
| `test_ibd_genesis.sh` | 14 | **14/14 PASS** | 2-node IBD sync (2000 blocks), chain identity, spot-check 5 random blocks |

**Key fixes applied to test scripts:**
- `debug=dag` → `debug=validation` (no "dag" logging category exists)
- Added `wait_for_reindex()` — polls height until stable after `-reindex`
- `-bind=127.0.0.1:PORT` instead of `-port=PORT` (avoids default port 18445 conflict)
- `addnode=` moved into `[regtest]` config section
- `grep -ci || echo 0` → `grep -i | wc -l` (bash arithmetic bug fix)
- Blue score persistence is a warning, not a failure (DAG metadata doesn't persist across restart)

### 5.2 Network/DAG Test Scripts (Python)

| Script | Description |
|--------|-------------|
| `test_dag_fork.py` / `v3` / `live` | DAG fork handling and resolution |
| `test_dag_wallet.py` | Wallet operations under DAG mode |
| `test_dag_testnet.py` | Testnet connectivity and chain validation |
| `test_ghostdag.py` / `polish` | GHOSTDAG scoring and ordering |
| `test_multinode.py` | Multi-node sync and consensus |
| `test_parallel_dag.py` / `dag2` | Parallel block production |
| `test_1000tx.py` | 1000-transaction load test |
| `test_10node_10k.py` | 10-node, 10k-block stress test |
| `run_ghostdag_test.py` / `v2` / `sh` | GHOSTDAG test runners |
| `run_full_test.sh` | Full test suite runner |

---

## 6. Live Testnet Status

### 6.1 Network Health (as of April 5, 2026)

| Server | IP | Height | Peers | Balance (QBTC) |
|--------|-----|--------|-------|-----------------|
| S1 (seed) | 46.62.156.169 | 96,637 | 3 | 1,563.98 |
| S2 (seed) | 37.27.47.236 | 96,654 | 4 | 1,937.28 |
| S3 (verify) | 89.167.109.241 | 96,654 | 3 | 1,903.29 |

- **Total supply mined:** ~8,050 QBTC
- **Total transactions:** ~134,900
- **Chain size on disk:** ~1,341 MB
- **Transaction rate:** ~7.2 tx/s
- **Mining:** 3 miners with `sleep 10` between rounds
- **TX traffic:** Recurring generators (S1: 0.01/0.5s, S2: 0.025/1s, S3: 0.05/2s)

### 6.2 UTXO Consolidation (Completed)

All 3 servers had extreme UTXO fragmentation from continuous mining:
- S1: 25,401 → 12 UTXOs
- S2: 25,885 → ~10 UTXOs
- S3: 24,279 → ~10 UTXOs

Consolidation used batched `createrawtransaction` with `-stdin` flag to avoid `ARG_MAX` limits from large PQC witnesses.

---

## 7. Infrastructure

### 7.1 QBTCScan Block Explorer
- **URL:** [beartec.uk/qbtc-scan](https://beartec.uk/qbtc-scan)
- Live dashboard: blocks, difficulty, hash rate, mempool, peers, DAG tips
- Search by txid, block hash/height, or address
- Shows PQC status, DAG mode, node version

### 7.2 Testnet Faucet
- **URL:** [beartec.uk/qbtc-faucet](https://beartec.uk/qbtc-faucet)
- **Amount:** 0.5 QBTC per claim
- **Rate limit:** 1 claim per hour per IP
- **Backend:** RPC `sendtoaddress` via S1's `miner` wallet (1,626 QBTC available)
- **Status:** Operational (verified via API)

### 7.3 Contrib Tools
- `contrib/beartec-wallet/qbtc_wallet.py` — Python wallet library
- `contrib/qbtc-testnet/` — Testnet config and startup scripts

---

## 8. Documentation

| Document | Description |
|----------|-------------|
| `README.md` | Project overview, build instructions, testing guide |
| `ROADMAP.md` | Development roadmap with build history and network stats |
| `SECURITY.md` | Security policy, PQC threat model |
| `CONTRIBUTING.md` | Contribution guidelines |
| `INSTALL.md` | Build and installation instructions |
| `doc/ghostdag.md` | GHOSTDAG consensus documentation and parameters |
| `TODO.md` | Tracking checklist for remaining items |

---

## 9. Key Bug Fixes

| Issue | Root Cause | Fix | Commit |
|-------|-----------|-----|--------|
| Block hash drift across restarts | DAG parents included in hash computation | `GetHash()` uses only canonical 80 bytes | `74ab011` |
| DAG sync failures (5 cascading bugs) | Missing parents during IBD, stub block index entries | Guard `BuildSkip`, handle broken `pprev` chain, skip PoW for DAG | `c9e53ed`..`01e7310` |
| `bad-cb-height` rejection | `CScript() << height` uses `OP_N` for heights 1-16 | Correct coinbase height encoding | (early commits) |
| Tipset not tracking fork blocks | `ConnectTip()` only fires for active chain | Moved to `AcceptBlock()` which fires for all blocks | (DAG wiring) |
| `MAX_BLOCK_PARENTS` mismatch | Constant was 32, consensus param was 64 | Raised constant to 64 | `0c319ed` |
| Kill-9 loses all blocks (regtest) | LevelDB block index never flushed for small blocks | Use `-reindex` on crash recovery | `b707f87` |
| Segfaults after PQC class changes | Stale `.o` files with old class layout | `make clean` rebuild required | (build process) |
| `debug=dag` invalid category | No "dag" logging category exists | Changed to `debug=validation` | `b707f87` |

---

## 10. Source File Inventory

### New directories (112 source files):
```
src/dag/                    — GHOSTDAG engine, DAG tipset, block index extensions
src/crypto/pqc/             — All PQC algorithm implementations
  ml-dsa/                   — Vendored Dilithium2 reference (ML-DSA-44)
  sphincsplus/              — Vendored SPHINCS+ reference (SLH-DSA)
  kyber.cpp/h               — ML-KEM-768 via liboqs
  ntru.cpp/h                — NTRU with FO transform
  frodokem.cpp/h            — FrodoKEM with FO transform
  dilithium.cpp/h           — High-level Dilithium API
  pqc_config.cpp/h          — PQC mode configuration
  sqisign.cpp/h             — SQIsign stub (disabled)
  falcon.h                  — Falcon stub (disabled)
src/consensus/pqc_validation.h/cpp — PQC consensus verification
```

### Test scripts: 18 files
### Documentation: 6 files
### Contrib: 2 directories with configs and tools
