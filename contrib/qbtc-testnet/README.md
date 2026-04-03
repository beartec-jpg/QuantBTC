# QuantumBTC Testnet

**QuantumBTC testnet** is a standalone blockchain network for testing quantum-safe transactions and BlockDAG consensus before mainnet deployment.

## Features

| Feature | Specification |
|---------|---------------|
| **Network** | Independent chain (not a Bitcoin testnet fork) |
| **Consensus** | GHOSTDAG (K=32, 1-second blocks) |
| **PQC** | ML-DSA-44 hybrid signatures (always active) |
| **Port** | 28333 (P2P), 28332 (RPC) |
| **Address prefix** | `qbtct1...` (bech32) |
| **Base58 prefix** | `q...` (P2PKH), `r...` (P2SH) |
| **Block reward** | 50 QBTC |
| **Max block weight** | 16 MB |
| **Difficulty** | Trivial (easy solo mining) |
| **Magic bytes** | `d1 a5 c3 b7` |

## Quick Start

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

## Connecting Peers

Since no DNS seeds are configured yet, use one of these methods:

```bash
# Via command line:
./src/bitcoind -qbtctestnet -seednode=<ip>:28333 -addnode=<ip>:28333

# Via config:
[qbtctestnet]
seednode=<ip>:28333
addnode=<ip>:28333

# Via RPC (while running):
./src/bitcoin-cli -qbtctestnet addnode "<ip>:28333" "add"
```

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
