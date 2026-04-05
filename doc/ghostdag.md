# GHOSTDAG BlockDAG Consensus in QuantumBTC

## Overview

QuantumBTC extends Bitcoin Core's linear chain with a BlockDAG
(Directed Acyclic Graph) layer based on the GHOSTDAG/PHANTOM protocol
(Sompolinsky & Zohar, 2018; Kaspa variant).  Each block may reference
multiple parent blocks (the current tips of the DAG), and the GHOSTDAG
algorithm assigns every block a **blue score**, classifying it as *blue*
(honest / selected sub-DAG) or *red* (off-chain / conflicting).

Key parameters live in `Consensus::Params` (`src/consensus/params.h`):

| Parameter             | qbtcmain | regtest | Meaning |
|-----------------------|----------|---------|---------|
| `ghostdag_k`          | 32       | 32      | Max anticone size for a blue block |
| `nDagTargetSpacingMs` | 1000     | 1000    | Target block interval (ms) |
| `nMaxDagParents`      | 64       | 64      | Max parent references per block |

Source files:

- `src/dag/ghostdag.h / .cpp` — GHOSTDAG algorithm (blue set, scoring)
- `src/dag/dagtipset.h / .cpp` — tip-set management, parent selection
- `src/primitives/block.h / .cpp` — `CBlockHeader` with `hashParents`
- `src/chain.h` — `CBlockIndex::vDagParents`, `CDiskBlockIndex::hashDagParents`
- `src/node/blockstorage.cpp` — `LoadBlockIndexGuts` (DAG parent restoration)
- `src/validation.cpp` — GHOSTDAG scoring during `AcceptBlock` / `ConnectTip`

---

## Block-Hash Design: 80-byte Identity

### The Rule

**`GetHash()` hashes only the 80-byte base header** (nVersion, hashPrevBlock,
hashMerkleRoot, nTime, nBits, nNonce).  DAG parent hashes (`hashParents`)
are **not** included in the block-identity hash or the PoW hash.

This is the single most important invariant in the DAG layer.

### Why

Including `hashParents` in `GetHash()` caused a critical restart-instability
bug (fixed in commit `74ab011`).  The failure cascade was:

1. `CBlockHeader::GetHash()` hashed 80 bytes **plus** serialized hashParents.
2. `CDiskBlockIndex` did **not** persist `hashParents` to LevelDB.
3. On restart, `LoadBlockIndexGuts` reconstructed the block index from disk —
   but `hashParents` was empty, so `ConstructBlockHash()` produced a
   different hash than the hash recorded before shutdown.
4. Every block's *identity* changed.  `mapBlockIndex` lookups failed,
   `GetAncestor` assertions fired, and nodes could not sync with peers
   that had never restarted.

The fix was twofold:

- `GetHash()` now hashes **only** the classic 80-byte header (matching
  Bitcoin Core's original behaviour and PoW verification).
- `CDiskBlockIndex` now serializes `hashDagParents` so that
  `LoadBlockIndexGuts` can restore `vDagParents` pointers on startup.

### Where the Invariant is Enforced

| Location | What it does |
|---|---|
| `CBlockHeader::GetHash()` (`block.cpp`) | Hashes 80 bytes only |
| `CDiskBlockIndex::ConstructBlockHash()` (`chain.h`) | Rebuilds the same 80-byte hash from on-disk fields |
| `CBlockHeader::SERIALIZE_METHODS` (`block.h`) | Serializes `hashParents` for the wire but **not** for hashing |

### WARNING for Future Contributors

> **Do NOT re-introduce `hashParents` into `GetHash()` or
> `ConstructBlockHash()`.  Doing so will re-create the restart-identity-
> drift bug described above.  DAG parent references are auxiliary data —
> they feed GHOSTDAG ordering but are not part of block identity.**

---

## hashDagParents: Auxiliary Persistence

`CDiskBlockIndex::hashDagParents` stores the parent hashes on disk so
that `vDagParents` (the pointer vector in `CBlockIndex`) can be
reconstructed on startup without re-downloading full blocks.

Serialization is conditional on `BLOCK_VERSION_DAGMODE`:

```cpp
if (nVersion & CBlockHeader::BLOCK_VERSION_DAGMODE) {
    READWRITE(obj.hashDagParents);
}
```

On load (`LoadBlockIndexGuts` in `src/node/blockstorage.cpp`), each hash
in `hashDagParents` is resolved to a `CBlockIndex*` via
`insertBlockIndex()`, and the resulting pointers populate
`CBlockIndex::vDagParents`.

---

## GHOSTDAG K = 32: Design and Monitoring

### Why K = 32

Kaspa uses K = 18.  QuantumBTC uses K = 32 for broader inclusivity —
a higher K means more concurrent blocks can be classified as "blue" per
round, so small / solo miners are less likely to be orphaned.  Combined
with a 1-second target interval, this creates a "People's Chain" where
home miners see blocks accepted alongside pool blocks.

### Expected Behaviour

With K = 32 and 1-second targets, the network can tolerate up to ~32
concurrent block arrivals per round without any of them being red-
classified.  Under normal hashrate distribution (< 32 blocks per
second), nearly all blocks will be blue.

### What to Monitor

As hashrate increases, watch these metrics (available via `getblock` /
`getblockheader` with `verbosity >= 2`, and `getdagstatus`):

| Metric | Healthy Range | Concern Threshold |
|---|---|---|
| **Anticone size** (per block) | 0–20 | Consistently > 28 (approaching K) |
| **Red block ratio** | < 5 % | > 15 % sustained |
| **Blue score growth rate** | ~1 per second | Stalling or erratic |
| **Tip-set size** | 1–10 | Persistently > 30 |

If anticone sizes regularly approach K = 32, consider:

1. **Reducing target interval** (increase `nDagTargetSpacingMs`).
2. **Increasing K** (raises tolerance but weakens the 50 % honest-
   majority security assumption).
3. **Improving relay latency** (compact block relay, FIBRE-style).

### Anti-Monopolisation via Early-Protection Weight

QuantumBTC adds "Early Protection" weight to prevent a single miner
from dominating the DAG.  See `CBlockIndex::nEarlyProtectionWeight` and
the consensus rules in `validation.cpp`.

---

## PQC Signature Cache and Performance

### Verification Overhead

ML-DSA-44 (Dilithium) hybrid witnesses contain ~3.7 kB of PQC data per
input (2420-byte signature + 1312-byte public key).  Raw verification is
approximately **35× slower** than ECDSA (`secp256k1_ecdsa_verify`).

### Signature Cache

The `SignatureCache` (in `src/script/sigcache.h`) caches verified
Dilithium signatures alongside ECDSA and Schnorr entries in a single
`CuckooCache`.  A block accepted into the mempool has its signatures
cached; when the same transaction appears in a mined block, the cache
avoids re-verifying the expensive PQC signature.

Cache operations for Dilithium:

- `ComputeEntryDilithiumRaw()` — hashes `(pqc_sig, pqc_pubkey,
   ecdsa_sig, scriptCode, sigversion)` with a salted hasher (padding
   byte `'D'`).
- `CachingTransactionSignatureChecker::CheckDilithiumSignature()` —
   checks the cache before falling back to full ML-DSA verification.

### Monitoring Cache Hit Rates

Use the `getpqcsigcachestats` RPC to retrieve real-time counters:

```
$ bitcoin-cli getpqcsigcachestats
{
  "dilithium_hits": 4821,
  "dilithium_misses": 1203,
  "dilithium_hit_rate": 0.8003,
  "ecdsa_hits": 51023,
  "ecdsa_misses": 12840,
  "ecdsa_hit_rate": 0.7990
}
```

A healthy hit rate on a synced node should be > 50 % (most transactions
are verified once at mempool acceptance, then hit the cache at block
connection).  If the Dilithium hit rate is persistently low:

- The signature cache may be too small (`-maxsigcachesize`).
- Block templates may contain transactions not previously seen in the
  mempool (out-of-order relay, compact block reconstruction).

---

## Consensus Activation

DAG mode is activated per-chain via `fDagMode = true` in `CChainParams`.
The `BLOCK_VERSION_DAGMODE` flag (`1 << 28`) is set in the block version
by the miner when DAG mode is active.

PQC verification is controlled by BIP 9 deployment `DEPLOYMENT_PQC`
(bit 3), which is `ALWAYS_ACTIVE` on regtest and qbtcmain.

---

## References

- Sompolinsky, Y. & Zohar, A. (2018). *PHANTOM: A Scalable BlockDAG Protocol.*
- Kaspa project — reference GHOSTDAG implementation.
- NIST FIPS 204 — ML-DSA (Dilithium) digital signature standard.
- Commit `74ab011` — "fix: stabilize block hash and persist DAG parents across restarts"
