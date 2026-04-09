# QuantumBTC Testnet

**QuantumBTC testnet** is a standalone blockchain network for testing quantum-safe transactions and BlockDAG consensus before mainnet deployment.

## Features

| Feature | Specification |
|---------|---------------|
| **Network** | Independent chain (not a Bitcoin testnet fork) |
| **Consensus** | GHOSTDAG (K=32, 10-second blocks) |
| **PQC** | ML-DSA-44 hybrid signatures (always active) |
| **Port** | 28333 (P2P), 28332 (RPC) |
| **Address prefix** | `qbtct1...` (bech32) |
| **Base58 prefix** | `q...` (P2PKH), `r...` (P2SH) |
| **Block reward** | 0.83333333 QBTC (83,333,333 qSats) |
| **Max block weight** | 16 MB |
| **Difficulty** | Trivial (easy solo mining) |
| **Magic bytes** | `d1 a5 c3 b7` |

## Quick Start

### One-Command Join

The fastest way to join the testnet:

```bash
git clone https://github.com/beartec-jpg/QuantBTC.git
cd QuantBTC
./contrib/qbtc-testnet/join-testnet.sh
```

This installs dependencies, builds from source, configures seed nodes,
starts the daemon, and creates a wallet with a mining address.

### Docker

```bash
git clone https://github.com/beartec-jpg/QuantBTC.git
cd QuantBTC
docker build -t qbtc-testnet -f contrib/qbtc-testnet/Dockerfile .
docker run -d --name qbtc -p 28333:28333 -p 28332:28332 -v qbtc-data:/home/qbtc/.bitcoin qbtc-testnet
```

See [doc/join-testnet.md](../../doc/join-testnet.md) for full Docker Compose setup.

### Manual Build

### 1. Build

```bash
cd /path/to/QuantBTC
./autogen.sh
./configure --with-incompatible-bdb
make -j$(nproc)
```

### 2. Start the node

```bash
# Start with the helper script:
./contrib/qbtc-testnet/qbtc-testnet.sh start

# Or start manually:
./src/bitcoind -qbtctestnet -daemon -fallbackfee=0.0001 -txindex=1

# Connect to a specific seed node:
QBTC_SEEDNODE=seed1.quantumbtc.org:28333 ./contrib/qbtc-testnet/qbtc-testnet.sh start
```

### 3. Check status

```bash
./contrib/qbtc-testnet/qbtc-testnet.sh status
# Or:
./src/bitcoin-cli -qbtctestnet getblockchaininfo
```

### 4. Mine blocks

```bash
# Mine 10 blocks:
./contrib/qbtc-testnet/qbtc-testnet.sh mine 10

# Or use the standalone mining script:
./qbtc-mine.sh 10 qbtctestnet
```

### 5. Send a PQC transaction

```bash
# Get a new address (with qbtct1... prefix):
./contrib/qbtc-testnet/qbtc-testnet.sh address

# Send QBTC:
./contrib/qbtc-testnet/qbtc-testnet.sh send qbtct1q... 1.0
```

### 6. Stop the node

```bash
./contrib/qbtc-testnet/qbtc-testnet.sh stop
```

## Configuration

Place `qbtc-testnet.conf` in `~/.bitcoin/bitcoin.conf` or use:
```bash
./src/bitcoind -qbtctestnet -conf=/path/to/qbtc-testnet.conf
```

See [qbtc-testnet.conf](qbtc-testnet.conf) for all available options.

### Config file sections

You can also use a section in your main `bitcoin.conf`:
```ini
[qbtctestnet]
server=1
listen=1
txindex=1
fallbackfee=0.0001
# seednode=seed1.quantumbtc.org:28333
```

## Connecting to the Live Testnet

Three public seed nodes are running continuously:

| Node | IP | P2P Port |
|------|-----|----------|
| Seed 1 | 46.62.156.169 | 28333 |
| Seed 2 | 37.27.47.236 | 28333 |
| Seed 3 | 89.167.109.241 | 28333 |

Add to your `bitcoin.conf`:

```ini
[qbtctestnet]
seednode=46.62.156.169:28333
seednode=37.27.47.236:28333
seednode=89.167.109.241:28333
```

Or via command line:

```bash
./src/bitcoind -qbtctestnet -seednode=46.62.156.169:28333 -seednode=37.27.47.236:28333 -seednode=89.167.109.241:28333
```

Or via RPC (while running):

```bash
./src/bitcoin-cli -qbtctestnet addnode "46.62.156.169:28333" "add"
./src/bitcoin-cli -qbtctestnet addnode "37.27.47.236:28333" "add"
./src/bitcoin-cli -qbtctestnet addnode "89.167.109.241:28333" "add"
```

## Public Services

| Service | URL | Description |
|---------|-----|-------------|
| Block Explorer | [beartec.uk/qbtc-scan](https://beartec.uk/qbtc-scan) | Search blocks, txs, addresses; view DAG tips and PQC status |
| Testnet Faucet | [beartec.uk/qbtc-faucet](https://beartec.uk/qbtc-faucet) | Claim 0.5 QBTC per hour for testing |

## Data Directory

Testnet data is stored in:
- Linux: `~/.bitcoin/qbtctestnet/`
- macOS: `~/Library/Application Support/Bitcoin/qbtctestnet/`
- Windows: `%LOCALAPPDATA%\Bitcoin\qbtctestnet\`

## Network Identity

| Parameter | Testnet | Mainnet |
|-----------|---------|---------|
| Chain type | `qbtctestnet` | `qbtcmain` |
| CLI flag | `-qbtctestnet` | `-qbtcmain` |
| P2P port | 28333 | 58333 |
| RPC port | 28332 | 58332 |
| Magic bytes | `d1 a5 c3 b7` | `e3 b5 d7 a9` |
| Bech32 HRP | `qbtct` | `qbtc` |
| GHOSTDAG K | 32 | 18 |

## Verifying PQC Signatures

Every transaction on the testnet carries hybrid signatures:
- **ECDSA** (secp256k1) — classical security
- **ML-DSA-44** (Dilithium2) — quantum-safe security

The witness stack for each P2WPKH input contains 4 elements:
1. ECDSA signature (~71 bytes)
2. EC public key (33 bytes, compressed)
3. Dilithium signature (2420 bytes)
4. Dilithium public key (1312 bytes)

Inspect a transaction:
```bash
./src/bitcoin-cli -qbtctestnet getrawtransaction <txid> true
```
