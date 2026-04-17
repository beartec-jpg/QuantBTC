#!/usr/bin/env bash
# qbtc-testnet.sh — Launch and manage a QuantumBTC testnet node
#
# Usage:
#   ./contrib/qbtc-testnet/qbtc-testnet.sh start     # start testnet node in background
#   ./contrib/qbtc-testnet/qbtc-testnet.sh stop      # graceful shutdown
#   ./contrib/qbtc-testnet/qbtc-testnet.sh status    # show chain and DAG status
#   ./contrib/qbtc-testnet/qbtc-testnet.sh mine [N]  # mine N blocks (default: 1)
#   ./contrib/qbtc-testnet/qbtc-testnet.sh cli ...   # pass-through to bitcoin-cli
#   ./contrib/qbtc-testnet/qbtc-testnet.sh info      # getblockchaininfo
#   ./contrib/qbtc-testnet/qbtc-testnet.sh peers     # show connected peers
#   ./contrib/qbtc-testnet/qbtc-testnet.sh wallet    # create or load miner wallet
#   ./contrib/qbtc-testnet/qbtc-testnet.sh address   # get a new testnet address
#   ./contrib/qbtc-testnet/qbtc-testnet.sh send <addr> <amount>  # send QBTC
#
# Environment:
#   QBTC_DATADIR   — custom data directory (default: ~/.bitcoin)
#   QBTC_BINDIR    — directory containing bitcoind/bitcoin-cli (default: ./src)
#   QBTC_WALLET    — wallet name for mining (default: miner)
#   QBTC_CONF      — custom config file path
#   QBTC_SEEDNODE  — seed node to connect to (ip:port)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

BINDIR="${QBTC_BINDIR:-${REPO_ROOT}/src}"
DATADIR="${QBTC_DATADIR:-}"
WALLET="${QBTC_WALLET:-miner}"
CONF="${QBTC_CONF:-}"
SEEDNODE="${QBTC_SEEDNODE:-}"
CHAIN="qbtctestnet"

BITCOIND="${BINDIR}/bitcoind"
CLI="${BINDIR}/bitcoin-cli"

# Verify binaries exist
if [[ ! -x "$BITCOIND" ]]; then
    echo "ERROR: bitcoind not found at $BITCOIND"
    echo "Build first:  cd ${REPO_ROOT} && ./configure && make -j\$(nproc)"
    exit 1
fi
if [[ ! -x "$CLI" ]]; then
    echo "ERROR: bitcoin-cli not found at $CLI"
    exit 1
fi

# Build CLI args
CLI_ARGS=("-${CHAIN}")
DAEMON_ARGS=("-${CHAIN}" "-daemon")

if [[ -n "$DATADIR" ]]; then
    CLI_ARGS+=("-datadir=${DATADIR}")
    DAEMON_ARGS+=("-datadir=${DATADIR}")
fi

if [[ -n "$CONF" ]]; then
    CLI_ARGS+=("-conf=${CONF}")
    DAEMON_ARGS+=("-conf=${CONF}")
fi

if [[ -n "$SEEDNODE" ]]; then
    DAEMON_ARGS+=("-seednode=${SEEDNODE}")
fi

cli() {
    "$CLI" "${CLI_ARGS[@]}" "$@"
}

cmd_start() {
    echo "Starting QuantumBTC testnet node..."
    echo "  Chain:    $CHAIN"
    echo "  Port:     28333 (P2P), 28332 (RPC)"
    echo "  Bech32:   qbtct1..."
    echo "  DAG:      GHOSTDAG K=32, 1s blocks"
    echo "  PQC:      ML-DSA-44 (always active)"
    echo ""

    local extra_args=("$@")
    "$BITCOIND" "${DAEMON_ARGS[@]}" "${extra_args[@]}" \
        -fallbackfee=0.0001 \
        -server=1 \
        -listen=1 \
        -txindex=1 \
        -logtimestamps=1 \
        -printtoconsole=0 \
        -maxsigcachesize=32

    echo "Node started. Use '$0 status' to check."
    echo "Logs: ~/.bitcoin/qbtctestnet/debug.log"
}

cmd_stop() {
    echo "Stopping QuantumBTC testnet node..."
    cli stop
    echo "Shutdown signal sent."
}

cmd_status() {
    if ! cli getblockchaininfo >/dev/null 2>&1; then
        echo "Node is NOT running (or RPC not reachable)."
        exit 1
    fi
    cli getblockchaininfo | python3 -c "
import sys, json
d = json.load(sys.stdin)
print('QuantumBTC Testnet Status')
print('=' * 40)
print(f'  Chain:        {d[\"chain\"]}')
print(f'  Blocks:       {d[\"blocks\"]}')
print(f'  Headers:      {d[\"headers\"]}')
print(f'  DAG mode:     {d.get(\"dagmode\", \"N/A\")}')
print(f'  DAG tips:     {d.get(\"dag_tips\", \"N/A\")}')
print(f'  GHOSTDAG K:   {d.get(\"ghostdag_k\", \"N/A\")}')
print(f'  PQC:          {d.get(\"pqc\", \"N/A\")}')
print(f'  Difficulty:   {d[\"difficulty\"]}')
print(f'  Pruned:       {d[\"pruned\"]}')
print(f'  Size on disk: {d[\"size_on_disk\"] / 1024 / 1024:.1f} MB')
"
}

