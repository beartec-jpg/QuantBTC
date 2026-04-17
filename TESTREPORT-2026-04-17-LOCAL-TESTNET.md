# QuantBTC Local Testnet Simulation Report
**Date:** 2026-04-17  
**Duration:** 192 seconds (~3.2 minutes, fast mode)  
**Script:** `test_local_testnet.py --fast`  
**Result:** ✅ 30/30 checks passed — ALL CHECKS PASSED

---

## Test Configuration

| Parameter | Value |
|-----------|-------|
| Mode | `--fast` (accelerated phase durations) |
| Nodes | 5 (regtest, localhost) |
| Wallets | 25 (5 per node) |
| PQC Scheme | Falcon-padded-512 (NIST Level 1, 128-bit PQ) |
| Network | Regtest (isolated, no external connectivity) |
| RPC Ports | 19801–19805 |
| P2P Ports | 19901–19905 |
| Chain | 222 blocks at end of test |

---

## Test Phases

### Phase 0 — Node 1 Bootstrap
Node 1 started on regtest with Falcon-512 PQC signatures enabled (`-pqcsig=falcon`). A mining wallet was created and 200 blocks were mined to fund the initial wallet and satisfy the coinbase maturity window (100 blocks). All blocks were produced and validated using Falcon-padded-512 signatures.

**Result:** ✅ Node 1 RPC responsive, height=200

---

### Phase 1–4 — Gradual Node Join (Nodes 2–5)
Nodes 2, 3, 4, and 5 joined the network sequentially. Each new node:
1. Started with identical PQC configuration
2. Connected to Node 1 via `addnode`
3. Synced the chain via IBD (Initial Block Download)
4. Had 5 wallets created with Falcon-512 key generation
5. Was funded by Node 1 via `sendtoaddress` from the primary mining wallet
6. Node 1 mined 2 additional blocks to confirm funding transactions

Each wallet received a Genesis funding transaction confirmed in the block immediately after it joined. All nodes synced the new blocks from Node 1.

**Results:**
| Node | Height at Join | Peers | Status |
|------|---------------|-------|--------|
| Node 2 | 202 | 1 | ✅ synced |
| Node 3 | 204 | 1 | ✅ synced |
| Node 4 | 206 | 1 | ✅ synced |
| Node 5 | 208 | 1 | ✅ synced |

All 5 nodes in sync: **1 unique tip hash** across the network.

---

### Phase 5 — Wallet Funding Verification
All 25 wallets (5 nodes × 5 wallets each) verified to have balance > 0.005 BTC.

**Result:** ✅ 25/25 wallets funded

---

### Phase 6 — 60-Second Transaction Storm
All 5 miners and 25 wallets ran concurrently:
- **5 concurrent miners**: Each node mined blocks continuously to its own Falcon-512 address
- **25 wallets transacting**: Each wallet sent transactions to a random peer wallet every ~3 seconds
- **Cross-node transfers**: Transactions sent between wallets on different nodes, propagated via P2P mempool relay

**Storm results:**
| Metric | Value |
|--------|-------|
| Blocks produced | 12 |
| Transactions confirmed | 29 |
| Mempool at t+30s | 4 pending |
| Chain height at end | 222 |
| All nodes consensus | ✅ single tip |

---

### Phase 7 — Final Assertions

| Check | Result |
|-------|--------|
| Blocks produced during storm | ✅ 12 blocks |
| Transactions sent during storm | ✅ 29 txs |
| All 5 nodes agree on chain tip | ✅ `61ce62d86e9901bc…` |
| Node 1 alive (height=222, peers=4) | ✅ |
| Node 2 alive (height=222, peers=1) | ✅ |
| Node 3 alive (height=222, peers=1) | ✅ |
| Node 4 alive (height=222, peers=1) | ✅ |
| Node 5 alive (height=222, peers=1) | ✅ |
| Wallets with transaction history | ✅ 25/25 |
| Node 1 getpqcinfo (scheme=falcon, nist_level=1) | ✅ |
| Node 2 getpqcinfo (scheme=falcon, nist_level=1) | ✅ |
| Node 3 getpqcinfo (scheme=falcon, nist_level=1) | ✅ |
| Node 4 getpqcinfo (scheme=falcon, nist_level=1) | ✅ |
| Node 5 getpqcinfo (scheme=falcon, nist_level=1) | ✅ |

