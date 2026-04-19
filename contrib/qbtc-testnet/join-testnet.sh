#!/usr/bin/env bash
# join-testnet.sh — One-command script to build, configure, and join the qBTC testnet
#
# Usage:
#   curl -sL https://raw.githubusercontent.com/beartec-jpg/QuantBTC/main/contrib/qbtc-testnet/join-testnet.sh | bash
#
# Or clone and run directly:
#   ./contrib/qbtc-testnet/join-testnet.sh
#
# What it does:
#   1. Installs build dependencies (apt-get)
#   2. Clones the repo (if not already in one)
#   3. Builds bitcoind + bitcoin-cli
#   4. Writes a testnet config with seed nodes
#   5. Starts the node and begins syncing
#   6. Creates a wallet and prints a mining address
#
# Environment overrides:
#   QBTC_DATADIR   — custom data directory (default: ~/.bitcoin)
#   QBTC_WALLET    — wallet name (default: miner)
#   QBTC_JOBS      — parallel make jobs (default: nproc)
#   QBTC_SKIP_DEPS — set to 1 to skip apt-get install
#   QBTC_LOW_SPEC  — set to 1 for older or low-memory hardware

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[qBTC]${NC} $*"; }
warn() { echo -e "${YELLOW}[qBTC]${NC} $*"; }
err()  { echo -e "${RED}[qBTC]${NC} $*" >&2; }

DATADIR="${QBTC_DATADIR:-$HOME/.bitcoin}"
WALLET="${QBTC_WALLET:-miner}"
JOBS="${QBTC_JOBS:-$(nproc 2>/dev/null || echo 2)}"
SKIP_DEPS="${QBTC_SKIP_DEPS:-0}"
LOW_SPEC="${QBTC_LOW_SPEC:-0}"
BINDIR="${QBTC_BINDIR:-}"

SEED1="46.62.156.169:28333"
SEED2="37.27.47.236:28333"
SEED3="89.167.109.241:28333"

usage() {
    cat <<EOF
Usage: ./contrib/qbtc-testnet/join-testnet.sh [option]

Options:
  --help, -h         Show this help and exit
  --configure-only   Write or refresh the qBTC testnet config only
  --start-only       Start the node and wallet using existing binaries/config

Environment:
  QBTC_DATADIR   Custom data directory (default: ~/.bitcoin)
  QBTC_BINDIR    Binary directory override
  QBTC_WALLET    Wallet name (default: miner)
  QBTC_JOBS      Parallel build jobs
  QBTC_SKIP_DEPS Set to 1 to skip system package install
  QBTC_LOW_SPEC  Set to 1 for older or low-memory hardware
EOF
}

# ── Step 1: Dependencies ─────────────────────────────────────────────
install_deps() {
    if [[ "$SKIP_DEPS" == "1" ]]; then
        log "Skipping dependency install (QBTC_SKIP_DEPS=1)"
        return
    fi

    log "Installing build dependencies..."
    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq \
            build-essential libtool autotools-dev automake pkg-config \
            bsdmainutils python3 libssl-dev libevent-dev libboost-dev \
            libboost-system-dev libboost-filesystem-dev \
            libsqlite3-dev libminiupnpc-dev libnatpmp-dev libzmq3-dev \
            git
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y gcc-c++ libtool autoconf automake make \
            python3 libevent-devel boost-devel sqlite-devel \
            miniupnpc-devel libnatpmp-devel zeromq-devel git
    elif command -v brew &>/dev/null; then
        brew install automake libtool pkg-config libevent boost \
            miniupnpc libnatpmp zeromq sqlite
    else
        warn "Unknown package manager — install dependencies manually."
        warn "Need: gcc/g++, autotools, libevent, boost, sqlite3, zmq"
    fi
}

# ── Step 2: Clone / locate repo ──────────────────────────────────────
locate_repo() {
    # If we're already inside the repo
    if [[ -f "src/bitcoind.cpp" ]] || [[ -f "configure.ac" && -d "src/dag" ]]; then
        REPO_DIR="$(pwd)"
        log "Already inside QuantBTC repo at $REPO_DIR"
        return
    fi

    # Check if parent is the repo (we might be in contrib/)
    if [[ -f "../../configure.ac" && -d "../../src/dag" ]]; then
        REPO_DIR="$(cd ../.. && pwd)"
        log "Found repo at $REPO_DIR"
        return
    fi

    # Clone fresh
    REPO_DIR="$HOME/QuantBTC"
    if [[ -d "$REPO_DIR/.git" ]]; then
        log "Repo already cloned at $REPO_DIR — pulling latest..."
        cd "$REPO_DIR" && git pull --ff-only
    else
        log "Cloning QuantBTC..."
        git clone https://github.com/beartec-jpg/QuantBTC.git "$REPO_DIR"
    fi
}

