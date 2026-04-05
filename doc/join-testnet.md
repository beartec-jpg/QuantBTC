# Joining the QuantumBTC Public Testnet

## Overview

The QuantumBTC testnet (`qbtctestnet`) is a live BlockDAG network running
GHOSTDAG consensus with post-quantum cryptographic (PQC) hybrid signatures.
Anyone can join, sync, mine, and send transactions.

| Property | Value |
|---|---|
| Network name | `qbtctestnet` |
| P2P port | 28333 |
| RPC port | 28332 |
| Block target | ~1 second |
| GHOSTDAG K | 32 |
| PQC algorithm | ML-DSA-44 (Dilithium) hybrid |
| Ticker | QBTC |

## Seed Nodes

| # | IP Address | P2P Port |
|---|---|---|
| S1 | 46.62.156.169 | 28333 |
| S2 | 37.27.47.236 | 28333 |
| S3 | 89.167.109.241 | 28333 |

## Quick Start

### 1. Build from Source

```bash
git clone https://github.com/QBlockQ/pqc-bitcoin.git
cd pqc-bitcoin

./autogen.sh
./configure --disable-wallet --without-gui
# Or with wallet support (requires BDB 4.8):
# ./configure --with-incompatible-bdb

make -j$(nproc)
```

### 2. Configure

Create `~/.bitcoin/bitcoin.conf`:

```ini
# Network selection
qbtctestnet=1

# RPC
server=1
rpcuser=<choose_a_username>
rpcpassword=<choose_a_strong_password>
rpcallowip=127.0.0.1

# PQC
pqc=1
pqcmode=hybrid

# DAG
dag=1
txindex=1

# Seed nodes
addnode=46.62.156.169:28333
addnode=37.27.47.236:28333
addnode=89.167.109.241:28333

[qbtctestnet]
port=28333
rpcport=28332
```

### 3. Start the Node

```bash
./src/bitcoind -daemon
```

Monitor sync progress:

```bash
CLI="./src/bitcoin-cli -conf=$HOME/.bitcoin/bitcoin.conf"
$CLI getblockchaininfo
```

Wait for `"initialblockdownload": false` before mining.

### 4. Create a Wallet and Start Mining

```bash
$CLI createwallet "miner"
ADDR=$($CLI -rpcwallet=miner getnewaddress)
echo "Mining to: $ADDR"

# Mine continuously
while true; do
    $CLI generatetoaddress 1 "$ADDR" 999999999
done
```

### 5. Check PQC Status

```bash
$CLI -rpcwallet=miner getpqcinfo
$CLI getpqcsigcachestats
```

## Monitoring

### Block & DAG status

```bash
$CLI getblockchaininfo     # chain height, dagmode, ghostdag_k
$CLI getchaintips          # active tips (should be 1 in steady state)
$CLI getpeerinfo           # connected peers
```

### Signature cache performance

```bash
$CLI getpqcsigcachestats
```

Fields: `ecdsa_hits`, `ecdsa_misses`, `ecdsa_hit_rate`, `dilithium_hits`,
`dilithium_misses`, `dilithium_hit_rate`. A healthy synced node should
show > 50 % hit rate for both ECDSA and Dilithium.

### DAG block details

```bash
HASH=$($CLI getbestblockhash)
$CLI getblockheader "$HASH"
# Look for: dagblock, dagparents, blue_score fields
```

## Minimum System Requirements

| Component | Minimum | Recommended |
|---|---|---|
| CPU | 2 cores | 4+ cores |
| RAM | 2 GB | 4+ GB |
| Disk | 10 GB SSD | 50 GB SSD |
| Network | 10 Mbps | 50+ Mbps |

## Difficulty & Mining Notes

- Difficulty starts very low and adjusts per-block.
- With SHA-256 PoW, you can mine with CPU on testnet.
- ASICs/GPUs will cause difficulty to climb rapidly.
- The DAG ensures small miners' blocks are included (blue) alongside
  larger miners — blocks are not orphaned if anticone < K=32.
- Monitor your block's inclusion with `getblockheader` — check
  `dagblock: true` and that the block shows up in the chain.

## Troubleshooting

| Issue | Solution |
|---|---|
| Node won't sync | Check `addnode` entries, verify firewall allows port 28333 |
| `high-hash` errors | You're connected to a node running older code; update both |
| Mining returns empty | Set `max_tries=999999999` in `generatetoaddress` |
| Wallet not found | `createwallet "miner"` or `loadwallet "miner"` first |
| PQC keys = 0 | Ensure `pqc=1` and `pqcmode=hybrid` in config |

## Links

- Repository: https://github.com/QBlockQ/pqc-bitcoin
- GHOSTDAG design: [doc/ghostdag.md](ghostdag.md)
- PQC documentation: [doc/pqc.md](pqc.md)