---

## Full Check Summary

```
✓ Node 1 starts              [rpc responsive]
✓ Initial 200 blocks mined   [height=200]
✓ Node 2 starts              [rpc responsive]
✓ Node 2 synced              [height=202]
✓ Node 2 has peers           [peers=1]
✓ Node 3 starts              [rpc responsive]
✓ Node 3 synced              [height=204]
✓ Node 3 has peers           [peers=1]
✓ Node 4 starts              [rpc responsive]
✓ Node 4 synced              [height=206]
✓ Node 4 has peers           [peers=1]
✓ Node 5 starts              [rpc responsive]
✓ Node 5 synced              [height=208]
✓ Node 5 has peers           [peers=1]
✓ All 5 nodes in sync        [1 unique tip hashes]
✓ Wallets funded (>0.005 BTC)[25/25 have balance]
✓ Blocks produced during storm [12 blocks]
✓ Transactions sent during storm [29 txs]
✓ All 5 nodes agree on chain tip [tip=61ce62d86e9901bc...]
✓ Node 1 alive at end        [height=222, peers=4]
✓ Node 2 alive at end        [height=222, peers=1]
✓ Node 3 alive at end        [height=222, peers=1]
✓ Node 4 alive at end        [height=222, peers=1]
✓ Node 5 alive at end        [height=222, peers=1]
✓ Wallets with transaction history [25/25]
✓ Node 1 getpqcinfo          [scheme=falcon nist_level=1]
✓ Node 2 getpqcinfo          [scheme=falcon nist_level=1]
✓ Node 3 getpqcinfo          [scheme=falcon nist_level=1]
✓ Node 4 getpqcinfo          [scheme=falcon nist_level=1]
✓ Node 5 getpqcinfo          [scheme=falcon nist_level=1]

30/30 checks passed
ALL CHECKS PASSED
```

---

## Bugs Fixed During Development

### Bug 1: Node P2P Bind Conflict
**Symptom:** Nodes 2–5 crashed immediately with `Unable to bind to 127.0.0.1:18445`.  
**Cause:** `-port=X` sets the advertised port but does not suppress the default regtest bind on port 18445. All nodes competed for the same port.  
**Fix:** Added `-bind=127.0.0.1:{p2p_port}` to each node's startup arguments.

### Bug 2: `IsPQCWitness()` Missing Falcon — Critical Consensus Bug
**Symptom:** `generatetoaddress` failed with `CreateNewBlock: TestBlockValidity failed: bad-pqc-witness, Input 0: invalid PQC witness element sizes` whenever Falcon-signed transactions were in the mempool.  
**Cause:** `pqc_validation.cpp::IsPQCWitness()` enumerated only Dilithium (sig=2420B, pk=1312B) and SPHINCS+ (sig=17088B, pk=32B) witness sizes. Falcon-512 (sig=666B, pk=897B) and Falcon-1024 (sig=1280B, pk=1793B) were absent. Any Falcon-signed mempool transaction caused block template validation to fail.  
**Note:** Coinbase-only mining was unaffected (coinbase transactions have no witness inputs).  
**Fix:** Added Falcon-512 and Falcon-1024 size entries to `IsPQCWitness()` in `src/consensus/pqc_validation.cpp`, with `#include <crypto/pqc/falcon.h>` using the canonical size constants.

---

## PQC Configuration Verified

All nodes reported consistent PQC configuration via `getpqcinfo`:

```json
{
  "scheme": "falcon",
  "variant": "falcon-padded-512",
  "nist_level": "1",
  "security_bits_quantum": 128,
  "pubkey_size": 897,
  "sig_size": 666
}
```

Falcon-1024 (NIST Level 5, 256-bit PQ) is available as a future upgrade path via `-pqcsig=falcon1024` and was not activated in this test.

---

## Conclusion

The QuantBTC 5-node local testnet simulation completed successfully in **192 seconds** with all **30/30 checks passing**. The network demonstrated:

- Correct node bootstrapping and peer discovery
- Falcon-512 PQC key generation across 25 wallets
- Block production and IBD sync across a growing network
- Cross-node transaction propagation and mempool relay
- 60-second concurrent mining and transaction storm with consensus maintained
- All nodes converging to a single chain tip after the storm
- Correct `getpqcinfo` responses confirming Falcon-512 NIST Level 1 configuration on every node