# ── Step 3: Build ────────────────────────────────────────────────────
build() {
    cd "$REPO_DIR"

    # Check common binary locations
    if [[ -x "src/bitcoind" && -x "src/bitcoin-cli" ]]; then
        BINDIR="$REPO_DIR/src"
        log "Binaries found at $BINDIR — skipping build"
        return
    fi

    if [[ -x "build-fresh/src/bitcoind" && -x "build-fresh/src/bitcoin-cli" ]]; then
        BINDIR="$REPO_DIR/build-fresh/src"
        log "Binaries found at $BINDIR — skipping build"
        return
    fi

    # Check QBTC_BINDIR override
    if [[ -n "${QBTC_BINDIR:-}" && -x "${QBTC_BINDIR}/bitcoind" ]]; then
        BINDIR="$QBTC_BINDIR"
        log "Binaries found at $BINDIR (via QBTC_BINDIR) — skipping build"
        return
    fi

    BINDIR="$REPO_DIR/src"
    log "Building QuantBTC (this may take 10-30 minutes)..."

    # Ensure stub Makefiles exist (required by AC_CONFIG_LINKS in configure.ac)
    for f in src/qt/Makefile src/qt/test/Makefile src/test/Makefile; do
        if [[ ! -f "$f" ]]; then
            mkdir -p "$(dirname "$f")"
            echo "# Placeholder file required by AC_CONFIG_LINKS during autoreconf." > "$f"
        fi
    done

    if [[ ! -f "Makefile.in" ]]; then
        log "Running autogen.sh..."
        ./autogen.sh
    fi

    if [[ ! -f "Makefile" ]]; then
        log "Running configure..."
        ./configure --with-incompatible-bdb --with-gui=no --disable-tests --disable-bench
    fi

    log "Compiling with $JOBS parallel jobs..."
    make -j"$JOBS"

    if [[ ! -x "src/bitcoind" ]]; then
        err "Build failed — bitcoind not found"
        exit 1
    fi

    BINDIR="$REPO_DIR/src"
    log "Build complete!"
}

# ── Step 4: Configure ────────────────────────────────────────────────
configure() {
    local CONF="$DATADIR/bitcoin.conf"

    mkdir -p "$DATADIR"

    if [[ -f "$CONF" ]]; then
        log "Updating testnet config at $CONF..."
    else
        log "Writing testnet config to $CONF..."
    fi

    append_if_missing() {
        local line="$1"
        grep -Fqx "$line" "$CONF" 2>/dev/null || echo "$line" >> "$CONF"
    }

    # Generate random RPC credentials
    local RPC_USER="qbtcuser"
    local RPC_PASS
    local DBCACHE MAXCONN MAXMEMPOOL MAXSIG PRUNE TXINDEX
    RPC_PASS="$(head -c 32 /dev/urandom | base64 | tr -dc 'a-zA-Z0-9' | head -c 24)"
    if [[ "$LOW_SPEC" == "1" ]]; then
        DBCACHE=128
        MAXCONN=16
        MAXMEMPOOL=150
        MAXSIG=16
        PRUNE=5500
        TXINDEX=0
    else
        DBCACHE=512
        MAXCONN=32
        MAXMEMPOOL=300
        MAXSIG=32
        PRUNE=10000
        TXINDEX=1
    fi

    if [[ ! -f "$CONF" ]]; then
        cat > "$CONF" <<EOF
# QuantumBTC Testnet Configuration
# Generated by join-testnet.sh on $(date -u +%Y-%m-%dT%H:%M:%SZ)

chain=qbtctestnet

[qbtctestnet]

# Network
server=1
listen=1
discover=1
dnsseed=1
txindex=${TXINDEX}

# RPC
rpcuser=${RPC_USER}
rpcpassword=${RPC_PASS}
rpcallowip=127.0.0.1
rpcbind=127.0.0.1

# Transaction settings
fallbackfee=0.0001
logtimestamps=1

# Seed nodes
seednode=${SEED1}
seednode=${SEED2}
seednode=${SEED3}

# Persistent peers for better convergence
addnode=${SEED1}
addnode=${SEED2}
addnode=${SEED3}

# Performance
dbcache=${DBCACHE}
maxconnections=${MAXCONN}
maxmempool=${MAXMEMPOOL}
maxsigcachesize=${MAXSIG}
prune=${PRUNE}
EOF
        log "Config written. RPC user: $RPC_USER"
    else
        if ! grep -q '^\[qbtctestnet\]' "$CONF"; then
            cat >> "$CONF" <<EOF

[qbtctestnet]
EOF
        fi
        append_if_missing "chain=qbtctestnet"
        append_if_missing "server=1"
        append_if_missing "listen=1"
        append_if_missing "discover=1"
        append_if_missing "dnsseed=1"
        append_if_missing "fallbackfee=0.0001"
        append_if_missing "logtimestamps=1"
        append_if_missing "seednode=${SEED1}"
        append_if_missing "seednode=${SEED2}"
        append_if_missing "seednode=${SEED3}"
        append_if_missing "addnode=${SEED1}"
        append_if_missing "addnode=${SEED2}"
        append_if_missing "addnode=${SEED3}"
        append_if_missing "dbcache=${DBCACHE}"
        append_if_missing "maxconnections=${MAXCONN}"
        append_if_missing "maxmempool=${MAXMEMPOOL}"
        append_if_missing "maxsigcachesize=${MAXSIG}"
        append_if_missing "prune=${PRUNE}"
        log "Config refreshed with current defaults."
    fi
}

