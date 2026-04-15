#!/bin/bash
set -e
# ============================================================
# QuantumBTC: Build & Run High-Throughput Multi-Miner DAG Test
# 90% ECDSA / 10% ML-DSA with ALL nodes mining concurrently
# ============================================================

SRCDIR="$(cd "$(dirname "$0")" && pwd)"
BUILDDIR="$SRCDIR/build-fresh"

echo "============================================================"
echo " QuantumBTC Build & High-Throughput Test Setup"
echo " 90% ECDSA / 10% ML-DSA | Multi-Miner DAG Stress"
echo "============================================================"

# ── 1. Install build dependencies ─────────────────────────────────────
echo ""
echo "▸ Step 1: Checking / installing build dependencies..."

install_deps() {
    if command -v apt-get &>/dev/null; then
        # Disable broken third-party repos (e.g. yarn) that block apt update
        for f in /etc/apt/sources.list.d/*.list; do
            if grep -qi 'yarnpkg\|yarn' "$f" 2>/dev/null; then
                echo "  Disabling broken repo: $f"
                sudo mv "$f" "${f}.disabled" 2>/dev/null || true
            fi
        done
        sudo apt-get update -qq 2>&1 | grep -v "^W:" | tail -3
        sudo apt-get install -y -qq \
            build-essential libtool autotools-dev automake pkg-config \
            bsdmainutils python3 libevent-dev libboost-dev libsqlite3-dev \
            libzmq3-dev 2>&1 | tail -3
    else
        echo "  (Non-Debian system — ensure build deps are installed manually)"
    fi
}

# Check if key tools/libs exist before installing
if ! pkg-config --exists libevent 2>/dev/null || \
   ! command -v automake &>/dev/null; then
    install_deps
else
    echo "  Build dependencies already present ✓"
fi

# ── 2. Build QuantumBTC ───────────────────────────────────────────────
echo ""
echo "▸ Step 2: Building QuantumBTC..."

if [[ -x "$BUILDDIR/src/bitcoind" && -x "$BUILDDIR/src/bitcoin-cli" ]]; then
    echo "  Binaries already built at $BUILDDIR ✓"
else
    cd "$SRCDIR"

    # Run autogen if configure doesn't exist
    if [[ ! -f configure ]]; then
        echo "  Running autogen.sh..."
        ./autogen.sh
    fi

    # Configure in build directory
    mkdir -p "$BUILDDIR"
    cd "$BUILDDIR"

    if [[ ! -f Makefile ]]; then
        echo "  Configuring (--without-gui --with-pqc --enable-dag)..."
        "$SRCDIR/configure" \
            --without-gui \
            --with-incompatible-bdb \
            --disable-bench \
            --disable-tests \
            --enable-suppress-external-warnings \
            CXXFLAGS="-O2 -g0" \
            2>&1 | tail -5
    fi

    NPROC=$(nproc 2>/dev/null || echo 4)
    echo "  Compiling with -j${NPROC}..."
    make -j"$NPROC" 2>&1 | tail -5

    if [[ ! -x src/bitcoind ]]; then
        echo "  FATAL: Build failed — src/bitcoind not found"
        exit 1
    fi
    echo "  Build complete ✓"
fi

# Verify binaries
echo ""
echo "▸ Binary check:"
"$BUILDDIR/src/bitcoind" --version 2>&1 | head -1
"$BUILDDIR/src/bitcoin-cli" --version 2>&1 | head -1

# ── 3. Kill any leftover nodes ────────────────────────────────────────
echo ""
echo "▸ Step 3: Cleaning up any leftover test nodes..."
pkill -f "qbtc-htp-" 2>/dev/null || true
sleep 1

# ── 4. Run the test ───────────────────────────────────────────────────
echo ""
echo "▸ Step 4: Launching high-throughput multi-miner DAG test..."
echo "  Binary: $BUILDDIR/src/bitcoind"
echo ""

cd "$SRCDIR"
export BITCOIND="$BUILDDIR/src/bitcoind"
export CLI="$BUILDDIR/src/bitcoin-cli"

# Default: 10 nodes, 5 wallets each, 50k txs, 500 batch
# Override with env vars or pass extra args after --
NODES="${TEST_NODES:-10}"
WALLETS="${TEST_WALLETS:-5}"
TXS="${TEST_TXS:-50000}"
BATCH="${TEST_BATCH:-200}"
DURATION="${TEST_DURATION:-0}"

python3 test_hightp_90ecdsa_10mldsa.py \
    --nodes "$NODES" \
    --wallets-per-node "$WALLETS" \
    --txs "$TXS" \
    --batch "$BATCH" \
    --duration "$DURATION" \
    "$@"
