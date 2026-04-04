# **QuantumBTC — beartec's Fork**

> **⚠️ All changes in this repository are [beartec's](https://github.com/beartec-jpg) version of QuantumBTC.**
> This is an independent fork maintained by beartec. The stress test results below represent the first comprehensive multi-node validation of this build.

---

## 🧪 First Stress Test Results — 10-Node PQC Network

**Test date:** April 2026 &nbsp;|&nbsp; **Status: ✅ PASSED — 10,000/10,000 transactions**

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

**Block Relay (miner → 9 peers)**

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
| PQC overhead vs P2WPKH | 34.9× |

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
  QuantumBTC 10-Node Stress Test
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
  All 10 nodes started ✓

[2/8] Establishing mesh connectivity...
  Node 0: 18 peers
  Node 1: 18 peers
  Node 2: 18 peers
  Node 9: 18 peers
  Average peers/node: 18.0

[3/8] Creating 30 wallets (3/node)...
  Created 30 wallets across 10 nodes ✓

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
── Network Topology ─────────────────────────────────────────
  Nodes: 10
  Wallets: 30 (3/node)
  All nodes: height=531, peers=18, mempool=26

── Transaction Summary ──────────────────────────────────────
  Attempted: 10,000
  Succeeded: 10,000 (100.0%)
  Confirmed on-chain: 10,061
  PQC hybrid txs: 10,061 | Classical: 0

── Timing ──────────────────────────────────────────────────
  Total wall time: 880s (14.7m)
  TX phase time: 746s (12.4m)
  Effective TPS: 13.4 tx/s
  Submit latency — Mean: 58.8ms, Median: 44.8ms, P95: 146.4ms

── P2P Propagation ─────────────────────────────────────────
  Mean: 2818ms | Median: 3126ms | P95: 4892ms

── Block Relay ─────────────────────────────────────────────
  Mean: 289ms | Median: 298ms | P95: 368ms

── Witness Analysis ────────────────────────────────────────
  4-element (PQC): 10,061 (100.0%)
  PQC overhead: 34.9x vs classical P2WPKH

── Cross-Node Activity ─────────────────────────────────────
  Cross-node txs: 9,320 (93.2%)
  Same-node txs: 680 (6.8%)

========================================================================
  TEST PASSED
  10,000/10,000 txs | 10 nodes | 531 blocks | 14.7m
========================================================================
```

</details>

---

## **About this fork**

QuantumBTC is a fork-in-progress of pqcBitcoin focused on combining post-quantum transaction security with high-throughput BlockDAG consensus while preserving Bitcoin-style economics.

This fork is being adapted with these goals:

- **Quantum-safe signatures** via the existing PQC integration from pqcBitcoin.
- **SHA-256 Proof of Work** retained for compatibility with established Bitcoin mining hardware assumptions.
- **BlockDAG / GHOSTDAG-style consensus** to support fast parallel block production, sub-second confirmation targets, and materially higher throughput than linear-chain Bitcoin.
- **Bitcoin-like monetary policy** including the 21 million supply cap and halving-based issuance model.

Current work in this fork includes introducing DAG-specific data structures, multi-parent block support, DAG-oriented mining hooks, and consensus parameter extensions needed to bring up a usable regtest-first QuantumBTC node.

This repository is the result of a collaborative effort between [QBlock](https://github.com/QBlockQ) & [Qbits](https://github.com/QbitsCode), working together to build a future-proof version of Bitcoin Core that can withstand the potential threats posed by quantum computers. The integration of Post-Quantum Cryptography (PQC) algorithms into Bitcoin Core is a key initiative in ensuring that Bitcoin remains secure in the advent of quantum computing.

Quantum computing represents a breakthrough in computational capabilities, but it also poses a significant risk to current cryptographic techniques, including the elliptic curve cryptography (ECC) widely used in Bitcoin today. These classical encryption methods could potentially be broken by powerful quantum computers, leading to vulnerabilities in blockchain technologies. To mitigate this, the integration of quantum-resistant algorithms into Bitcoin Core is imperative.

## **Overview**

Quantum computers poses a potential threat to current cryptographic methods, including those used in Bitcoin, like elliptic curve cryptography (ECC). This project investigates incorporating post-quantum cryptographic algorithms to secure Bitcoin transactions and wallets in the event of future quantum attacks.

The goal is to make Bitcoin Core quantum-resistant by adopting algorithms that remain secure even in a world with powerful quantum computers.

## **Features**

- **Integration of PQC Algorithms**: Implements quantum-safe cryptographic algorithms alongside existing Bitcoin protocols.
- **Quantum-Resistant Wallets**: Modify Bitcoin Core's wallet functionality to utilize PQC keys for enhanced security.
- **Backward Compatibility**: Maintain compatibility with Bitcoin's current cryptographic algorithms for users not yet ready to switch to PQC.

## **Current PQC Algorithms Implemented**

### Group 1: Digital Signature Algorithms
- **SPHINCS+**: A stateless hash-based signature scheme with minimal security assumptions.
- **CRYSTALS-Dilithium**: A lattice-based digital signature scheme.
- **FALCON**: A fast lattice-based digital signature scheme optimized for small signatures.
- **SQIsign**: An isogeny-based signature scheme.

### Group 2: Key Encapsulation Mechanisms (KEM)
- **Kyber**: A lattice-based key encapsulation mechanism (KEM) for public-key encryption.
- **FrodoKEM**: A key encapsulation mechanism based on the hardness of the learning with errors (LWE) problem.
- **NTRU**: A lattice-based public-key cryptosystem designed to be secure against quantum computers.

These algorithms are integrated into the Bitcoin codebase in a way that ensures both backward and forward compatibility with existing Bitcoin infrastructure. Group 1 algorithms handle digital signatures for transaction signing, while Group 2 algorithms provide secure key exchange mechanisms for encrypted communications between nodes and wallets.

## **Post-Quantum Cryptography Support**

This fork of Bitcoin Core implements post-quantum cryptography (PQC) to provide protection against quantum computer attacks while maintaining backward compatibility with the existing Bitcoin network.

### **Implemented PQC Features**

#### Key Management System
- HybridKey class for managing both classical and PQC keys
- Integration with Bitcoin's existing key management system
- Support for hybrid key generation and signing

#### Supported PQC Algorithms
##### Digital Signatures (Group 1)
- **SPHINCS+**: Stateless hash-based signatures
- **CRYSTALS-Dilithium**: Lattice-based signatures
- **FALCON**: Fast lattice-based signatures
- **SQIsign**: Isogeny-based signatures

##### Key Encapsulation (Group 2)
- **Kyber**: Lattice-based KEM
- **FrodoKEM**: LWE-based KEM
- **NTRU**: Lattice-based cryptosystem

#### Configuration Options
Enable PQC features using command-line arguments:
```bash
bitcoind -pqc=1 -pqcalgo=kyber,ntru -pqcsig=sphincs,dilithium -pqchybridsig=1
```

Available options:
- `-pqc=0|1`: Enable/disable all PQC features (default: 1)
- `-pqchybridkeys=0|1`: Enable/disable hybrid key generation (default: 1)
- `-pqchybridsig=0|1`: Enable/disable hybrid signatures (default: 1)
- `-pqcalgo=algo1,algo2,...`: Specify enabled KEM algorithms (default: kyber,frodo,ntru)
- `-pqcsig=sig1,sig2,...`: Specify enabled signature schemes (default: sphincs,dilithium,falcon,sqisign)

For detailed documentation on PQC features, see [doc/pqc.md](doc/pqc.md).

## **Installation**

To build and test the PQC-enabled Bitcoin Core:

### Build Requirements

* GCC 7+ or Clang 8+
* CMake 3.13+
* OpenSSL 1.1+
* Boost 1.70+
* Additional PQC-specific requirements:
  - PQCRYPTO-NIST library (for Kyber and NTRU)
  - FrodoKEM reference implementation

### Build Steps

1. Install dependencies:
```bash
# Ubuntu/Debian
sudo apt-get install build-essential libtool autotools-dev automake pkg-config bsdmainutils python3
sudo apt-get install libevent-dev libboost-dev libboost-system-dev libboost-filesystem-dev
sudo apt-get install libsqlite3-dev libminiupnpc-dev libnatpmp-dev libzmq3-dev
sudo apt-get install libqt5gui5 libqt5core5a libqt5dbus5 qttools5-dev qttools5-dev-tools

# Install PQC dependencies
git clone https://github.com/PQClean/PQClean.git
cd PQClean && make
sudo make install
```

2. Clone and build:
```bash
git clone https://github.com/QBlockQ/pqc-bitcoin.git
cd pqc-bitcoin
./autogen.sh
./configure --with-pqc
make
make check  # Run tests
```

3. Run with PQC features:
```bash
./src/bitcoind -pqc=1 -pqcalgo=kyber,ntru -pqchybridsig=1
```

## Run PQC Bitcoin Core

After building Bitcoin Core, you can run the PQC-enabled Bitcoin Core in regtest mode for testing
```bash
./src/bitcoind -regtest
```

## Testing PQC Bitcoin

The test framework ensures that the PQC algorithms integrate smoothly with Bitcoin Core’s existing features.
For detailed testing instructions, refer to the Bitcoin Test Suite.

## To run tests:
```bash
make check
```

## Validate PQC Key Generation: 

Test key generation using PQC algorithms

```bash
./src/bitcoin-cli pqc-keygen
```

## Contributions

We welcome contributions to make Bitcoin Core quantum-resistant. Feel free to fork this repository and submit pull requests.

For discussions and issues, please open an issue on the GitHub repository.

## License

This project is licensed under the MIT License. **Made with love by [QBlock](https://github.com/QBlockQ) & [Qbits](https://github.com/QbitsCode))** 💖
