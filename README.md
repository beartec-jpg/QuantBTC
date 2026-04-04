# **qBTC (QuantumBTC)**

> A quantum-resistant, high-throughput blockchain built on Bitcoin Core v28.0.0.
>
> qBTC is an independent fork maintained by [beartec](https://github.com/beartec-jpg), derived from [QBlockQ/pqc-bitcoin](https://github.com/QBlockQ/pqc-bitcoin). It combines **post-quantum cryptographic signatures** with **BlockDAG consensus (GHOSTDAG)** to create a network that is secure against both classical and quantum adversaries — not as a future upgrade, but as a consensus requirement from genesis.

---

## What is qBTC?

qBTC (QuantumBTC) transforms Bitcoin Core into a quantum-safe, high-throughput blockchain while preserving Bitcoin's economic model (21M supply cap, halving schedule, SHA-256 PoW). Every transaction carries a **hybrid witness**: a classical ECDSA signature paired with a lattice-based ML-DSA-44 (Dilithium2) signature, providing dual-layer cryptographic protection.

### Key Capabilities

| Capability | Status |
|------------|--------|
| PQC hybrid transactions (ECDSA + ML-DSA-44) | ✅ |
| BlockDAG parallel block production (GHOSTDAG) | ✅ |
| Solo mining via `generatetoaddress` | ✅ |
| P2P node sync with PQC transactions | ✅ |
| Wallet operations (send, receive, encrypt) | ✅ |
| PQC-aware fee estimation | ✅ |
| RBF and CPFP support | ✅ |
| DAG-aware block validation and reorg handling | ✅ |
| Unique bech32 addresses (`qbtct1...` / `qbtc1...`) | ✅ |

---

## What Changed from pqcBitcoin

qBTC is forked from [QBlockQ/pqc-bitcoin](https://github.com/QBlockQ/pqc-bitcoin), which provided the initial PQC algorithm stubs, `HybridKey` class, `PQCConfig` system, wallet PQC key storage, and script interpreter hooks. qBTC builds significantly on top of that foundation with the following changes:

### BlockDAG Consensus (GHOSTDAG)

Replaced Bitcoin's linear chain with parallel block production via the GHOSTDAG protocol:

- **`GhostdagManager`** — computes blue scores, merge sets, and the selected parent chain
- **`DagTipSet`** — tracks concurrent DAG tips and provides mining parents
- **Multi-parent block headers** — `hashParents` field with `BLOCK_VERSION_DAGMODE` flag
- **DAG-aware validation** — parent existence checks, duplicate detection, max parents limit
- **DAG difficulty adjustment** — `GetNextWorkRequiredDAG()` for variable block spacing
- **1-second block target** with 16 MB max block weight
- **RPC fields**: `dagparents`, `dagblock`, `dagmode`, `ghostdag_k`, `dag_tips`

### Real Cryptography (ML-DSA-44)

Replaced the upstream HMAC-based placeholder stubs with production NIST reference implementations:

- **Vendored ML-DSA-44 (Dilithium2)** — NIST FIPS 204, real sign/verify wired into the script interpreter, wallet signing, and consensus (`src/crypto/pqc/ml-dsa/`)
- **Vendored SPHINCS+** (SLH-DSA-SHA2-128f) — stateless hash-based signatures (`src/crypto/pqc/sphincsplus/`)
- **Vendored ML-KEM (Kyber-768)** — lattice-based KEM (`src/crypto/pqc/ml-kem/`)
- **Single `randombytes()` implementation** using Bitcoin Core's `GetStrongRandBytes` with proper memory cleansing
- **Fixed `#define N 256` macro leakage** from Dilithium `params.h` that conflicted with Bitcoin Core symbols

### Consensus Verification

Hardened the consensus layer for real cryptographic verification:

- **`CheckPQCSignature()`** in the script interpreter performs real Dilithium verification
- **4-element PQC witness format** validated at consensus: `[ECDSA sig, EC pubkey, Dilithium sig (2420B), Dilithium pubkey (1312B)]`
- **Dedicated error codes**: `SCRIPT_ERR_PQC_VERIFY_FAILED`, `SCRIPT_ERR_PQC_WITNESS_MALFORMED`, `SCRIPT_ERR_PQC_ALGO_UNSUPPORTED`, `SCRIPT_ERR_PQC_KEY_SIZE_MISMATCH`
- **Unique chain identity** — distinct magic bytes, ports, and genesis block hashes per chain

### PQC-Aware Fee Estimation

Fixed a critical bug where the wallet calculated fees based on ECDSA-only virtual size (~141 vB) while PQC hybrid transactions are ~7.6x larger (~1,075 vB):

- `WPKHDescriptor::MaxSatSize()` returns correct PQC witness sizes when hybrid signatures are active
- `DummySignatureCreator::CreatePQCSig()` produces dummy 2420B sig + 1312B pubkey for accurate size estimation
- Coin selection now correctly accounts for PQC witness weight

### Standalone Testnet & Mainnet Parameters

- **qBTC Testnet**: magic `d1a5c3b7`, P2P port 28333, RPC port 28332, bech32 prefix `qbtct`
- **qBTC Mainnet** (reserved): magic `e3b5d7a9`, P2P port 58333, RPC port 58332, bech32 prefix `qbtc`
- PQC is **always active** on qBTC chains — no manual `-pqc=1` flag needed
- GHOSTDAG K=32 (testnet) / K=18 (mainnet)
- 0.08333333 QBTC block reward (8,333,333 satoshis), 126,000,000 block halving interval (~4 years), ~21M supply cap
- Launch script and config template at `contrib/qbtc-testnet/`

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
Classical equivalent:         ~141 vB (7.6x smaller)
```

---

## PQC Algorithms

### Digital Signature Algorithms
- **CRYSTALS-Dilithium (ML-DSA-44)** — lattice-based, NIST FIPS 204. **Primary signature algorithm used in consensus.**
- **SPHINCS+ (SLH-DSA-SHA2-128f)** — stateless hash-based signatures. Crypto primitives implemented; not yet wired to wallet signing.
- **Falcon** — stub only, not wired to a real implementation.
- **SQIsign** — stub only, not wired to a real implementation.

### Key Encapsulation Mechanisms (KEM)
- **Kyber (ML-KEM-768)** — lattice-based KEM with vendored reference implementation.
- **FrodoKEM** — LWE-based KEM.
- **NTRU** — lattice-based cryptosystem using `GetStrongRandBytes()` for key generation.

For detailed PQC documentation, see [doc/pqc.md](doc/pqc.md).

### Configuration Options

PQC is enabled by default on qBTC chains. For manual configuration:

```bash
./src/bitcoind -pqc=1 -pqcalgo=kyber,ntru -pqcsig=sphincs,dilithium -pqchybridsig=1
```

| Option | Description | Default |
|--------|-------------|---------|
| `-pqc=0\|1` | Enable/disable PQC features | `1` |
| `-pqchybridkeys=0\|1` | Enable/disable hybrid key generation | `1` |
| `-pqchybridsig=0\|1` | Enable/disable hybrid signatures | `1` |
| `-pqcalgo=algo1,algo2,...` | KEM algorithms | `kyber,frodo,ntru` |
| `-pqcsig=sig1,sig2,...` | Signature schemes | `sphincs,dilithium` |

---

## Building qBTC

### Requirements

- GCC 7+ or Clang 8+
- Autotools (autoconf, automake, libtool)
- pkg-config
- Python 3 (for tests)
- Standard Bitcoin Core dependencies (libevent, Boost, SQLite, etc.)

### Install Dependencies (Ubuntu/Debian)

```bash
sudo apt-get install build-essential libtool autotools-dev automake pkg-config bsdmainutils python3
sudo apt-get install libevent-dev libboost-dev libboost-system-dev libboost-filesystem-dev
sudo apt-get install libsqlite3-dev libminiupnpc-dev libnatpmp-dev libzmq3-dev
```

### Build

```bash
git clone https://github.com/beartec-jpg/QuantBTC.git
cd QuantBTC
./autogen.sh
./configure --with-incompatible-bdb --with-gui=no
make -j$(nproc)
```

> **Note:** The Qt GUI (`--with-gui=qt5`) currently fails to build due to Falcon/Kyber liboqs link errors. Use `--with-gui=no` for the daemon and CLI builds.

---

## Running qBTC

### Quick Start (Testnet)

```bash
# Start the qBTC testnet daemon
./src/bitcoind -qbtctestnet -daemon -fallbackfee=0.0001 -txindex=1

# Interact via CLI
./src/bitcoin-cli -qbtctestnet getblockchaininfo
./src/bitcoin-cli -qbtctestnet createwallet "mywallet"
./src/bitcoin-cli -qbtctestnet -rpcwallet=mywallet getnewaddress

# Mine blocks (regtest/testnet with trivial difficulty)
./src/bitcoin-cli -qbtctestnet -rpcwallet=mywallet generatetoaddress 10 $(./src/bitcoin-cli -qbtctestnet -rpcwallet=mywallet getnewaddress)

# Stop the daemon
./src/bitcoin-cli -qbtctestnet stop
```

### Using the Helper Script

```bash
./contrib/qbtc-testnet/qbtc-testnet.sh start     # Launch daemon
./contrib/qbtc-testnet/qbtc-testnet.sh mine 10    # Mine 10 blocks
./contrib/qbtc-testnet/qbtc-testnet.sh status     # Show blockchain info
./contrib/qbtc-testnet/qbtc-testnet.sh address    # Generate new address
./contrib/qbtc-testnet/qbtc-testnet.sh send <addr> <amount>  # Send QBTC
./contrib/qbtc-testnet/qbtc-testnet.sh stop       # Graceful shutdown
```

### Configuration

Place in `~/.bitcoin/bitcoin.conf`:

```ini
[qbtctestnet]
chain=qbtctestnet
server=1
listen=1
fallbackfee=0.0001
txindex=1
# seednode=<ip>:28333
```

A configuration template is available at `contrib/qbtc-testnet/qbtc-testnet.conf`.

### Network Parameters

| Parameter | Testnet | Mainnet (reserved) |
|-----------|---------|-------------------|
| CLI flag | `-qbtctestnet` | `-qbtcmain` |
| Magic bytes | `d1 a5 c3 b7` | `e3 b5 d7 a9` |
| P2P port | 28333 | 58333 |
| RPC port | 28332 | 58332 |
| Bech32 prefix | `qbtct` | `qbtc` |
| GHOSTDAG K | 32 | 18 |
| Block target | 1 second | 1 second |
| Max block weight | 16 MB | 16 MB |
| Block reward | 0.08333333 QBTC | 0.08333333 QBTC |
| Halving interval | 126,000,000 blocks (~4 years) | 126,000,000 blocks (~4 years) |
| Supply cap | ~21,000,000 QBTC | ~21,000,000 QBTC |
| PQC deployment | Always active | Always active |
| DAG mode | Enabled | Enabled |

### Tokenomics

QBTC uses 1-second DAG blocks, so its emission parameters are scaled to match Bitcoin's ~4-year halving cadence and ~21M total supply:

| Parameter | Bitcoin | QBTC |
|-----------|---------|------|
| Block interval | 600 s | 1 s |
| Halving interval | 210,000 blocks (~4 years) | 126,000,000 blocks (~4 years) |
| Initial block reward | 50 BTC | 0.08333333 QBTC (8,333,333 satoshis) |
| Total supply | ~21,000,000 BTC | ~21,000,000 QBTC |

#### Two-Phase Emission Model

**Phase 1 — Distribution (blocks 0 to 125,999,999 / ~4 years)**

- Empty blocks (coinbase-only) are valid and earn the full block reward.
- Anyone can mine and collect QBTC — no transaction activity is required.
- ~10,500,000 QBTC (50% of total supply) is distributed during this phase.
- This is a fair-launch distribution: hash power is the only requirement.

**Phase 2+ — Operational (block 126,000,000 onward, forever)**

- Empty blocks remain technically valid so the chain never stalls during quiet periods.
- However, empty blocks earn **zero subsidy** (fees only).
- Blocks that include at least one user transaction earn the normal halved subsidy plus fees.
- This naturally transitions the network to transaction-driven mining.

### RPC Extensions

qBTC adds several RPC fields beyond standard Bitcoin Core:

- `getblockchaininfo` — reports `pqc: true` on qBTC chains
- `getaddressinfo` — includes `pqc_enabled`, `has_pqc_key`, `pqc_algorithm`, `pqc_pubkey`
- `getpqcinfo` — returns PQC configuration status
- `gettransaction` — includes `pqc_signed` field for PQC witness detection
- Block RPCs — `dagparents`, `dagblock`, `dagmode`, `ghostdag_k`, `dag_tips`

---

## Testing

### Unit Tests

Run all unit tests (including 45+ PQC-specific test cases):

```bash
make check
```

PQC unit tests cover:

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
| `dag_tests` | — | DAG topology, GHOSTDAG ordering |

### Integration Tests

The integration test suite validates 61 assertions across 30 test groups:

```bash
./run_full_test.sh
```

Integration tests cover:
- Node identity and wallet PQC provisioning
- PQC hybrid transaction creation and signature verification
- Batch transactions and mempool behavior
- DAG parallel blocks and GHOSTDAG ordering
- Multi-hop PQC, wallet reload, multi-input transactions
- Corrupt and wrong-size witness rejection
- Sig mutation and replay protection
- Fee estimation accuracy, RBF, and CPFP
- Two-node propagation and cross-wallet verification
- Wallet encryption with PQC signing

### DAG-Specific Tests

```bash
python3 test_ghostdag.py          # GHOSTDAG block ordering
python3 test_parallel_dag.py      # Parallel block production
python3 test_dag_fork.py          # DAG reorganization
python3 test_dag_wallet.py        # Wallet PQC in DAG mode
python3 test_dag_testnet.py       # Testnet-specific scenarios
```

### Fuzz Testing

Fuzz targets for PQC primitives:

```bash
# Build with fuzzing support, then run:
# crypto_pqc_dilithium, crypto_pqc_sphincs, crypto_pqc_kyber,
# crypto_pqc_ntru, crypto_pqc_frodokem, pqc_witness
```

### Functional Tests (Bitcoin Core)

The standard Bitcoin Core functional test suite:

```bash
test/functional/test_runner.py
```

---

## Stress Test Results — 10-Node PQC Network

**Test date:** April 2026 | **Status: PASSED — 10,000/10,000 transactions**

<details open>
<summary><strong>Test Configuration</strong></summary>

| Parameter | Value |
|-----------|-------|
| Nodes | 10 |
| Wallets | 30 (3 per node) |
| Transactions | 10,000 post-quantum hybrid |
| Blocks mined | 531 |
| Total wall time | 14.7 minutes |

</details>

<details open>
<summary><strong>Transaction Performance</strong></summary>

| Metric | Value |
|--------|-------|
| Attempted | 10,000 |
| Succeeded | 10,000 (100.0%) |
| Failed | 0 |
| Confirmed on-chain | 10,061 |
| PQC hybrid txs | 10,061 (100%) |
| Classical txs | 0 |
| Effective TPS | 13.4 tx/s |

**Submit Latency**

| Stat | Value |
|------|-------|
| Mean | 58.8 ms |
| Median | 44.8 ms |
| P95 | 146.4 ms |
| P99 | 181.8 ms |
| Min | 12.9 ms |
| Max | 439.3 ms |

</details>

<details>
<summary><strong>Network & Propagation</strong></summary>

**P2P Propagation (to all 10 nodes)**

| Stat | Value |
|------|-------|
| Samples | 50 |
| Mean | 2,818 ms |
| Median | 3,126 ms |
| P95 | 4,892 ms |
| Max | 5,632 ms |

**Block Relay (miner to 9 peers)**

| Stat | Value |
|------|-------|
| Samples | 50 |
| Mean | 289 ms |
| Median | 298 ms |
| P95 | 368 ms |
| Max | 394 ms |

**Network Topology:** Each node maintained 18 peers in a full mesh. All 10 nodes synced consistently at height 531.

</details>

<details>
<summary><strong>Transaction Size & Witness Analysis</strong></summary>

| Metric | Value |
|--------|-------|
| Analyzed | 10,061 txs |
| Mean vsize | 1,479 vB |
| Median vsize | 1,075 vB |
| P95 vsize | 3,080 vB |
| Max vsize | 8,060 vB |
| Total tx data | 55.7 MB |
| 4-element PQC witness | 10,061 (100%) |
| PQC overhead vs P2WPKH | 34.9x |

</details>

<details>
<summary><strong>Fees & Cross-Node Activity</strong></summary>

| Metric | Value |
|--------|-------|
| Avg fee | 15,099 sats |
| Fee rate (mean) | 11.4 sat/vB |
| Fee rate (median) | 10.0 sat/vB |
| Est. total fees | 1.5189 QBTC |
| Cross-node txs | 9,320 (93.2%) |
| Same-node txs | 680 (6.8%) |

</details>

<details>
<summary><strong>Storage</strong></summary>

| Node | Size |
|------|------|
| Node 0 | 206 MB |
| Node 1 | 207 MB |
| Node 2 | 202 MB |
| Node 9 | 204 MB |
| **Total** | **2.0 GB** |

</details>

<details>
<summary><strong>Full Raw Test Output</strong></summary>

```
========================================================================
  qBTC 10-Node Stress Test
  10 nodes | 30 wallets | 10,000 transactions
========================================================================
[1/8] Starting 10 nodes...
  Node 0: pid=76598, p2p=28333, rpc=28332
  Node 1: pid=76599, p2p=28433, rpc=28432
  Node 2: pid=76600, p2p=28533, rpc=28532
  Node 3: pid=76601, p2p=28633, rpc=28632
  Node 4: pid=76602, p2p=28733, rpc=28732
  Node 5: pid=76603, p2p=28833, rpc=28832
  Node 6: pid=76604, p2p=28933, rpc=28932
  Node 7: pid=76605, p2p=29033, rpc=29032
  Node 8: pid=76606, p2p=29133, rpc=29132
  Node 9: pid=76607, p2p=29233, rpc=29232
  Waiting for nodes to start...
  All 10 nodes started

[2/8] Establishing mesh connectivity...
  Node 0: 18 peers
  Node 1: 18 peers
  Node 2: 18 peers
  Node 9: 18 peers
  Average peers/node: 18.0

[3/8] Creating 30 wallets (3/node)...
  Created 30 wallets across 10 nodes

[4/8] Mining initial blocks & funding wallets...
  Mining 350 blocks on node 0...
  All nodes synced at height 350
  Funding round 1: 29 wallets funded
  Funding round 2: 29 wallets funded
  Funding round 3: 29 wallets funded
  Wallet balances: miner=11374.99, min=75.00, avg=75.00 QBTC

[5/8] Running 10,000 PQC transactions across 10 nodes...
  Batch  1: 200 ok 0 fail |   200/10000 (  2.0%) | relay 0.33s | 22.5 tps |   9s
  Batch  2: 200 ok 0 fail |   400/10000 (  4.0%) | relay 0.32s | 23.4 tps |  17s
  Batch  3: 200 ok 0 fail |   600/10000 (  6.0%) | relay 0.37s | 22.4 tps |  27s
  Batch  4: 200 ok 0 fail |   800/10000 (  8.0%) | relay 0.36s | 21.3 tps |  38s
  Batch  5: 200 ok 0 fail |  1000/10000 ( 10.0%) | relay 0.34s | 21.4 tps |  47s
  ...
  Batch 25: 200 ok 0 fail |  5000/10000 ( 50.0%) | relay 0.28s | 16.3 tps | 307s
  ...
  Batch 50: 200 ok 0 fail | 10000/10000 (100.0%) | relay 0.29s | 13.4 tps | 746s

[6/8] Final mining and sync...
  All 10 nodes synced at height 531

[7/8] Analyzing on-chain transactions (scanning ~181 blocks)...

========================================================================
  MULTI-NODE 10K STRESS TEST REPORT
========================================================================
-- Network Topology --
  Nodes: 10
  Wallets: 30 (3/node)
  All nodes: height=531, peers=18, mempool=26

-- Transaction Summary --
  Attempted: 10,000
  Succeeded: 10,000 (100.0%)
  Confirmed on-chain: 10,061
  PQC hybrid txs: 10,061 | Classical: 0

-- Timing --
  Total wall time: 880s (14.7m)
  TX phase time: 746s (12.4m)
  Effective TPS: 13.4 tx/s
  Submit latency -- Mean: 58.8ms, Median: 44.8ms, P95: 146.4ms

-- P2P Propagation --
  Mean: 2818ms | Median: 3126ms | P95: 4892ms

-- Block Relay --
  Mean: 289ms | Median: 298ms | P95: 368ms

-- Witness Analysis --
  4-element (PQC): 10,061 (100.0%)
  PQC overhead: 34.9x vs classical P2WPKH

-- Cross-Node Activity --
  Cross-node txs: 9,320 (93.2%)
  Same-node txs: 680 (6.8%)

========================================================================
  TEST PASSED
  10,000/10,000 txs | 10 nodes | 531 blocks | 14.7m
========================================================================
```

</details>

---

## Architecture

```
+-----------------------------------------------------------+
|                      qBTC Node                            |
+--------------+--------------+-----------------------------+
|   Wallet     |   Mempool    |   Block Validation          |
|  +--------+  |              |  +---------------------+    |
|  |Hybrid  |  |  fee-rate    |  | VerifyScript()      |    |
|  |Key Mgmt|  |  estimation  |  |  +- CheckSig(ECDSA) |    |
|  |ECDSA + |  |  (PQC-aware) |  |  +- CheckPQCSig()   |    |
|  |ML-DSA  |  |              |  |      (ML-DSA-44)    |    |
|  +--------+  |              |  +---------------------+    |
+--------------+--------------+-----------------------------+
|              GHOSTDAG Consensus Engine                     |
|  +----------+  +----------+  +--------------------+       |
|  | Blue     |  | Merge    |  | Selected Parent    |       |
|  | Score    |  | Set      |  | Chain              |       |
|  | Compute  |  | Ordering |  | (virtual backbone) |       |
|  +----------+  +----------+  +--------------------+       |
+-----------------------------------------------------------+
|              Network Layer (P2P)                           |
|  Testnet: Magic d1a5c3b7 | Port 28333 | HRP qbtct         |
|  Mainnet: Magic e3b5d7a9 | Port 58333 | HRP qbtc          |
+-----------------------------------------------------------+
```

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for the full development history and planned phases, including:

- **Phase 8** — Public testnet with seed nodes, DNS seeds, and block explorer
- **Phase 9** — Mining infrastructure (Stratum v2, pool protocol)
- **Phase 10** — Protocol hardening (SPHINCS+ wallet signing, ML-KEM for P2P, security audit)
- **Phase 11** — Mainnet preparation (genesis block, release binaries)

---

## Contributing

We welcome contributions to qBTC. Feel free to fork this repository and submit pull requests.

For discussions and issues, please open an issue on the [GitHub repository](https://github.com/beartec-jpg/QuantBTC/issues).

See [CONTRIBUTING.md](CONTRIBUTING.md) for contribution guidelines.

---

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.

qBTC is forked from [QBlockQ/pqc-bitcoin](https://github.com/QBlockQ/pqc-bitcoin), originally created by [QBlock](https://github.com/QBlockQ) & [Qbits](https://github.com/QbitsCode), which is itself based on [Bitcoin Core](https://github.com/bitcoin/bitcoin).
