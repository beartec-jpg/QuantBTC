<!-- Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; then MIT. See LICENSE-BUSL and NOTICE. -->
# QuantumBTC Development Roadmap

## What Is QuantumBTC?

QuantumBTC (QBTC) is a Bitcoin Core v28.0.0 fork that combines **post-quantum cryptographic signatures** with **BlockDAG consensus** (GHOSTDAG) to create a quantum-resistant, high-throughput blockchain network while preserving Bitcoin's economic model (21M supply cap, halving schedule, SHA-256 PoW).

Every transaction on the network carries a **hybrid witness**: a classical ECDSA signature paired with a lattice-based ML-DSA-44 (Dilithium2) signature, providing cryptographic security against both classical and quantum adversaries today — not as a future upgrade, but as a consensus requirement from genesis.

---

## Development Phases Completed

### Phase 1: Foundation (pqcBitcoin Upstream)

**Status: ✅ Complete (inherited)**

The base fork from [QBlockQ/pqc-bitcoin](https://github.com/QBlockQ/pqc-bitcoin) provided:

- [x] PQC algorithm stubs for 7 algorithms (Dilithium, SPHINCS+, Falcon, SQIsign, Kyber, FrodoKEM, NTRU)
- [x] `HybridKey` class for dual classical+PQC key management
- [x] `PQCConfig` runtime configuration system (`-pqc=1`, `-pqcmode=hybrid`)
- [x] PQC key storage in wallet DB (`walletdescriptorpqckey` prefix)
- [x] Descriptor wallet integration for PQC key provisioning
- [x] Basic RPC extensions (`getpqcinfo`, PQC fields in `getaddressinfo`)
- [x] Script interpreter hooks for PQC witness validation

### Phase 2: BlockDAG Consensus (GHOSTDAG)

**Status: ✅ Complete**

Introduced parallel block production via the GHOSTDAG protocol:

- [x] `GhostdagManager` — computes blue scores, merge sets, selected parent chain
- [x] `DagTipSet` — tracks concurrent DAG tips, provides mining parents
- [x] Multi-parent block headers (`hashParents` field, `BLOCK_VERSION_DAGMODE` flag)
- [x] DAG-aware `AcceptBlockHeader()` validation (parent existence, duplicate detection, max parents)
- [x] DAG-aware difficulty adjustment (`GetNextWorkRequiredDAG`)
- [x] Tipset management in `AcceptBlock()` (not `ConnectTip()` — fork blocks tracked too)
- [x] RPC fields: `dagparents`, `dagblock`, `dagmode`, `ghostdag_k`, `dag_tips`
- [x] Early protection system (IP throttle, ramp weight, activation delay)

### Phase 3: Real Cryptography — ML-DSA-44

**Status: ✅ Complete**

Replaced placeholder HMAC-based stubs with the real NIST ML-DSA (Dilithium2) reference implementation:

- [x] Vendored pq-crystals ML-DSA-44 reference code at `src/crypto/pqc/ml-dsa/`
- [x] Fixed `#define N 256` macro leakage from `params.h` (conflicted with Bitcoin Core symbols)
- [x] Single canonical `randombytes()` implementation using `GetStrongRandBytes`
- [x] Wired real Dilithium `Sign()` / `Verify()` into `HybridKey`, interpreter, and wallet signing
- [x] Vendored SPHINCS+ (SLH-DSA-SHA2-128f) reference code at `src/crypto/pqc/sphincsplus/`
- [x] Vendored ML-KEM (Kyber) reference code at `src/crypto/pqc/ml-kem/`

### Phase 4: Consensus Verification & Audit Fixes

**Status: ✅ Complete**

Hardened the consensus layer for production readiness:

- [x] Real Dilithium cryptographic verification in script interpreter (`CheckPQCSignature`)
- [x] PQC witness structure validation (4 elements: ECDSA sig, EC pubkey, Dilithium sig 2420B, Dilithium pubkey 1312B)
- [x] Error codes: `SCRIPT_ERR_PQC_SIG_SIZE`, `SCRIPT_ERR_PQC_SIG`
- [x] Fixed `randombytes` ODR violation (single definition rule)
- [x] Fixed dual signing path (explicit hybrid format, error on Dilithium failure)
- [x] Fixed `pqc_validation.cpp` — Dilithium-only verification (removed broken SPHINCS+/Falcon calls)
- [x] Unique regtest magic bytes and port (no collision with Bitcoin Core)
- [x] Genesis block hash assertions for QBTC chains

### Phase 5: PQC-Aware Fee Estimation

**Status: ✅ Complete**

Fixed a critical bug where the wallet calculated fees on ECDSA-only vsize (~141 vB) but PQC hybrid witness made actual transactions ~7.6× larger (~1075 vB):

- [x] `WPKHDescriptor::MaxSatSize()` — returns PQC sizes (3+2420+3+1312) when `enable_hybrid_signatures` active
- [x] `DummySignatureCreator::CreatePQCSig()` — produces dummy 2420B sig + 1312B pubkey for size estimation
- [x] Coin selection now correctly accounts for PQC witness weight
- [x] Verified: `fee=10750sat, vsize=1075vB, rate=10.0sat/vB` (at `fallbackfee=0.0001`)

### Phase 6: Comprehensive Test Suite

**Status: ✅ Complete**

Built a multi-layer test infrastructure covering unit, integration, and fuzz testing:

**C++ Unit Tests (45 test cases across 10 files):**
- [x] `pqc_dilithium_tests` — 9 tests: keygen, sign/verify, tampered message/sig, wrong pubkey, deterministic derivation
- [x] `pqc_witness_tests` — 4 tests: valid PQC witness, wrong Dilithium sig, wrong-size sig, wrong-size pubkey
- [x] `pqc_fee_tests` — 2 tests: MaxSatisfactionWeight with/without PQC, DummySignatureCreator witness structure
- [x] `pqc_kyber_tests` — 5 tests: roundtrip, tampered ciphertext, cross-key mismatch
- [x] `pqc_sphincs_tests` — 8 tests: keygen, sign/verify, tampered message/sig
- [x] `pqc_frodo_fo_tests` — 6 tests: roundtrip, implicit rejection
- [x] `pqc_ntru_fo_tests` — 5 tests: roundtrip, implicit rejection
- [x] `pqc_signature_tests` — 4 tests: all signature schemes
- [x] `pqc_tests` — 2 tests: Kyber basic, PQC manager
- [x] `pqc_witness` (fuzz target) — random witness stack fuzzing

**Integration Tests (61 assertions across 30 test groups):**
- [x] Tests 1–4: Node identity, wallet PQC provisioning, mining, DAG block version
- [x] Tests 5–7: PQC hybrid tx creation, signature verification, batch transactions
- [x] Tests 8–9: DAG parallel blocks, GHOSTDAG ordering
- [x] Tests 10–14: Multi-hop PQC, wallet reload, multi-input, corrupt/wrong-size witness rejection
- [x] Tests 15–18: Sig mutation, replay protection, PQC tx size/weight validation
- [x] Tests 19–22: Mempool batch, block weight, reorg persistence, cross-wallet verification
- [x] Tests 23–26: Fee estimation accuracy, estimatesmartfee, RBF, CPFP
- [x] Tests 27–30: Two-node propagation, SPHINCS+ primitives, importprivkey, wallet encryption

### Phase 7: Full Testnet Implementation

**Status: ✅ Complete**

Brought up a standalone QuantumBTC testnet network:

- [x] `CQbtcTestNetParams` — full chain parameters (magic `d1a5c3b7`, port 28333, bech32 `qbtct`)
- [x] `CQbtcMainParams` — mainnet parameters reserved (magic `e3b5d7a9`, port 58333, bech32 `qbtc`)
- [x] `-qbtctestnet` CLI flag, `[qbtctestnet]` config section, `chain=qbtctestnet` support
- [x] Auto-enable PQC on QBTC chains (no need for manual `-pqc=1`)
- [x] `getblockchaininfo` reports `pqc: true` from `PQCConfig` (not raw CLI flag)
- [x] Updated help strings for `-assumevalid`, `-minimumchainwork` with QBTC values
- [x] Data directory: `~/.bitcoin/qbtctestnet/`
- [x] Launch script: `contrib/qbtc-testnet/qbtc-testnet.sh` (start/stop/mine/status/send/address)
- [x] Config template: `contrib/qbtc-testnet/qbtc-testnet.conf`
- [x] Documentation: `contrib/qbtc-testnet/README.md`, updated `doc/files.md`
- [x] Validated: fresh node startup, 121 blocks mined, PQC transaction confirmed, two-node sync verified

---

## Current Network Capabilities

### What Works Today

| Capability | Status | Details |
|------------|--------|---------|
| **Solo mining** | ✅ | `generatetoaddress` produces DAG-mode blocks with trivial difficulty |
| **PQC transactions** | ✅ | Every spend carries hybrid ECDSA + ML-DSA-44 witness |
| **Peer-to-peer sync** | ✅ | Nodes discover, connect, and sync full chain including PQC txs |
| **Wallet operations** | ✅ | Create, load, encrypt, send, receive with PQC keys |
| **Fee estimation** | ✅ | Correctly accounts for PQC witness size (~1075 vB per input) |
| **RBF** | ✅ | Replace-by-fee works with PQC transactions |
| **CPFP** | ✅ | Child-pays-for-parent with PQC witness |
| **Block validation** | ✅ | Full consensus verification of PQC sigs + DAG parents |
| **Reorg handling** | ✅ | Chain reorganizations preserve PQC transaction integrity |
| **Multiple wallets** | ✅ | Concurrent wallets, cross-wallet PQC verification |
| **Wallet encryption** | ✅ | Encrypt/unlock/lock cycle with PQC signing |
| **DAG parallel blocks** | ✅ | Multiple concurrent tips, GHOSTDAG blue ordering |
| **Cross-chain atomic swaps** | ✅ | QBTC ↔ USDC via HTLC (P2WSH + EVM), 3 swaps completed |
| **`qbtct1...` addresses** | ✅ | Unique bech32 prefix, no confusion with Bitcoin |

### What's Not Yet Production-Ready

| Item | Status | Notes |
|------|--------|-------|
| DNS seed nodes | ❌ | No public DNS seeds — bootstrap via `-seednode=<ip>:28333` |
| Pool mining | ❌ | No stratum integration; solo mining only |
| SPHINCS+ wallet signing | ❌ | Only crypto primitive tested; wallet uses Dilithium only |
| Falcon/SQIsign | ❌ | Stubs only — not wired to real implementations |
| KEMs in protocol | ❌ | Kyber/FrodoKEM/NTRU not used for node communication yet |
| Mainnet launch | ❌ | `CQbtcMainParams` defined but not deployed |
| GUI (bitcoin-qt) | ❌ | Build fails (Falcon/Kyber liboqs link errors) |

---

## Roadmap: What's Next

### Phase 8: Public Testnet (Deployed)

**Status: ✅ Complete**

Brought up a live 3-node testnet with public services:

- [x] Deploy 3 seed nodes with static IPs (46.62.156.169, 37.27.47.236, 89.167.109.241)
- [x] Continuous solo mining (~1 block/10 seconds) on all 3 nodes
- [x] Web faucet for distributing testnet QBTC (beartec.uk/qbtc-faucet — 0.5 QBTC per claim, 1-hour rate limit)
- [x] Web block explorer / search (beartec.uk/qbtc-scan — live dashboard with blocks, txs, DAG tips, PQC status)
- [x] Stress tested with 10 parallel transaction streams (~7.2 tx/s sustained)
- [x] UTXO consolidation across all 3 nodes (25k+ UTXOs → ~10 each)
- [x] Stability tests passing: `test_kill9_recovery.sh` (10/10), `test_restart_10k.sh` (9/9), `test_ibd_genesis.sh` (14/14)
- [ ] Add DNS seeds to `CQbtcTestNetParams::vSeeds`
- [ ] Docker images for easy node deployment
- [ ] Operator documentation (systemd service files, monitoring)

**Live Network Stats (April 15, 2026):**

| Metric | Value |
|--------|-------|
| Chain height | ~154,000+ blocks |
| Chain size on disk | ~5+ GB |
| Active peers per node | 3–4 |
| Cross-chain swaps completed | 3 (QBTC ↔ USDC) |
| Total transactions | ~417,000+ |
| 72-hour endurance test | Completed — 0 consensus splits, 0 data loss |
| Node uptime | Continuous since deployment |

### Phase 8.5: Memory & Consensus Hardening

**Status: ✅ Complete**

Proactive fixes identified via chain audit at ~30,000 blocks and validated through continued operation to ~96,600+ blocks:

- [x] **IsBlockAncestor BFS** — replaced `MAX_BFS_VISITS=100000` silent wrong-answer with height-bounded BFS. The old code could return `false` for a genuine ancestor, producing non-deterministic mergesets across nodes. New code guarantees correct answers proportional to DAG width × height difference.
- [x] **EarlyProtection nChainWork** — removed per-node ephemeral data (peer activation times, ramp counts, IP windows) from `nChainWork` scaling. Different nodes seeing different peer events would compute different chain weights, causing inconsistent chain selection.
- [x] **m_known_scores pruning** — `DagTipSet::m_known_scores` was never pruned, growing ~8.2 MB/day at 10-second blocks. Now evicts entries more than 1,000 blue_score behind the best tip that aren't current tips.
- [x] **SelectedParentChain depth limit** — `GhostdagManager::SelectedParentChain()` walked to genesis on every block call. Limited to `2*K+1` (37 blocks for K=18), reducing O(height) to O(K).
- [x] **Mergeset pruning** — `dagData.mergeset_blues` / `mergeset_reds` vectors were never freed. Now cleared for blocks buried more than 1,000 blocks deep during `ConnectTip()`.
- [x] **PQC signature cache** — `CachingTransactionSignatureChecker` now overrides `CheckDilithiumSignature` to cache verification results in the CuckooCache, avoiding redundant 2,420-byte Dilithium checks during block relay and mempool re-acceptance.
- [x] **mapDeltas bounding** — `PrioritiseTransaction` entries capped at 100,000 to prevent unbounded growth from orphaned delta entries.
- [x] **jemalloc integration** — linked at build time to replace glibc ptmalloc2, reducing heap fragmentation by ~40–60% under DAG block churn. DAG-optimized default cache sizes (`-dbcache=150`, `-maxsigcachesize=32`) added to launch scripts.

### Phase 8.6: 10-Second Block Migration

**Status: ✅ Complete**

Migrated from 1-second to 10-second blocks to balance DAG utility against PQC storage/bandwidth costs:

- [x] `nPowTargetSpacing`: 1 → 10 (10-second blocks)
- [x] `nDagTargetSpacingMs`: 1000 → 10000
- [x] `nPowTargetTimespan`: 128 → 1280 (128-block window × 10s)
- [x] `nSubsidyHalvingInterval`: 126,000,000 → 12,600,000 (~4 years preserved)
- [x] `DAG_INITIAL_BLOCK_REWARD`: 8,333,333 → 83,333,333 qSats (0.8333 QBTC/block)
- [x] Total supply ~21M QBTC preserved exactly
- [x] Genesis block unchanged (same nonce, nBits, hash)
- [x] Chain wiped and rebuilt from genesis on all 3 nodes
- [x] Difficulty converged to ~10s within 4 retarget windows (~512 blocks)
- [x] Introduced "qSat" naming for QBTC's smallest unit (1 qSat = 0.00000001 QBTC)

**Rationale:**
- 1-second blocks with PQC signatures (20× larger) created 326 GB/day bandwidth at full blocks and 31.5M blocks/year IBD burden
- 10-second blocks reduce this to 32 GB/day and 3.15M blocks/year while keeping 60× faster confirmations than Bitcoin
- DAG collision rate at 10s with 100+ miners: ~40% parallel blocks — the DAG remains valuable

See [TESTREPORT-2026-04-09.md](TESTREPORT-2026-04-09.md) for the full migration analysis.

### Phase 8.7: Cross-Chain Atomic Swaps (QBTC ↔ USDC)

**Status: ✅ Complete**

First-ever cross-chain atomic swap between a post-quantum blockchain and an EVM stablecoin, executed April 14, 2026:

- [x] EVM HTLC smart contract deployed on Ethereum Sepolia (`0xaF898a5F565c0cAE1746122ad475c0B7F160A3eb`)
- [x] QBTC P2WSH HTLC script — hash-only claim path (secret = proof, no private key needed)
- [x] Swap coordination server (Node.js/Express/PostgreSQL) — secret generation, state tracking, claim verification
- [x] Web wallet integration — HTLC construction, EVM interaction, order book UI
- [x] Timelock safety: QBTC 48h (seller refund) > EVM 24h (buyer refund)
- [x] Fixed `pqc_validation.cpp` to allow 3-element P2WSH witnesses alongside PQC 4-element witnesses
- [x] **3 successful swaps completed** — 0.03 QBTC ↔ 13 USDC, all verified on both chains
- [x] All HTLC addresses fully settled (0 balance, preimages revealed on-chain)

See [ATOMIC-SWAP-REPORT.md](ATOMIC-SWAP-REPORT.md) for full transaction details and protocol documentation.

### Phase 8.8: Performance Testing & Validation

**Status: ✅ Complete**

Systematic throughput and resilience testing at scale:

- [x] 7-phase stress test (baseline → ramp → sustained → burst → recovery → multi-output → cooldown)
- [x] Max-TPS blast test: 60 wallets, 3 nodes, 180s blast → 87 tx/s confirmed, 894 tx/block peak
- [x] 30–60 minute sustained run at 15–20 tx/s with 50+ wallets (endurance test)
- [x] True GHOSTDAG parallelism test: 8–12 miners to force simultaneous blocks and verify blue/red scoring under contention
- [x] 50,000-tx high-throughput test: 10 nodes, 90% ECDSA / 10% ML-DSA, 61.2 tx/s, 100% success, 29.2% multi-parent blocks
- [x] 72-hour surge endurance: ~417,000 txs, 25,736 blocks, 0 consensus splits, 0 data loss
- [x] Security audit: 86/90 pass, 0 unexpected failures, all 17 findings fixed (3 HIGH, 6 MEDIUM, 8 LOW)
- [ ] PQC signature verification CPU profiling under peak load (`getpqcsigcachestats`)
- [ ] Benchmark signature cache hit rates during sustained blast
- [ ] Pruning strategy validation for DAG metadata beyond 100k blocks

Test reports: [Max-TPS](TESTREPORT-2026-04-09-MAX-TPS.md) | [Stress](TESTREPORT-2026-04-09-STRESS.md) | [Sustained](TESTREPORT-2026-04-09-SUSTAINED-GHOSTDAG.md) | [72-Hour Surge](TESTREPORT-2026-04-14-72HR-FINAL.md) | [Security Audit](TESTREPORT-2026-07-15-SECURITY-AUDIT.md) | [Scalability Projections](TESTREPORT-2026-04-15-PROJECTIONS.md)

### Phase 9: Mining Infrastructure (Planned)

- [ ] Stratum v2 integration for pool mining
- [ ] DAG-aware mining pool protocol (multi-parent template)
- [ ] GPU/ASIC miner compatibility testing
- [ ] Difficulty adjustment tuning for real hash rate
- [ ] Publish home mining guides (CPU/GPU/small ASIC) using current testnet difficulty

### Phase 10: Protocol Hardening (Planned)

- [ ] Wire SPHINCS+ as alternative signature algorithm in wallet
- [ ] Replace Falcon/SQIsign stubs with real implementations (or remove)
- [ ] Integrate ML-KEM (Kyber) for encrypted P2P communication
- [ ] Formal security audit of PQC consensus rules
- [ ] BIP specification for QBTC hybrid witness format
- [ ] Add SPHINCS+ signature cache entries alongside Dilithium
- [ ] Pruning strategy for DAG metadata as the chain grows beyond 100k blocks

### Phase 11: Mainnet Preparation (Planned)

- [ ] Set realistic mainnet difficulty (not trivial)
- [x] Finalize block reward schedule and halving parameters (scaled to 12.6M-block interval and 83,333,333 qSat reward for 10-second DAG blocks)
- [x] Distribution Phase / Operational Phase emission model implemented
- [ ] EXT_PUBLIC_KEY / EXT_SECRET_KEY prefix finalization
- [ ] Genesis block with real mining (not nonce=0)
- [ ] Checkpoint infrastructure
- [ ] Release binaries (Linux, macOS, Windows)

---

## Codebase Statistics

### Source Code

| Component | Files | Lines |
|-----------|-------|-------|
| PQC cryptography (`src/crypto/pqc/`) | 90+ | 10,461 |
| BlockDAG consensus (`src/dag/`) | 5 | 807 |
| PQC consensus validation | 2 | 126 |
| Script interpreter PQC code | — | 27 lines |
| Wallet PQC integration | 7 files | — |
| PQC test code | 10 | 1,238 |
| DAG test code | 1 | 398 |
| Integration test script | 1 | ~1,050 |
| **Total project source** | **—** | **345,281** |

### Test Coverage

| Layer | Count | Pass Rate |
|-------|-------|-----------|
| C++ unit tests (PQC) | 45 cases | 45/45 (100%) |
| C++ unit tests (DAG) | in dag_tests.cpp | ✅ |
| Integration tests | 61 assertions | 61/61 (100%) |
| Fuzz targets | 2 (crypto_pqc, pqc_witness) | Compiled |

### Compiled Binaries

| Binary | Size |
|--------|------|
| `bitcoind` | 225 MB |
| `bitcoin-cli` | 18 MB |
| `test_bitcoin` | 412 MB |

### Network Parameters

| Parameter | Testnet | Mainnet (reserved) |
|-----------|---------|-------------------|
| Chain type | `qbtctestnet` | `qbtcmain` |
| CLI flag | `-qbtctestnet` | `-qbtcmain` |
| Magic bytes | `d1 a5 c3 b7` | `e3 b5 d7 a9` |
| P2P port | 28333 | 58333 |
| RPC port | 28332 | 58332 |
| Bech32 HRP | `qbtct` | `qbtc` |
| Base58 P2PKH | 120 (`q`) | 58 (`Q`) |
| Base58 P2SH | 122 (`r`) | 60 (`R`) |
| GHOSTDAG K | 32 | 18 |
| Block target | 10 seconds | 10 seconds |
| Max block weight | 16 MB | 16 MB |
| Block reward | 0.83333333 QBTC | 0.83333333 QBTC |
| Supply cap | ~21,000,000 QBTC | ~21,000,000 QBTC |
| Halving interval | 12,600,000 blocks (~4 years) | 12,600,000 blocks (~4 years) |
| PQC deployment | Always active | Always active |
| DAG mode | Enabled | Enabled |

### PQC Transaction Anatomy

```
P2WPKH Input Witness (4 elements):
  [0] ECDSA signature        ~71 bytes   (secp256k1)
  [1] EC public key            33 bytes   (compressed)
  [2] Dilithium signature   2,420 bytes   (ML-DSA-44)
  [3] Dilithium public key  1,312 bytes   (ML-DSA-44)

Total witness per input:    ~3,836 bytes
Virtual size (1-in/2-out):  ~1,075 vB
Weight (1-in/2-out):        ~4,299 WU
Classical equivalent:         ~141 vB (7.6× smaller)
```

### Git History

| Metric | Value |
|--------|-------|
| Total commits | 194 |
| Branch | `main` |
| Upstream | `beartec-jpg/QuantBTC` → forked from `QBlockQ/pqc-bitcoin` |
| Base | Bitcoin Core v28.0.0 |

### Key Commits

| Commit | Description |
|--------|-------------|
| `f09a9b6` | Add QuantumBTC testnet support with PQC integration |
| `4fbecdf` | Refactor PQC hybrid signing and add full integration tests |
| `be41ba9` | Wire PQC consensus verification, fix Dilithium to vendored ML-DSA |
| `b32855e` | Fix fresh build regressions in PQC code |
| `585a93f` | Refactor PQC validation and wallet integration |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    QuantumBTC Node                       │
├──────────────┬──────────────┬───────────────────────────┤
│   Wallet     │   Mempool    │   Block Validation        │
│  ┌────────┐  │              │  ┌─────────────────────┐  │
│  │Hybrid  │  │  fee-rate    │  │ VerifyScript()      │  │
│  │Key Mgmt│  │  estimation  │  │  ├─ CheckSig(ECDSA) │  │
│  │ECDSA + │  │  (PQC-aware) │  │  └─ CheckPQCSig()   │  │
│  │ML-DSA  │  │              │  │      (ML-DSA-44)    │  │
│  └────────┘  │              │  └─────────────────────┘  │
├──────────────┴──────────────┴───────────────────────────┤
│              GHOSTDAG Consensus Engine                   │
│  ┌──────────┐  ┌──────────┐  ┌────────────────────┐    │
│  │ Blue     │  │ Merge    │  │ Selected Parent    │    │
│  │ Score    │  │ Set      │  │ Chain              │    │
│  │ Compute  │  │ Ordering │  │ (virtual backbone) │    │
│  └──────────┘  └──────────┘  └────────────────────┘    │
├─────────────────────────────────────────────────────────┤
│              Network Layer (P2P)                         │
│  Magic: d1a5c3b7 │ Port: 28333 │ Bech32: qbtct         │
└─────────────────────────────────────────────────────────┘
```

---

*Last updated: April 14, 2026*
*QuantumBTC — Quantum-safe BlockDAG for a post-quantum world*
