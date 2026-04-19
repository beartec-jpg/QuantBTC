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
| Chain height | 96,600+ blocks (and growing) |
| Chain size | ~1.3 GB |
| Explorer | [beartec.uk/qbtc-scan](https://beartec.uk/qbtc-scan) |
| Faucet | [beartec.uk/qbtc-faucet](https://beartec.uk/qbtc-faucet) |

## Seed Nodes

| # | IP Address | P2P Port |
|---|---|---|
| S1 | 46.62.156.169 | 28333 |
| S2 | 37.27.47.236 | 28333 |
| S3 | 89.167.109.241 | 28333 |

---

## Option A: One-Command Join (Recommended)

The fastest way to get a node running — installs dependencies, builds from
source, configures seed nodes, starts the daemon, and creates a wallet:

```bash
git clone https://github.com/beartec-jpg/QuantBTC.git
cd QuantBTC
./contrib/qbtc-testnet/join-testnet.sh
```

The script is idempotent — if binaries are already built or the node is
already running, it skips those steps.

**Environment overrides:**

| Variable | Default | Description |
|---|---|---|
| `QBTC_DATADIR` | `~/.bitcoin` | Custom data directory |
| `QBTC_WALLET` | `miner` | Wallet name |
| `QBTC_JOBS` | `$(nproc)` | Parallel compile jobs |
| `QBTC_SKIP_DEPS` | `0` | Set to `1` to skip `apt-get install` |

---

## Option B: Docker

Build and run a testnet node in Docker:

```bash
git clone https://github.com/beartec-jpg/QuantBTC.git
cd QuantBTC

# Build the image (~15 min first time)
docker build -t qbtc-testnet -f contrib/qbtc-testnet/Dockerfile .

# Run with persistent data
docker run -d --name qbtc \
  -p 28333:28333 -p 28332:28332 \
  -v qbtc-data:/home/qbtc/.bitcoin \
  qbtc-testnet

# Check sync progress
docker exec qbtc bitcoin-cli -qbtctestnet getblockchaininfo

# Create wallet and start mining
docker exec qbtc bitcoin-cli -qbtctestnet createwallet miner
docker exec qbtc bash -c 'bitcoin-cli -qbtctestnet -rpcwallet=miner generatetoaddress 1 $(bitcoin-cli -qbtctestnet -rpcwallet=miner getnewaddress)'

# View logs
docker logs -f qbtc
```

**Docker Compose** (save as `docker-compose.yml`):

```yaml
services:
  qbtc:
    build:
      context: .
      dockerfile: contrib/qbtc-testnet/Dockerfile
    ports:
      - "28333:28333"
      - "28332:28332"
    volumes:
      - qbtc-data:/home/qbtc/.bitcoin
    restart: unless-stopped

volumes:
  qbtc-data:
```

```bash
docker compose up -d
```

---

## Windows (via WSL)

Windows users can run QuantumBTC through Windows Subsystem for Linux (WSL).
This gives you a full Ubuntu environment inside Windows — the join script
works exactly the same as on native Linux.

### 1. Install WSL (one-time)

Open **PowerShell as Administrator** and run:

```powershell
wsl --install
```

Restart your computer when prompted. On first launch, create a Unix
username and password.

### 2. Join the Testnet

Open the **Ubuntu** app from the Start Menu (or type `wsl` in PowerShell),
then run:

```bash
sudo apt-get update && sudo apt-get install -y git
git clone https://github.com/beartec-jpg/QuantBTC.git
cd QuantBTC
./contrib/qbtc-testnet/join-testnet.sh
```

That's it — same 4 commands as Linux.

### WSL Tips

- **Low RAM?** WSL defaults to half your system RAM. If build OOMs, use
  `QBTC_JOBS=1 ./contrib/qbtc-testnet/join-testnet.sh`
- **Disk location:** Your WSL files are at `\\wsl$\Ubuntu\home\<user>\` in
  Windows Explorer
- **Port forwarding:** WSL2 automatically forwards ports — your node's P2P
  port (28333) is reachable from the network without extra config
- **Persist across reboots:** The node stops when you close WSL. To restart:
  ```bash
  cd ~/QuantBTC
  ./src/bitcoind -qbtctestnet -daemon -datadir=$HOME/.bitcoin
  ```

### Alternative: Docker Desktop for Windows

If you prefer Docker:

1. Install [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
   (enable WSL2 backend during install)
2. Open PowerShell:
   ```powershell
   git clone https://github.com/beartec-jpg/QuantBTC.git
   cd QuantBTC
   docker build -t qbtc -f contrib/qbtc-testnet/Dockerfile .
   docker run -d --name qbtc -p 28333:28333 -p 28332:28332 qbtc
   ```

---

## Option C: Manual Build

### 1. Build from Source

```bash
git clone https://github.com/beartec-jpg/QuantBTC.git
cd QuantBTC

sudo apt-get install -y build-essential libtool autotools-dev automake pkg-config \
    bsdmainutils python3 libevent-dev libboost-dev libboost-system-dev \
    libboost-filesystem-dev libsqlite3-dev libminiupnpc-dev libnatpmp-dev libzmq3-dev

./autogen.sh
./configure --with-incompatible-bdb --with-gui=no
make -j$(nproc)
```

### 2. Configure

Create `~/.bitcoin/bitcoin.conf`:

```ini
[qbtctestnet]
chain=qbtctestnet

# RPC
server=1
rpcuser=<choose_a_username>
rpcpassword=<choose_a_strong_password>
rpcallowip=127.0.0.1

# Transaction settings
fallbackfee=0.0001
txindex=1

# Seed nodes
seednode=46.62.156.169:28333
seednode=37.27.47.236:28333
seednode=89.167.109.241:28333
```

### 3. Start the Node

```bash
./src/bitcoind -daemon
```

### Windows quick start for older PCs

A low-spec Windows profile is now available under:

- `contrib/qbtc-testnet/qbtc-testnet-windows.bat`
- `contrib/qbtc-testnet/qbtc-testnet-windows.ps1`
- `contrib/qbtc-testnet/qbtc-windows-low-spec.conf`

The launcher auto-creates the config if needed, uses pruning and reduced cache settings, and attempts to re-add the public seed peers when the local peer count is too low.

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

- Repository: https://github.com/beartec-jpg/QuantBTC
- Block Explorer: https://beartec.uk/qbtc-scan
- Testnet Faucet: https://beartec.uk/qbtc-faucet
- GHOSTDAG design: [doc/ghostdag.md](ghostdag.md)

---

## Home Mining Guide

The qBTC testnet uses SHA-256 Proof of Work with very low difficulty,
making it easy to mine on consumer hardware. Every mined block earns
the block reward in QBTC and contributes to DAG tip diversity.

### Mining with the Helper Script

The simplest way to mine:

```bash
# Mine 10 blocks
./contrib/qbtc-testnet/qbtc-testnet.sh mine 10

# Or use the join script's output — it prints a mining command
```

### Continuous CPU Mining

```bash
CLI="./src/bitcoin-cli -qbtctestnet"
ADDR=$($CLI -rpcwallet=miner getnewaddress)

# Mine one block per second with a 1-second pause
while true; do
    $CLI generatetoaddress 1 "$ADDR" 999999999 2>/dev/null
    sleep 1
done
```

**Why `sleep 1`?** Without a pause, mining consumes 100% CPU and floods
the network with blocks faster than they can propagate. A 1-second pause
matches the block target and keeps CPU usage manageable (~10-30%).

### Mining Performance by Hardware

All numbers are for solo `generatetoaddress` mining at testnet difficulty:

| Hardware | Hash Rate (approx) | Blocks/hour | CPU Usage | Notes |
|---|---|---|---|---|
| 1-core VPS (2 GHz) | 1-5 MH/s | ~3,600 | ~100% without sleep | Use `sleep 1` |
| 4-core desktop (3 GHz) | 5-20 MH/s | ~3,600 | ~25% with sleep | Comfortable 24/7 |
| Raspberry Pi 4 | 0.5-1 MH/s | ~3,600 | ~100% without sleep | Works fine with sleep |
| GPU (any) | N/A | ~3,600 | — | No GPU miner yet; `generatetoaddress` is CPU-only |
| ASIC (any SHA-256) | N/A | ~3,600 | — | No Stratum support yet |

> At current testnet difficulty, any hardware can mine ~1 block/second.
> The block rate is limited by `sleep`, not by hash power. When difficulty
> rises (more miners join), faster hardware will win blocks more often.

### Mining Throttling (Recommended)

To keep your node as a good network citizen:

```bash
# Throttled mining — 1 block, then sleep 10 seconds
while true; do
    $CLI generatetoaddress 1 "$ADDR" 999999999 2>/dev/null
    sleep 10
done
```

This mines ~360 blocks/hour and uses minimal CPU. The other seed nodes
use this pattern.

### What You Earn

| Parameter | Value |
|---|---|
| Block reward | 0.08333333 QBTC (8,333,333 satoshis) |
| Blocks per hour (sleep 1) | ~3,600 |
| QBTC per hour (sleep 1) | ~300 QBTC |
| Blocks per hour (sleep 10) | ~360 |
| QBTC per hour (sleep 10) | ~30 QBTC |
| Halving interval | 126,000,000 blocks (~4 years) |

### Mining + Transaction Traffic

To also generate transactions while mining (useful for testing):

```bash
# Background miner
nohup bash -c 'while true; do
    ./src/bitcoin-cli -qbtctestnet -rpcwallet=miner \
        generatetoaddress 1 $(./src/bitcoin-cli -qbtctestnet -rpcwallet=miner getnewaddress) \
        999999999 2>/dev/null
    sleep 10
done' &>/tmp/miner.log &

# Transaction generator — send 0.01 QBTC every 2 seconds
nohup bash -c 'while true; do
    ./src/bitcoin-cli -qbtctestnet -rpcwallet=miner \
        sendtoaddress $(./src/bitcoin-cli -qbtctestnet -rpcwallet=miner getnewaddress) \
        0.01 2>/dev/null
    sleep 2
done' &>/tmp/txgen.log &
```

### Future: Pool Mining & GPU/ASIC Support

Pool mining (Stratum v2) and GPU/ASIC compatibility are planned for
Phase 9. Currently only solo CPU mining via `generatetoaddress` RPC is
supported. See [ROADMAP.md](../ROADMAP.md) for details.