cmd_info() {
    cli getblockchaininfo
}

cmd_peers() {
    if ! cli getpeerinfo >/dev/null 2>&1; then
        echo "Node is NOT running."
        exit 1
    fi
    local count
    count=$(cli getconnectioncount)
    echo "Connected peers: $count"
    if [[ "$count" -gt 0 ]]; then
        cli getpeerinfo | python3 -c "
import sys, json
peers = json.load(sys.stdin)
for p in peers:
    print(f'  {p[\"addr\"]:30s}  {p[\"subver\"]:30s}  height={p.get(\"synced_headers\", \"?\")}')
"
    fi
}

cmd_wallet() {
    if cli -rpcwallet="$WALLET" getwalletinfo >/dev/null 2>&1; then
        echo "Wallet '$WALLET' already loaded."
    elif cli loadwallet "$WALLET" >/dev/null 2>&1; then
        echo "Wallet '$WALLET' loaded."
    elif cli createwallet "$WALLET" >/dev/null 2>&1; then
        echo "Wallet '$WALLET' created."
    else
        echo "ERROR: Failed to create/load wallet '$WALLET'."
        exit 1
    fi
    cli -rpcwallet="$WALLET" getwalletinfo | python3 -c "
import sys, json
w = json.load(sys.stdin)
print(f'  Name:    {w[\"walletname\"]}')
print(f'  Balance: {w[\"balance\"]} QBTC')
print(f'  TxCount: {w[\"txcount\"]}')
"
}

cmd_address() {
    cmd_wallet >/dev/null 2>&1 || true
    local addr
    addr=$(cli -rpcwallet="$WALLET" getnewaddress "" "bech32")
    echo "$addr"
}

cmd_mine() {
    local count="${1:-1}"
    cmd_wallet >/dev/null 2>&1 || true
    local addr
    addr=$(cli -rpcwallet="$WALLET" getnewaddress "" "bech32")
    echo "Mining $count block(s) to $addr ..."
    for i in $(seq 1 "$count"); do
        local result hash height
        result=$(cli -rpcwallet="$WALLET" generatetoaddress 1 "$addr")
        hash=$(echo "$result" | python3 -c "import sys,json; print(json.load(sys.stdin)[0][:16])" 2>/dev/null)
        height=$(cli getblockcount)
        echo "  [$i/$count] height=$height  hash=${hash}..."
    done
    echo ""
    cmd_status
}

cmd_send() {
    local to_addr="$1"
    local amount="$2"
    if [[ -z "$to_addr" || -z "$amount" ]]; then
        echo "Usage: $0 send <address> <amount>"
        exit 1
    fi
    cmd_wallet >/dev/null 2>&1 || true
    local txid
    txid=$(cli -rpcwallet="$WALLET" sendtoaddress "$to_addr" "$amount")
    echo "Sent $amount QBTC to $to_addr"
    echo "TxID: $txid"
}

cmd_cli() {
    cli "$@"
}

usage() {
    echo "Usage: $0 <command> [args...]"
    echo ""
    echo "Commands:"
    echo "  start [bitcoind-args]   Start testnet node in background"
    echo "  stop                    Graceful shutdown"
    echo "  status                  Show chain and DAG status"
    echo "  info                    Raw getblockchaininfo JSON"
    echo "  peers                   Show connected peers"
    echo "  wallet                  Create or load miner wallet"
    echo "  address                 Get a new testnet address"
    echo "  mine [N]               Mine N blocks (default: 1)"
    echo "  send <addr> <amount>   Send QBTC"
    echo "  cli [args...]          Pass-through to bitcoin-cli"
    echo ""
    echo "Environment:"
    echo "  QBTC_DATADIR   Custom data directory"
    echo "  QBTC_BINDIR    Binary directory (default: ./src)"
    echo "  QBTC_WALLET    Wallet name (default: miner)"
    echo "  QBTC_SEEDNODE  Seed node to bootstrap from (ip:port)"
}

COMMAND="${1:-}"
shift || true

case "$COMMAND" in
    start)   cmd_start "$@" ;;
    stop)    cmd_stop ;;
    status)  cmd_status ;;
    info)    cmd_info ;;
    peers)   cmd_peers ;;
    wallet)  cmd_wallet ;;
    address) cmd_address ;;
    mine)    cmd_mine "$@" ;;
    send)    cmd_send "$@" ;;
    cli)     cmd_cli "$@" ;;
    help|-h|--help|"")
        usage ;;
    *)
        echo "Unknown command: $COMMAND"
        usage
        exit 1 ;;
esac