# ── Step 5: Start ────────────────────────────────────────────────────
start_node() {
    cd "$REPO_DIR"

    local CLI="$BINDIR/bitcoin-cli -qbtctestnet -datadir=$DATADIR"

    # Check if already running
    if $CLI getblockchaininfo &>/dev/null; then
        log "Node is already running!"
        return
    fi

    log "Starting QuantumBTC testnet node..."
    "$BINDIR/bitcoind" -qbtctestnet -daemon -datadir="$DATADIR"

    # Wait for RPC
    log "Waiting for RPC to become available..."
    local tries=0
    while ! $CLI getblockchaininfo &>/dev/null; do
        tries=$((tries + 1))
        if [[ $tries -gt 30 ]]; then
            err "Node failed to start after 30 seconds"
            err "Check logs: $DATADIR/qbtctestnet/debug.log"
            exit 1
        fi
        sleep 1
    done

    for peer in "$SEED1" "$SEED2" "$SEED3"; do
        $CLI addnode "$peer" onetry >/dev/null 2>&1 || true
    done

    local height
    height=$($CLI getblockcount)
    local peers
    peers=$($CLI getconnectioncount)
    log "Node started! Height: $height, Peers: $peers"
}

# ── Step 6: Create wallet & print address ────────────────────────────
setup_wallet() {
    cd "$REPO_DIR"
    local CLI="$BINDIR/bitcoin-cli -qbtctestnet -datadir=$DATADIR"

    # Create or load wallet
    if $CLI -rpcwallet="$WALLET" getwalletinfo &>/dev/null; then
        log "Wallet '$WALLET' already loaded"
    elif $CLI loadwallet "$WALLET" &>/dev/null; then
        log "Wallet '$WALLET' loaded"
    elif $CLI createwallet "$WALLET" &>/dev/null; then
        log "Wallet '$WALLET' created"
    else
        warn "Could not create wallet — you can do it manually later"
        return
    fi

    local addr
    addr=$($CLI -rpcwallet="$WALLET" getnewaddress "" "bech32")

    echo ""
    echo -e "${CYAN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║              QuantumBTC Testnet Node Ready!                 ║${NC}"
    echo -e "${CYAN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${CYAN}║${NC}  Your mining address: ${GREEN}${addr}${NC}"
    echo -e "${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  Start mining:"
    echo -e "${CYAN}║${NC}    ${YELLOW}cd $REPO_DIR${NC}"
    echo -e "${CYAN}║${NC}    ${YELLOW}./contrib/qbtc-testnet/qbtc-testnet.sh mine 10${NC}"
    echo -e "${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  Or mine continuously:"
    echo -e "${CYAN}║${NC}    ${YELLOW}while true; do ${REPO_DIR}/src/bitcoin-cli -qbtctestnet \\${NC}"
    echo -e "${CYAN}║${NC}    ${YELLOW}  generatetoaddress 1 ${addr}; sleep 1; done${NC}"
    echo -e "${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  Check status:"
    echo -e "${CYAN}║${NC}    ${YELLOW}./contrib/qbtc-testnet/qbtc-testnet.sh status${NC}"
    echo -e "${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  Get free testnet QBTC:"
    echo -e "${CYAN}║${NC}    ${YELLOW}curl -X POST https://beartec.uk/qbtc-faucet -d \"address=$addr\"${NC}"
    echo -e "${CYAN}║${NC}"
    echo -e "${CYAN}║${NC}  Block explorer: ${GREEN}https://beartec.uk/qbtc-scan${NC}"
    echo -e "${CYAN}║${NC}  Logs: $DATADIR/qbtctestnet/debug.log"
    echo -e "${CYAN}╚══════════════════════════════════════════════════════════════╝${NC}"
}

# ── Main ─────────────────────────────────────────────────────────────
main() {
    local mode="full"
    case "${1:-}" in
        --help|-h|help)
            usage
            return 0
            ;;
        --configure-only)
            mode="configure-only"
            ;;
        --start-only)
            mode="start-only"
            ;;
        "")
            ;;
        *)
            err "Unknown option: $1"
            echo ""
            usage
            return 1
            ;;
    esac

    echo ""
    echo -e "${CYAN}  ╭────────────────────────────────────────────╮${NC}"
    echo -e "${CYAN}  │   QuantumBTC Testnet — Join Script         │${NC}"
    echo -e "${CYAN}  │   PQC + GHOSTDAG + 10-second targets       │${NC}"
    echo -e "${CYAN}  ╰────────────────────────────────────────────╯${NC}"
    echo ""

    case "$mode" in
        configure-only)
            locate_repo
            configure
            ;;
        start-only)
            locate_repo
            build
            configure
            start_node
            setup_wallet
            ;;
        full)
            install_deps
            locate_repo
            build
            configure
            start_node
            setup_wallet
            ;;
    esac
}

main "$@"
