<!-- Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; then MIT. See LICENSE-BUSL and NOTICE. -->

# qBTC: A Post-Quantum Cryptographic BlockDAG Protocol

**Technical White Paper**

| | |
|---|---|
| **Author** | BearTec |
| **Date** | April 2026 |
| **Version** | 1.0 |
| **License** | BUSL-1.1 until 2030-04-09; then MIT |
| **Repository** | [beartec-jpg/QuantBTC](https://github.com/beartec-jpg/QuantBTC) |

---

## Abstract

qBTC (QuantumBTC) is a post-quantum-secure, high-throughput blockchain protocol built as an independent fork of Bitcoin Core v28.0.0, itself derived from [QBlockQ/pqc-bitcoin](https://github.com/QBlockQ/pqc-bitcoin). It combines two major innovations: a hybrid cryptographic signature scheme resistant to quantum attack, and a BlockDAG consensus mechanism that enables parallel block production.

Every transaction on the qBTC network carries a **hybrid witness**: a classical ECDSA (secp256k1) signature paired with a lattice-based ML-DSA-44 (Dilithium2) signature standardised under NIST FIPS 204. This dual-signature design ensures that the network remains secure even if one of the two cryptographic assumptions is broken — whether by a classical adversary exploiting ECDSA weaknesses or by a quantum adversary running Shor's algorithm against elliptic-curve discrete logarithms. Quantum resistance is enforced as a **consensus rule from genesis**, not deferred as a future upgrade.

The protocol replaces Bitcoin's linear chain model with a Directed Acyclic Graph (DAG) consensus layer based on the GHOSTDAG/PHANTOM protocol (Sompolinsky & Zohar, 2018). Blocks reference multiple concurrent tips, enabling parallel block production at a 10-second target interval with up to 64 parent references per block and a GHOSTDAG k-parameter of 32 (testnet) / 18 (mainnet). This yields 60× faster confirmations than Bitcoin while preserving Bitcoin's economic model: a 21,000,000 QBTC supply cap with SHA-256 proof-of-work and a halving schedule calibrated to the same ~4-year cadence.

As of April 2026, qBTC operates a live testnet with 3 public seed nodes, over **96,600 blocks**, over **134,900 transactions**, and approximately **8,050 QBTC** mined. A public block explorer ([beartec.uk/qbtc-scan](https://beartec.uk/qbtc-scan)) and testnet faucet ([beartec.uk/qbtc-faucet](https://beartec.uk/qbtc-faucet)) are operational. Mainnet has not yet been launched.

---

## 1. Introduction

### 1.1 The Quantum Computing Threat to Bitcoin

Bitcoin's security relies fundamentally on the computational hardness of the elliptic-curve discrete logarithm problem (ECDLP) on the secp256k1 curve. A sufficiently powerful quantum computer running **Shor's algorithm** (1994) can solve this problem in polynomial time, breaking ECDSA and exposing the private keys of any address whose public key has been revealed on-chain — including every address that has ever sent a transaction.

The threat is not hypothetical in the long term. Advances in quantum hardware have accelerated steadily, and the cryptographic community broadly accepts that ECDSA will eventually become insecure against quantum adversaries. For a public, append-only ledger like Bitcoin, this poses a permanent retroactive exposure risk: transactions signed today with ECDSA can be re-examined in a future quantum computing environment.

### 1.2 Motivation for a Post-Quantum Bitcoin Fork

Existing proposals to add post-quantum security to Bitcoin (e.g., via soft fork or script upgrade) face significant coordination challenges: they require consensus among miners, nodes, and the broader Bitcoin developer community, and they cannot be activated retroactively. Retrofitting quantum resistance onto a live, trillion-dollar network without disrupting existing UTXOs is an extraordinarily difficult problem.

qBTC takes a different approach: **a clean-slate fork** that enforces hybrid quantum-resistant signatures as a consensus rule from the genesis block. There are no legacy ECDSA-only UTXOs to protect. Every address on the network has been provisioned with both classical and post-quantum key material from creation.

### 1.3 Design Philosophy

qBTC is designed around three principles:

1. **Preserve Bitcoin's economic model.** The 21M supply cap, SHA-256 proof-of-work, and halving schedule are preserved. Users familiar with Bitcoin's monetary properties will find qBTC's tokenomics immediately recognisable.

2. **Enforce quantum resistance at the protocol level.** Hybrid ECDSA + ML-DSA-44 signatures are a consensus requirement, not an optional feature. A transaction without a valid Dilithium signature is invalid on the qBTC network.

3. **Enable high throughput via BlockDAG.** The GHOSTDAG consensus layer allows parallel block production, increasing transaction throughput without increasing block size limits to unworkable levels.

### 1.4 Provenance

qBTC is maintained by [BearTec](https://github.com/beartec-jpg) and is forked from [QBlockQ/pqc-bitcoin](https://github.com/QBlockQ/pqc-bitcoin), which itself is a fork of **Bitcoin Core v28.0.0**. The upstream pqc-bitcoin project provided the initial PQC algorithm stubs, `HybridKey` class, `PQCConfig` system, wallet PQC key storage, and script interpreter hooks. qBTC has substantially extended this foundation with production cryptographic implementations, the GHOSTDAG consensus engine, a live testnet, and a comprehensive test suite.

---

## 2. Post-Quantum Cryptography

### 2.1 Threat Model: Why ECDSA Is Vulnerable

ECDSA security rests on the hardness of the elliptic-curve discrete logarithm problem: given a point $Q = kG$ on a curve, recovering the scalar $k$ is computationally infeasible for classical computers. However, Shor's algorithm (1994) solves this problem efficiently on a quantum computer, recovering the private key $k$ from the public key $Q$ in $O((\log n)^3)$ quantum operations.

The practical consequence for Bitcoin — and any ECDSA-based system — is that once a Bitcoin address sends a transaction, its public key is revealed in the witness. On a sufficiently powerful quantum computer, that public key can be used to derive the private key, enabling theft of any remaining funds at that address. Addresses that have never sent a transaction (and thus have not revealed their public key) retain some protection, but the long-term trend in quantum hardware development renders ECDSA-only schemes an unacceptable long-term security model for a value-bearing network.

### 2.2 Hybrid Signature Scheme

qBTC uses a **hybrid signature scheme** combining two cryptographic systems:

1. **ECDSA (secp256k1)** — the classical Bitcoin signature algorithm, providing security against classical adversaries under current computational assumptions.
2. **ML-DSA-44 (CRYSTALS-Dilithium2)** — a lattice-based digital signature scheme standardised as **NIST FIPS 204**, providing quantum resistance via the hardness of the Module Learning With Errors (MLWE) problem.

A transaction is valid only if **both** signatures verify correctly. This approach provides a **dual-failure model**: security is maintained if either system is unbroken. An adversary must simultaneously break ECDSA (classically hard) and ML-DSA-44 (quantum-hard) to forge a signature. Conversely, if ML-DSA-44 is later found to have a classical weakness, ECDSA still provides the classical security guarantee.

The hybrid design is implemented by vendoring the official pq-crystals ML-DSA-44 reference implementation at `src/crypto/pqc/ml-dsa/`, using Bitcoin Core's `GetStrongRandBytes()` as the entropy source for all key generation and signing operations.

### 2.3 Transaction Witness Format

PQC hybrid transactions use a **4-element P2WPKH witness stack**:

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

The 4-element witness stack is automatically detected by the consensus layer in `src/script/interpreter.cpp`. When a 4-element witness is present with elements matching Dilithium sizes (signature 2,420 bytes; public key 1,312 bytes), `CheckPQCSignature()` is invoked for cryptographic Dilithium verification in addition to the standard ECDSA path.

Witness data is stored in the SegWit witness area and benefits from the witness weight discount (4× discount factor), making PQC transactions approximately 34.9× heavier than a standard P2WPKH transaction by virtual size — a known and accepted cost of quantum resistance. Fee estimation in the wallet correctly accounts for PQC witness weight.

### 2.4 Supported Algorithms

#### Digital Signature Algorithms

| Algorithm | Standard | Status | Notes |
|-----------|----------|--------|-------|
| ML-DSA-44 (Dilithium2) | NIST FIPS 204 | ✅ **Primary — fully implemented and consensus-enforced** | Vendored pq-crystals reference; sign/verify wired into interpreter and wallet |
| SPHINCS+ (SLH-DSA-SHA2-128f) | NIST FIPS 205 | ✅ Crypto primitives implemented | Sig: 17,088 B, PK: 32 B; not yet wired to wallet signing |
| Falcon (FN-DSA-512) | — | ❌ Stub only | All operations return errors; not wired to real implementation |
| SQIsign | — | ❌ Stub only | All operations return errors; awaiting NIST standardisation |

#### Key Encapsulation Mechanisms (KEMs)

| Algorithm | Standard | Status | Notes |
|-----------|----------|--------|-------|
| ML-KEM-768 (Kyber) | NIST FIPS 203 | Implemented | Not yet used in protocol; KEM not used for node communication |
| FrodoKEM-976 | — | Implemented | Not yet used in protocol; KeyGen/Encaps/Decaps currently disabled |
| NTRU-HPS-4096-821 | — | Implemented | Not yet used in protocol; KeyGen/Encaps/Decaps currently disabled |

> **Note on KEMs:** The three KEM algorithms (Kyber, FrodoKEM, NTRU) are implemented in code but are not currently used in the qBTC protocol. They are present for future use in encrypted P2P communication. Specifying them via `-pqcalgo=kyber,frodo,ntru` logs a warning and is currently ignored. The `enabled_kems` default is `{}` (empty).

### 2.5 Key Management

PQC key management is integrated into the descriptor wallet:

- **Storage prefix:** `walletdescriptorpqckey`, keyed by `(descriptor_id, EC_public_key)` in the wallet database.
- **Generation:** Approximately **8,000 Dilithium keypairs** are generated per wallet (8 descriptors × 1,000 keys) during wallet creation and top-up.
- **Derivation:** Deterministic key derivation from 32-byte seeds using `GetStrongRandBytes()`.
- **Memory security:** Private key material is stored in `PQCPrivateKey` — a `std::vector<unsigned char, secure_allocator<unsigned char>>` — providing memory locking and automatic cleansing on destruction. There is no public getter for raw private key material; signing is performed via the scoped `SignPQCMessage()` method which cleanses intermediate buffers after use.
- **Scale:** At a 10-second block interval, a wallet with 8,000 pre-generated keys provides years of address capacity without requiring on-the-fly key generation.

### 2.6 Consensus Verification

PQC signature verification in the consensus layer is implemented in `src/script/interpreter.cpp`:

- **Detection:** A 4-element witness stack triggers PQC verification. The dispatch is by signature size: elements matching `DILITHIUM_SIGNATURE_SIZE` (2,420 bytes) route to `CheckPQCSignature()` (ML-DSA-44), and elements matching `SPHINCS_SIGNATURE_SIZE` (17,088 bytes) route to `CheckSPHINCSSignature()`.
- **Error codes:** Dedicated error codes provide precise rejection reasons: `SCRIPT_ERR_PQC_VERIFY_FAILED`, `SCRIPT_ERR_PQC_WITNESS_MALFORMED`, `SCRIPT_ERR_PQC_ALGO_UNSUPPORTED`, `SCRIPT_ERR_PQC_KEY_SIZE_MISMATCH`.
- **Script flag:** `SCRIPT_VERIFY_PQC` (bit 21) enables PQC enforcement.
- **BIP 9 deployment:** `DEPLOYMENT_PQC` uses version bit 3. On qBTC chains (testnet and mainnet), the deployment is `ALWAYS_ACTIVE` — no signalling period is required.
- **Verification timing:** PQC signatures are verified at both mempool acceptance and block connection. The PQC signature cache (see Section 6.2) avoids redundant verification for transactions already seen in the mempool.

---

## 3. BlockDAG Consensus (GHOSTDAG)

### 3.1 From Linear Chain to DAG

Bitcoin's linear chain model enforces a strict total ordering of blocks: at most one block can extend the chain tip at any given time, and any concurrent block is immediately orphaned. This design is simple and secure, but it wastes significant mining work (orphaned blocks) and limits throughput, because block intervals must be long enough that propagation delay is small relative to the inter-block time.

A **BlockDAG** (Directed Acyclic Graph) generalises the linear chain: each block may reference **multiple** previous blocks as parents, and concurrent blocks are not discarded but incorporated into the DAG structure. This allows parallel block production and dramatically increases the fraction of mining work that contributes to chain security. The challenge is establishing a consistent **total ordering** of DAG blocks so that all nodes agree on transaction precedence.

### 3.2 GHOSTDAG Protocol

qBTC implements the **GHOSTDAG** variant of the PHANTOM protocol (Sompolinsky & Zohar, 2018), as deployed in the Kaspa network. The algorithm operates as follows:

1. **Blue set computation.** For each block, GHOSTDAG computes a **blue score** — an integer representing the cumulative weight of "honest" (blue) blocks in its past cone. A block is classified as **blue** if its anticone (the set of blocks neither in its past nor its future) has size at most **k**. Blue blocks form the "selected sub-DAG" representing the honest chain.

2. **Red classification.** Blocks with an anticone exceeding k are classified as **red** (conflicting). Red blocks are still included in the DAG and their transactions may still be confirmed, but they carry lower trust weight.

3. **Selected parent chain.** The selected parent of a block is the block in its parent set with the highest blue score. Following selected parents from the current tip back to genesis yields the **selected parent chain** — a linear backbone analogous to Bitcoin's main chain, used for difficulty adjustment and transaction ordering.

4. **Merge set ordering.** For each block connected to the selected parent chain, the **merge set** — the set of blue blocks in its past cone not already in the selected parent chain — is incorporated in blue-score order, providing a consistent total ordering of all transactions.

The `GhostdagManager` class (`src/dag/ghostdag.cpp`) implements blue score computation, merge set construction, and selected parent chain traversal. The selected parent chain walk is bounded to `2K+1` blocks to avoid O(height) complexity.

### 3.3 Parameters

| Parameter | qbtctestnet | qbtcmain | Description |
|-----------|-------------|----------|-------------|
| `ghostdag_k` | 32 | 18 | Max anticone size for a blue block |
| `nMaxDagParents` | 64 | 64 | Maximum parent references per block |
| `fDagMode` | `true` | `true` | BlockDAG mode enabled |
| Block target interval | 10 seconds | 10 seconds | Target time between blocks |
| Max block weight | 16 MB | 16 MB | Maximum block weight |

The testnet uses K=32 for broader inclusivity: a higher k value means more concurrent blocks can be classified as blue per round, reducing the probability that small or solo miners are orphaned. K=18 is used on mainnet, matching the Kaspa reference deployment.

With K=32 and 10-second targets, the network can tolerate up to approximately 32 concurrent block arrivals per round without any being red-classified. Under normal hashrate distribution, nearly all blocks will be blue.

### 3.4 Block Identity: 80-Byte Hash Invariant

A critical design decision in the qBTC DAG layer is that **`GetHash()` hashes only the canonical 80-byte base header** (nVersion, hashPrevBlock, hashMerkleRoot, nTime, nBits, nNonce). DAG parent hashes (`hashParents`) are **not** included in the block identity hash or the proof-of-work hash.

This invariant was introduced to fix a critical restart-instability bug (commit `74ab011`). The failure cascade was:

1. `CBlockHeader::GetHash()` hashed the 80-byte base header **plus** serialised `hashParents`.
2. `CDiskBlockIndex` did not persist `hashParents` to LevelDB.
3. On restart, `LoadBlockIndexGuts` reconstructed the block index from disk, but `hashParents` was empty, causing `ConstructBlockHash()` to produce a different hash than was recorded before shutdown.
4. Every block's identity changed. `mapBlockIndex` lookups failed, `GetAncestor` assertions fired, and nodes could not sync with peers that had never restarted.

The fix was twofold: `GetHash()` now hashes only the classic 80 bytes (matching Bitcoin Core's original behaviour), and `CDiskBlockIndex` now serialises `hashDagParents` so that `LoadBlockIndexGuts` can restore `vDagParents` pointers on startup.

The `nVersion` bit `0x10000000` (`BLOCK_VERSION_DAGMODE`) signals that a block is a DAG block and triggers DAG-specific serialisation for parent references.

### 3.5 Tip-Set Management

The `DagTipSet` class (`src/dag/dagtipset.cpp`) tracks all concurrent tips of the DAG:

- **Tracking location:** Tip-set updates occur in `AcceptBlock()`, not `ConnectTip()`. This ensures that fork blocks (blocks on non-selected branches) are also tracked as tips, which is critical for GHOSTDAG correctness.
- **Parent selection:** `GetMiningParents()` returns the current tip set sorted by blue_score descending, providing miners with the optimal parent set for maximising the blue score of the next block.
- **Score pruning:** `m_known_scores` is pruned to evict entries more than 1,000 blue_scores behind the best tip (that are not current tips), capping memory growth at approximately 82 KB rather than ~82 MB/day of unbounded growth.
- **Maximum parents:** Each block may reference up to 64 parent blocks (`nMaxDagParents`).

### 3.6 DAG Difficulty Adjustment

Difficulty adjustment in DAG mode uses `GetNextWorkRequiredDAG()` with a 128-block rolling window, analogous to Bitcoin's 2,016-block retarget but adapted to the 10-second block target. The window size of 128 blocks corresponds to approximately 21 minutes at the target spacing, providing responsive difficulty adjustment while filtering out short-term hashrate variance.

---

## 4. Tokenomics & Economic Model

### 4.1 Supply Parameters

qBTC preserves Bitcoin's core monetary properties:

- **Total supply cap:** 21,000,000 QBTC
- **Block reward:** 0.83333333 QBTC (83,333,333 qSats)
- **Halving interval:** 12,600,000 blocks (~4 years at 10-second blocks)
- **Proof-of-work algorithm:** SHA-256 (identical to Bitcoin)

### 4.2 Comparison with Bitcoin

| Parameter | Bitcoin | qBTC |
|-----------|---------|------|
| Block interval | 600 seconds | 10 seconds |
| Halving interval | 210,000 blocks (~4 years) | 12,600,000 blocks (~4 years) |
| Initial block reward | 50 BTC | 0.83333333 QBTC (83,333,333 qSats) |
| Total supply cap | ~21,000,000 BTC | ~21,000,000 QBTC |
| Consensus | Linear chain (longest chain) | BlockDAG (GHOSTDAG) |
| Signature | ECDSA only | ECDSA + ML-DSA-44 (hybrid) |
| Block throughput | ~1 block/10 min | ~6 blocks/min (DAG, parallel) |

The emission schedule is scaled so that the halving cadence matches Bitcoin's ~4-year rhythm despite the 60× faster block interval. This preserves the supply schedule's economic properties: a predictable, decreasing emission rate with a hard cap.

### 4.3 Two-Phase Emission Model

qBTC implements a two-phase emission model to bootstrap the network and transition it to transaction-driven mining:

**Phase 1 — Distribution (blocks 0 to 12,599,999, approximately 4 years)**

- Empty blocks (coinbase-only transactions with no user transactions) are valid and earn the full block reward.
- Any participant can mine and collect QBTC — no transaction activity is required.
- Approximately 10,500,000 QBTC (50% of the total supply) is distributed during this phase.
- This is a **fair-launch distribution**: SHA-256 proof-of-work is the only requirement.

**Phase 2+ — Operational (block 12,600,000 onward, in perpetuity)**

- Empty blocks remain technically valid (the chain never stalls during quiet periods).
- However, **empty blocks earn zero subsidy** — fees only.
- Blocks that include at least one user transaction earn the normal halved subsidy plus transaction fees.
- This structure naturally transitions the network to transaction-driven mining incentives, mirroring the long-term dynamics of Bitcoin after its final halving.

### 4.4 Unit Denomination

The smallest unit of qBTC is the **qSat** (quantum satoshi):

- 1 QBTC = 100,000,000 qSats
- 1 qSat = 0.00000001 QBTC

The naming is intentional: it preserves the familiar satoshi denomination while acknowledging the quantum-resistant design of the network.

---

## 5. Network Architecture

### 5.1 Chain Parameters

| Parameter | qbtctestnet | qbtcmain (reserved) |
|-----------|-------------|---------------------|
| CLI flag | `-qbtctestnet` | `-qbtcmain` |
| Chain type | `qbtctestnet` | `qbtcmain` |
| Magic bytes | `d1 a5 c3 b7` | `e3 b5 d7 a9` |
| P2P port | 28333 | 58333 |
| RPC port | 28332 | 58332 |
| Bech32 HRP | `qbtct` | `qbtc` |
| Bech32 address prefix | `qbtct1...` | `qbtc1...` |
| Base58 P2PKH prefix | 120 (`q`) | 58 (`Q`) |
| Base58 P2SH prefix | 122 (`r`) | 60 (`R`) |
| GHOSTDAG K | 32 | 18 |
| Block target interval | 10 seconds | 10 seconds |
| Max block weight | 16 MB | 16 MB |
| Block reward | 0.83333333 QBTC | 0.83333333 QBTC |
| Halving interval | 12,600,000 blocks (~4 years) | 12,600,000 blocks (~4 years) |
| Supply cap | ~21,000,000 QBTC | ~21,000,000 QBTC |
| PQC deployment | Always active | Always active |
| DAG mode | Enabled | Enabled |

### 5.2 Address Format

qBTC uses distinct address prefixes that prevent confusion with Bitcoin or other Bitcoin forks:

- **Testnet bech32:** `qbtct1...` (HRP: `qbtct`)
- **Mainnet bech32:** `qbtc1...` (HRP: `qbtc`)
- **Testnet base58 P2PKH:** prefix byte 120, producing addresses starting with `q`
- **Testnet base58 P2SH:** prefix byte 122, producing addresses starting with `r`
- **Mainnet base58 P2PKH:** prefix byte 58, producing addresses starting with `Q`
- **Mainnet base58 P2SH:** prefix byte 60, producing addresses starting with `R`

PQC is **always active** on qBTC chains — no manual `-pqc=1` flag is required. New wallets automatically receive both ECDSA and Dilithium key material.

### 5.3 P2P Protocol

The qBTC P2P protocol extends Bitcoin Core's existing messaging layer:

- **Seed nodes (testnet):** `46.62.156.169:28333`, `37.27.47.236:28333`, `89.167.109.241:28333`
- **Block relay:** PQC-aware block relay using compact block extensions to handle the larger PQC transaction witnesses.
- **DAG header extension:** `hashParents` is serialised after the standard 80-byte header in `CBlockHeader::SERIALIZE_METHODS` for P2P transmission, but not included in `GetHash()`.
- **Version bits:** Block version bit `0x10000000` (`BLOCK_VERSION_DAGMODE`) signals DAG-mode blocks to peers.

### 5.4 RPC Extensions

qBTC adds several RPC fields and commands beyond standard Bitcoin Core:

| RPC | Description |
|-----|-------------|
| `getpqcinfo` | Returns PQC configuration status: enabled flag, mode, algorithm, key counts per wallet |
| `getpqcsigcachestats` | Returns real-time signature cache statistics: hit/miss counts and rates for Dilithium and ECDSA |
| `getblockchaininfo` | Extended with `pqc: true` on qBTC chains |
| `getblockheader` | Extended with `dagparents` (array of parent block hashes) and `dagblock` (bool) |
| `getblock` | Extended with the same DAG fields as `getblockheader`, plus `dagmode` and `ghostdag_k` |
| `getaddressinfo` | Extended with `pqc_enabled`, `has_pqc_key`, `pqc_algorithm`, `pqc_pubkey` |
| `gettransaction` | Extended with `pqc_signed` for PQC witness detection |

---

## 6. Performance & Scalability

### 6.1 Memory Optimisation

qBTC's 10-second DAG blocks generate significant memory churn: block templates, GHOSTDAG merge sets, transaction validation queues, and PQC signature caching. Several proactive optimisations have been implemented to keep memory usage bounded as the chain scales:

- **jemalloc integration:** Build-time integration of [jemalloc](https://jemalloc.net/) replaces glibc's default `ptmalloc2` allocator, reducing heap fragmentation by approximately 40–60% under DAG block churn through thread-local arenas, size-class bucketing, and aggressive page purging.
- **DAG-optimised cache flags:** Default cache sizes of `-dbcache=150` (coins cache) and `-maxsigcachesize=32` (PQC signature cache) are tuned for 10-second block production.
- **m_known_scores pruning:** `DagTipSet::m_known_scores` is pruned to evict entries more than 1,000 blue_scores behind the best tip, capping growth to approximately 82 KB rather than ~82 MB/day.
- **SelectedParentChain depth limit:** `GhostdagManager::SelectedParentChain()` is bounded to `2K+1` blocks (37 for K=18), reducing per-call complexity from O(height) to O(K).
- **Mergeset pruning:** `mergeset_blues` / `mergeset_reds` vectors are cleared for blocks buried more than 1,000 blocks deep during `ConnectTip()`, preventing permanent RAM growth.
- **mapDeltas bounding:** `PrioritiseTransaction` delta entries are capped at 100,000 to prevent unbounded growth from orphaned priority entries.
- **IsBlockAncestor BFS:** Replaced a height-unlimited BFS with a height-bounded implementation, preventing non-deterministic merge sets across nodes that could arise from the previous incorrect `false` returns for genuine ancestors.

### 6.2 PQC Signature Cache

ML-DSA-44 verification is approximately **35× slower** than ECDSA verification (`secp256k1_ecdsa_verify`), and each Dilithium witness occupies approximately 3.7 KB (2,420-byte signature + 1,312-byte public key). Without caching, block relay would require re-verifying every Dilithium signature seen in the mempool.

The `SignatureCache` (`src/script/sigcache.h`) caches verified Dilithium signatures alongside ECDSA and Schnorr entries in a single `CuckooCache`:

- **Cache key computation:** `ComputeEntryDilithiumRaw()` hashes `(pqc_sig, pqc_pubkey, ecdsa_sig, scriptCode, sigversion)` using a salted hasher with padding byte `'D'`.
- **Cache lookup:** `CachingTransactionSignatureChecker::CheckDilithiumSignature()` checks the cache before falling back to full ML-DSA-44 verification.
- **Hit rate monitoring:** `getpqcsigcachestats` provides real-time counters. A healthy hit rate on a synced node should be above 50% (most transactions are verified once at mempool acceptance, then served from cache at block connection).

### 6.3 Stress Test Results

A comprehensive 10-node stress test was conducted in April 2026:

**Test Configuration**

| Parameter | Value |
|-----------|-------|
| Nodes | 10 |
| Wallets | 30 (3 per node) |
| Transactions | 10,000 post-quantum hybrid |
| Blocks mined | 531 |
| Total wall time | 14.7 minutes |

**Transaction Performance**

| Metric | Value |
|--------|-------|
| Attempted | 10,000 |
| Succeeded | 10,000 (100.0%) |
| Failed | 0 |
| PQC hybrid txs | 10,061 (100%) |
| Effective TPS | **13.4 tx/s** |

**Submit Latency**

| Statistic | Value |
|-----------|-------|
| Mean | 58.8 ms |
| Median | 44.8 ms |
| P95 | 146.4 ms |
| P99 | 181.8 ms |

**Block Relay (miner to 9 peers)**

| Statistic | Value |
|-----------|-------|
| Mean | **289 ms** |
| Median | 298 ms |
| P95 | 368 ms |

**P2P Propagation (to all 10 nodes)**

| Statistic | Value |
|-----------|-------|
| Mean | 2,818 ms |
| Median | 3,126 ms |

**Transaction Size**

| Metric | Value |
|--------|-------|
| Median vsize | 1,075 vB |
| Mean vsize | 1,479 vB |
| PQC overhead vs P2WPKH | 34.9× |

All 10 nodes maintained 18 peers in a full mesh and synced consistently at height 531. The 100% success rate across 10,000 PQC hybrid transactions demonstrates the protocol's readiness for testnet use.

### 6.4 10-Second Block Rationale

qBTC migrated from 1-second to 10-second blocks in April 2026 (commit series, Phase 8.6). The primary driver was the interaction between PQC transaction size and block interval:

- **1-second blocks with full PQC transactions** would generate approximately **326 GB/day** of network bandwidth at capacity and 31,500,000 blocks/year for initial block download (IBD).
- **10-second blocks** reduce this to approximately **32 GB/day** and 3,150,000 blocks/year while retaining 60× faster confirmations than Bitcoin.
- **DAG collision rate** at 10-second blocks with 100+ miners remains approximately **40% parallel blocks** — the BlockDAG structure remains valuable and distinguishes qBTC from a linear chain.

All chain parameters (subsidy halving interval, block reward, difficulty window) were rescaled to preserve the ~4-year halving cadence and ~21M supply cap. The migration was completed with a full chain wipe and rebuild from genesis on all 3 testnet nodes; difficulty converged to the 10-second target within approximately 4 retarget windows (~512 blocks).

---

## 7. Security

### 7.1 Hybrid Security Model

The hybrid ECDSA + ML-DSA-44 signature scheme provides **layered security**:

- **If ECDSA remains secure** (classical computers only), the classical signature alone provides the same security guarantee as Bitcoin.
- **If a quantum computer breaks ECDSA**, the Dilithium signature provides quantum-resistant security independently.
- **Both must be broken simultaneously** for a transaction to be forgeable.

This design ensures that qBTC is not merely post-quantum-ready in name — it is quantum-secure under the current state of both classical and quantum adversary capabilities.

### 7.2 Constant-Time Operations

All PQC algorithms in qBTC are implemented using **constant-time operations** to prevent timing side-channel attacks:

- The vendored pq-crystals ML-DSA-44 reference implementation uses constant-time arithmetic throughout.
- The SPHINCS+ (SLH-DSA) reference implementation uses SHA-256 in a manner that is not branch-dependent on secret material.
- Bitcoin Core's `GetStrongRandBytes()` is used as the entropy source for all key generation.
- A single canonical `randombytes()` implementation is defined, using `GetStrongRandBytes` with proper memory cleansing — preventing the multiple-definition bug (ODR violation) that was present in the upstream pqc-bitcoin codebase.

### 7.3 Memory Safety

Private key material is handled with explicit memory safety measures:

- **PQCPrivateKey type:** Private keys are stored as `std::vector<unsigned char, secure_allocator<unsigned char>>`, providing memory locking (`mlock`) and automatic cleansing on destruction via `secure_allocator`.
- **No public key getter:** `GetPQCPrivateKey()` was removed. External code accesses the private key only through the scoped `SignPQCMessage()` method, which cleanses intermediate signature buffers (`classical_sig`, `pqc_sig`) with `memory_cleanse()` before returning.
- **Intermediate buffer cleansing:** All intermediate cryptographic buffers in `HybridKey::Sign()` are explicitly cleansed after use.

### 7.4 Audit Results

An internal code review of the PQC consensus and key management code was conducted in April 2026, identifying **12 findings** (3 CRITICAL, 5 HIGH, 4 MEDIUM). All 12 findings have been resolved. The full details are documented in [REPORT.md § 9](REPORT.md).

**Summary of findings and resolutions:**

| Severity | Finding | Resolution |
|----------|---------|-----------|
| CRITICAL | SPHINCS+ witness routing — interpreter hard-gated on Dilithium sig size, SPHINCS+ always rejected | 4-element witness path now branches on sig size: Dilithium routes to `CheckPQCSignature()`, SPHINCS+ to `CheckSPHINCSSignature()` |
| CRITICAL | PQC private key in plain `std::vector<unsigned char>` with no memory locking | Changed to `PQCPrivateKey` with `secure_allocator`; removed public getter; added scoped `SignPQCMessage()` |
| CRITICAL | `CheckPQCSignatures()` name implied cryptographic verification but only checked element sizes | Added explicit docstring clarifying it is a structural precheck only; cryptographic verification is in `VerifyScript()` |
| HIGH | Hot-path `LogPrintf` in witness verification | Replaced with `LogDebug(BCLog::VALIDATION, ...)` |
| HIGH | `GetPQCPrivateKey()` public getter exposed raw secret key material | Removed getter; added `HasPQCPrivateKey()` (bool) and `SignPQCMessage()` |
| HIGH | `HybridKey::Sign()` hybrid blob format undocumented | Added docstring clarifying internal format vs. consensus witness format |
| HIGH | `-pqcalgo=kyber,frodo,ntru` silently accepted despite all being stubs | Now logs warning; default `enabled_kems` changed to `{}` |
| HIGH | Falcon/SQIsign stubs | Already safe — all operations return `false` |
| MEDIUM | Default `enabled_kems` advertised `{KYBER, FRODOKEM, NTRU}` despite all being stubs | Fixed as part of H7 resolution |
| MEDIUM | SPHINCS+ size check over-permissive (range check) | Tightened to exact match: `sig_elem.size() == SPHINCS::SIGNATURE_SIZE` |
| MEDIUM | `Verify()` used config flag as branch condition, silently downgrading hybrid txs | Now detects hybrid format from signature structure, regardless of config flag |
| MEDIUM | `memory_cleanse()` not called on intermediate signature vectors | Added `memory_cleanse()` calls for all intermediate vectors before return |

### 7.5 Early Protection System

qBTC implements an **Early Protection System** to mitigate anti-competitive behaviour during network bootstrap:

- Per-peer block weight tracking using IP-based identification to prevent a single miner from dominating the DAG during the early network phase.
- Activation threshold, throttle factor, and ramp-up period are implemented as consensus parameters.
- The `nEarlyProtectionWeight` field in `CBlockIndex` carries the per-block protection weight score.

The Early Protection System's ephemeral per-node data (peer activation times, ramp counts, IP windows) was deliberately **excluded** from `nChainWork` calculations to prevent chain-selection inconsistencies: different nodes observing different peer events must compute identical chain weights for consensus to be maintained.

---

## 8. Implementation Status

### 8.1 What Works Today

| Capability | Status | Details |
|------------|--------|---------|
| Solo mining | ✅ | `generatetoaddress` produces DAG-mode blocks with trivial difficulty |
| PQC transactions | ✅ | Every spend carries hybrid ECDSA + ML-DSA-44 witness |
| Peer-to-peer sync | ✅ | Nodes discover, connect, and sync full chain including PQC transactions |
| Wallet operations | ✅ | Create, load, encrypt, send, receive with PQC keys |
| Fee estimation | ✅ | Correctly accounts for PQC witness size (~1,075 vB per input) |
| RBF (Replace-by-Fee) | ✅ | Fully functional with PQC transactions |
| CPFP (Child-pays-for-parent) | ✅ | Functional with PQC witness |
| Block validation | ✅ | Full consensus verification of PQC signatures and DAG parents |
| Reorg handling | ✅ | Chain reorganisations preserve PQC transaction integrity |
| Multiple wallets | ✅ | Concurrent wallets, cross-wallet PQC verification |
| Wallet encryption | ✅ | Encrypt/unlock/lock cycle with PQC signing |
| DAG parallel blocks | ✅ | Multiple concurrent tips, GHOSTDAG blue ordering |
| Unique addresses | ✅ | `qbtct1...` / `qbtc1...` prefixes, no confusion with Bitcoin |
| Signature cache | ✅ | Dilithium verification cached alongside ECDSA/Schnorr |
| PQC-aware fee estimation | ✅ | `WPKHDescriptor::MaxSatSize()` returns correct PQC witness sizes |
| jemalloc integration | ✅ | Linked at build time for reduced heap fragmentation |

### 8.2 Test Coverage

**C++ Unit Tests (45 test cases across 10 test files):**

| Test Suite | Cases | Coverage |
|------------|-------|----------|
| `pqc_dilithium_tests` | 9 | Keygen, sign/verify, tampered message/sig, wrong pubkey, deterministic derivation |
| `pqc_witness_tests` | 4 | Valid PQC witness, wrong Dilithium sig, wrong-size sig, wrong-size pubkey |
| `pqc_fee_tests` | 2 | MaxSatisfactionWeight with/without PQC, DummySignatureCreator witness structure |
| `pqc_kyber_tests` | 5 | Encaps/decaps roundtrip, tampered ciphertext, cross-key mismatch |
| `pqc_sphincs_tests` | 8 | Keygen, sign/verify, tampered message/sig |
| `pqc_frodo_fo_tests` | 6 | Roundtrip, implicit rejection |
| `pqc_ntru_fo_tests` | 5 | Roundtrip, implicit rejection |
| `pqc_signature_tests` | 4 | All signature schemes |
| `dag_tests` | — | DAG topology, GHOSTDAG scoring and ordering |

**Integration Tests:** 61 assertions across 30 test groups, covering: node identity, wallet PQC provisioning, PQC hybrid transaction creation and verification, DAG parallel blocks, GHOSTDAG ordering, corrupt witness rejection, sig mutation, replay protection, fee estimation, RBF, CPFP, two-node propagation, wallet encryption, and more.

**Fuzz Targets:** `crypto_pqc_dilithium`, `crypto_pqc_sphincs`, `crypto_pqc_kyber`, `crypto_pqc_ntru`, `crypto_pqc_frodokem`, `pqc_witness` (random witness stack fuzzing).

**Stability Tests (all passing):**
- `test_kill9_recovery.sh`: 10/10 PASS — SIGKILL crash recovery with `-reindex`
- `test_restart_10k.sh`: 9/9 PASS — Mine 10k blocks, graceful stop, restart, verify chain
- `test_ibd_genesis.sh`: 14/14 PASS — 2-node IBD sync (2,000 blocks)

### 8.3 Live Testnet

The qBTC testnet has been operational continuously since deployment. Network statistics as of April 5, 2026:

| Metric | Value |
|--------|-------|
| Chain height | ~96,600+ blocks |
| Total transactions | ~134,900+ |
| Chain size on disk | ~1.34 GB |
| Active nodes | 3 seed nodes |
| Active peers per node | 3–4 |
| Total mined supply | ~8,050 QBTC |
| Sustained transaction rate | ~7.2 tx/s |

**Seed nodes:**

| Node | IP Address | Height | Balance (QBTC) |
|------|------------|--------|----------------|
| S1 (seed) | 46.62.156.169 | 96,637 | 1,563.98 |
| S2 (seed) | 37.27.47.236 | 96,654 | 1,937.28 |
| S3 (verify) | 89.167.109.241 | 96,654 | 1,903.29 |

To join the testnet, add the following to `~/.bitcoin/bitcoin.conf`:

```ini
[qbtctestnet]
chain=qbtctestnet
server=1
listen=1
fallbackfee=0.0001
txindex=1
seednode=46.62.156.169:28333
seednode=37.27.47.236:28333
seednode=89.167.109.241:28333
```

### 8.4 Infrastructure

- **Block Explorer:** [beartec.uk/qbtc-scan](https://beartec.uk/qbtc-scan) — live dashboard with blocks, difficulty, hash rate, mempool, peers, DAG tips. Search by txid, block hash/height, or address. Shows PQC status, DAG mode, and node version.
- **Testnet Faucet:** [beartec.uk/qbtc-faucet](https://beartec.uk/qbtc-faucet) — 0.5 QBTC per claim, rate-limited to one claim per hour per IP address.
- **Python wallet library:** `contrib/beartec-wallet/qbtc_wallet.py`
- **Testnet scripts:** `contrib/qbtc-testnet/` — configuration template, launch script, and Docker support

---

## 9. Roadmap

qBTC follows an 11-phase development roadmap. Phases 1–8 are complete. The remaining phases are:

### Phase 9: Mining Infrastructure (Planned)

- Stratum v2 integration for pool mining
- DAG-aware mining pool protocol supporting multi-parent block templates
- GPU/ASIC miner compatibility testing
- Difficulty adjustment tuning for real hashrate distributions
- Published home mining guides (CPU/GPU/small ASIC)

### Phase 10: Protocol Hardening (Planned)

- Wire SPHINCS+ (SLH-DSA-SHA2-128f) as an alternative signature algorithm in the wallet
- Replace Falcon/SQIsign stubs with real implementations, or formally remove them
- Integrate ML-KEM (Kyber) for encrypted P2P node communication
- Formal third-party security audit of PQC consensus rules
- BIP specification for the QBTC hybrid witness format
- SPHINCS+ signature cache entries alongside Dilithium
- Pruning strategy for DAG metadata as the chain grows beyond 100k blocks

### Phase 11: Mainnet Preparation (Planned)

- Set realistic mainnet difficulty (not trivial testnet proof-of-work)
- Genesis block with real mining (not `nonce=0`)
- Checkpoint infrastructure for IBD acceleration
- EXT_PUBLIC_KEY / EXT_SECRET_KEY prefix finalisation
- Release binaries for Linux, macOS, and Windows

> **Note:** Mainnet (`CQbtcMainParams`) is defined in code but has not been deployed. No mainnet launch date has been announced.

---

## 10. Conclusion

qBTC occupies a unique position in the blockchain landscape: it is the only production-tested Bitcoin fork that simultaneously provides (1) **quantum-resistant signatures** enforced as a consensus rule from genesis, (2) **BlockDAG parallel block production** via GHOSTDAG for high throughput, and (3) **Bitcoin's economic model** — the 21M supply cap, SHA-256 proof-of-work, and halving schedule — preserved intact.

The protocol addresses the long-term existential threat that quantum computing poses to ECDSA-based blockchains, doing so today rather than deferring the problem to future governance battles. The hybrid ECDSA + ML-DSA-44 design ensures backwards compatibility with classical security assumptions while providing forward security against quantum adversaries.

The live testnet demonstrates that the design is technically sound: over 96,600 blocks and 134,900 transactions have been produced with a 100% PQC witness rate, the network has sustained 13.4 tx/s under stress, and block relay averages 289 ms across 10 nodes.

**Join the testnet.** Connect a node to the public seed addresses, claim testnet QBTC from the faucet, and submit PQC hybrid transactions. The network is live and accepting peers.

**Review the code.** The full source is available at [github.com/beartec-jpg/QuantBTC](https://github.com/beartec-jpg/QuantBTC). Security researchers and cryptographers are encouraged to audit the PQC consensus rules, hybrid witness format, and key management implementation.

**Contribute.** Development is open. Phase 9 (mining infrastructure) and Phase 10 (protocol hardening) are the immediate priorities. See [ROADMAP.md](ROADMAP.md) and [CONTRIBUTING.md](CONTRIBUTING.md) for details.

---

## References

1. Shor, P. W. (1994). Algorithms for quantum computation: Discrete logarithms and factoring. *Proceedings 35th Annual Symposium on Foundations of Computer Science*, 124–134.

2. Sompolinsky, Y. & Zohar, A. (2018). *PHANTOM: A Scalable BlockDAG Protocol.* IACR Cryptology ePrint Archive, Report 2018/104.

3. National Institute of Standards and Technology. (2024). *Module-Lattice-Based Digital Signature Standard (ML-DSA).* NIST FIPS 204. https://doi.org/10.6028/NIST.FIPS.204

4. National Institute of Standards and Technology. (2024). *Stateless Hash-Based Digital Signature Standard (SLH-DSA).* NIST FIPS 205. https://doi.org/10.6028/NIST.FIPS.205

5. Bitcoin Core Developers. (2024). *Bitcoin Core v28.0.0.* https://github.com/bitcoin/bitcoin/releases/tag/v28.0

6. QBlockQ. (2024). *pqc-bitcoin: Post-Quantum Cryptography for Bitcoin Core.* https://github.com/QBlockQ/pqc-bitcoin

7. Ducas, L., Kiltz, E., Lepoint, T., Lyubashevsky, V., Schwabe, P., Seiler, G., & Stehlé, D. (2021). *CRYSTALS-Dilithium: A Lattice-Based Digital Signature Scheme.* IACR Transactions on Cryptographic Hardware and Embedded Systems, 2018(1), 238–268.

8. Kaspa. (2022). *GHOSTDAG: A greedy algorithm for PHANTOM.* https://github.com/kaspanet/kaspad

---

## Appendix A: PQC Transaction Anatomy

The following diagram illustrates the structure of a qBTC PQC hybrid transaction input witness:

```
P2WPKH Input Witness (4 elements):
┌─────────────────────────────────────────────────────────────────┐
│  Element [0]: ECDSA signature                    ~71 bytes      │
│               (secp256k1, DER-encoded, SIGHASH appended)       │
├─────────────────────────────────────────────────────────────────┤
│  Element [1]: EC public key                       33 bytes      │
│               (secp256k1, compressed)                           │
├─────────────────────────────────────────────────────────────────┤
│  Element [2]: Dilithium signature               2,420 bytes     │
│               (ML-DSA-44 / NIST FIPS 204)                      │
├─────────────────────────────────────────────────────────────────┤
│  Element [3]: Dilithium public key              1,312 bytes     │
│               (ML-DSA-44 / NIST FIPS 204)                      │
└─────────────────────────────────────────────────────────────────┘

Total raw witness data per input:  ~3,836 bytes
Virtual size (1-in / 2-out tx):    ~1,075 vB
Weight units (1-in / 2-out tx):    ~4,299 WU
Classical P2WPKH equivalent:         ~141 vB
PQC overhead factor:                  7.6× vsize / 34.9× raw
```

Both the ECDSA and Dilithium signatures are verified by the script interpreter for every input. A transaction is rejected if either signature fails verification. The 4-element witness stack is automatically detected by `HasPQCSignatures()` in `src/consensus/pqc_validation.cpp` without requiring a special witness version marker.

---

## Appendix B: Architecture Overview

The following diagram illustrates the high-level architecture of a qBTC node:

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

**PQC cryptography stack (`src/crypto/pqc/`):**
```
src/crypto/pqc/
  ml-dsa/               — Vendored ML-DSA-44 (Dilithium2) reference (NIST FIPS 204)
  sphincsplus/          — Vendored SLH-DSA-SHA2-128f (SPHINCS+) reference (NIST FIPS 205)
  ml-kem/               — Vendored ML-KEM-768 (Kyber) reference
  dilithium.cpp/h       — High-level Dilithium keygen / sign / verify API
  kyber.cpp/h           — ML-KEM-768 via liboqs
  ntru.cpp/h            — NTRU-HPS-4096-821 with Fujisaki-Okamoto transform
  frodokem.cpp/h        — FrodoKEM-976 with Fujisaki-Okamoto transform
  pqc_config.cpp/h      — PQC mode configuration system
  hybrid_key.cpp/h      — HybridKey: combined ECDSA + PQC key management
  falcon.h              — Falcon-512 stub (disabled — returns false on all ops)
  sqisign.cpp/h         — SQIsign stub (disabled — returns false on all ops)

src/dag/
  ghostdag.cpp/h        — GHOSTDAG blue/red set computation, blue_score, selected_parent
  dagtipset.cpp/h       — Tip tracking, parent selection (up to 64 parents)
  ghostdag_blockindex.h — Per-block DAG metadata (blue_score, mergeset, parents)

src/consensus/
  pqc_validation.cpp/h  — IsPQCActivated(), HasPQCSignatures() structural prechecks
```

---

## Appendix C: Network Parameters Reference

Full testnet vs. mainnet parameter comparison:

| Parameter | qbtctestnet | qbtcmain (reserved) |
|-----------|-------------|---------------------|
| CLI flag | `-qbtctestnet` | `-qbtcmain` |
| Chain type | `qbtctestnet` | `qbtcmain` |
| Magic bytes | `d1 a5 c3 b7` | `e3 b5 d7 a9` |
| P2P port | 28333 | 58333 |
| RPC port | 28332 | 58332 |
| Bech32 HRP | `qbtct` | `qbtc` |
| Address prefix (bech32) | `qbtct1...` | `qbtc1...` |
| Base58 P2PKH prefix | 120 (produces `q`) | 58 (produces `Q`) |
| Base58 P2SH prefix | 122 (produces `r`) | 60 (produces `R`) |
| Data directory | `~/.bitcoin/qbtctestnet/` | `~/.bitcoin/qbtcmain/` |
| GHOSTDAG K | 32 | 18 |
| Max DAG parents | 64 | 64 |
| Block target interval | 10 seconds | 10 seconds |
| Max block weight | 16 MB | 16 MB |
| Block reward | 0.83333333 QBTC (83,333,333 qSats) | 0.83333333 QBTC (83,333,333 qSats) |
| Halving interval | 12,600,000 blocks (~4 years) | 12,600,000 blocks (~4 years) |
| Supply cap | ~21,000,000 QBTC | ~21,000,000 QBTC |
| PQC deployment | Always active | Always active |
| DAG mode | Enabled | Enabled |
| Proof-of-work | SHA-256 | SHA-256 |
| Genesis nonce | 0 | TBD (real mining required) |
| BIP9 DEPLOYMENT_PQC | ALWAYS_ACTIVE | ALWAYS_ACTIVE |
| SCRIPT_VERIFY_PQC bit | 21 | 21 |
| BLOCK_VERSION_DAGMODE | `0x10000000` | `0x10000000` |
| Seed nodes | 46.62.156.169:28333, 37.27.47.236:28333, 89.167.109.241:28333 | TBD |
| Block explorer | beartec.uk/qbtc-scan | TBD |
| Faucet | beartec.uk/qbtc-faucet | N/A |
| Status | **Live** | **Not launched** |

---

*Copyright (c) 2026 BearTec. Licensed under BUSL-1.1 until 2030-04-09; thereafter under the MIT License. See [LICENSE-BUSL](LICENSE-BUSL) and [NOTICE](NOTICE) for full terms.*
