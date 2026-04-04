#!/usr/bin/env bash
# install-qbtc-node.sh
#
# One-line install for a qBTC testnet node.
# Usage:
#   curl -sSL https://raw.githubusercontent.com/beartec-jpg/QuantBTC/main/install-qbtc-node.sh | bash
#
# Supports Linux (x86_64 and aarch64) only.
# Prefers Docker when available; falls back to a native build from source.

set -euo pipefail

# ── Colours & helpers ─────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[qBTC]${NC} $*"; }
success() { echo -e "${GREEN}[qBTC]${NC} $*"; }
warn()    { echo -e "${YELLOW}[qBTC]${NC} $*"; }
die()     { echo -e "${RED}[qBTC] ERROR:${NC} $*" >&2; exit 1; }

REPO_URL="https://github.com/beartec-jpg/QuantBTC.git"
DOCKER_IMAGE="ghcr.io/beartec-jpg/quantbtc:testnet"
P2P_PORT=28333
RPC_PORT=28332

# ── OS / Architecture detection ───────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"

case "$OS" in
    Linux) ;;
    Darwin) die "macOS is not supported yet. Please use Docker Desktop and run:
  docker run -d --name qbtc-node -p 28333:28333 -v qbtc-data:/data ${DOCKER_IMAGE}" ;;
    *)     die "Unsupported OS: ${OS}. Only Linux is supported at this time." ;;
esac

case "$ARCH" in
    x86_64|aarch64) ;;
    *) die "Unsupported architecture: ${ARCH}. Only x86_64 and aarch64 are supported." ;;
esac

info "Detected: ${OS}/${ARCH}"

# ── Docker path ───────────────────────────────────────────────────────────────
docker_install() {
    info "Docker detected – using Docker path."

    # Prompt for a seed node
    echo ""
    warn "Optional: Enter a seed node IP:port (e.g. 1.2.3.4:28333) for initial peer discovery."
    warn "Press ENTER to skip (you can add it later via SEEDNODE env var)."
    read -r -p "Seed node [leave blank to skip]: " SEEDNODE_INPUT

    info "Pulling image ${DOCKER_IMAGE} ..."
    docker pull "${DOCKER_IMAGE}"

    DOCKER_CMD=(
        docker run -d
        --name qbtc-node
        --restart unless-stopped
        -p "${P2P_PORT}:${P2P_PORT}"
        -p "${RPC_PORT}:${RPC_PORT}"
        -v qbtc-data:/data
    )

    if [[ -n "${SEEDNODE_INPUT:-}" ]]; then
        DOCKER_CMD+=(-e "SEEDNODE=${SEEDNODE_INPUT}")
    fi

    DOCKER_CMD+=("${DOCKER_IMAGE}")

    "${DOCKER_CMD[@]}"

    success "qBTC testnet node started via Docker!"
    echo ""
    info "Useful commands:"
    echo "  View logs:    docker logs -f qbtc-node"
    echo "  Chain info:   docker exec qbtc-node bitcoin-cli -qbtctestnet -datadir=/data getblockchaininfo"
    echo "  Peer count:   docker exec qbtc-node bitcoin-cli -qbtctestnet -datadir=/data getconnectioncount"
    echo "  Stop node:    docker stop qbtc-node"
    echo "  Remove node:  docker rm qbtc-node"
}

# ── Native (build-from-source) path ───────────────────────────────────────────
native_install() {
    info "Docker not found – building qBTC from source (native install)."

    # Ensure we are running as root or can sudo
    if [[ "$EUID" -ne 0 ]]; then
        SUDO="sudo"
        info "Will use sudo for privileged operations."
    else
        SUDO=""
    fi

    # ── 1. Install build dependencies ─────────────────────────────────────────
    info "Installing build dependencies via apt ..."
    $SUDO apt-get update -qq
    $SUDO apt-get install -y --no-install-recommends \
        build-essential \
        libtool \
        autotools-dev \
        automake \
        pkg-config \
        bsdmainutils \
        python3 \
        libevent-dev \
        libboost-dev \
        libboost-system-dev \
        libboost-filesystem-dev \
        libsqlite3-dev \
        libminiupnpc-dev \
        libnatpmp-dev \
        libzmq3-dev \
        git

    # ── 2. Clone and build ────────────────────────────────────────────────────
    BUILD_DIR="$(mktemp -d /tmp/qbtc-build.XXXXXX)"
    info "Cloning repository into ${BUILD_DIR} ..."
    git clone --depth 1 "${REPO_URL}" "${BUILD_DIR}/QuantBTC"

    info "Building qBTC (this may take 10–20 minutes) ..."
    cd "${BUILD_DIR}/QuantBTC"
    ./autogen.sh
    ./configure \
        --with-incompatible-bdb \
        --with-gui=no \
        --disable-tests \
        --disable-bench
    make -j"$(nproc)"
    strip src/bitcoind src/bitcoin-cli

    # ── 3. Install binaries ───────────────────────────────────────────────────
    info "Installing binaries to /usr/local/bin/ ..."
    $SUDO install -m 755 src/bitcoind   /usr/local/bin/bitcoind
    $SUDO install -m 755 src/bitcoin-cli /usr/local/bin/bitcoin-cli

    # ── 4. Install config ─────────────────────────────────────────────────────
    info "Installing config to /etc/qbtc/bitcoin.conf ..."
    $SUDO mkdir -p /etc/qbtc
    $SUDO install -m 644 contrib/qbtc-testnet/qbtc-testnet.conf /etc/qbtc/bitcoin.conf

    # ── 5. Create qbtc system user ────────────────────────────────────────────
    if ! id -u qbtc &>/dev/null; then
        info "Creating system user 'qbtc' ..."
        $SUDO useradd --system --no-create-home --shell /usr/sbin/nologin qbtc
    else
        info "System user 'qbtc' already exists – skipping."
    fi

    # ── 6. Install systemd service ────────────────────────────────────────────
    info "Installing systemd service file ..."
    $SUDO install -m 644 \
        contrib/qbtc-testnet/qbtc-node.service \
        /etc/systemd/system/qbtc-node.service

    # ── 7. Enable and start the service ───────────────────────────────────────
    info "Enabling and starting qbtc-node.service ..."
    $SUDO systemctl daemon-reload
    $SUDO systemctl enable qbtc-node.service
    $SUDO systemctl start  qbtc-node.service

    # ── 8. Clean up build directory ───────────────────────────────────────────
    cd /
    rm -rf "${BUILD_DIR}"

    # ── 9. Print status ───────────────────────────────────────────────────────
    success "qBTC testnet node installed and running!"
    echo ""
    $SUDO systemctl status qbtc-node.service --no-pager || true
    echo ""
    info "Useful commands:"
    echo "  View logs:    sudo journalctl -u qbtc-node -f"
    echo "  Chain info:   bitcoin-cli -qbtctestnet -datadir=/var/lib/qbtc getblockchaininfo"
    echo "  Peer count:   bitcoin-cli -qbtctestnet -datadir=/var/lib/qbtc getconnectioncount"
    echo "  Stop node:    sudo systemctl stop qbtc-node"
    echo "  Restart node: sudo systemctl restart qbtc-node"
}

# ── Entry point ───────────────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║      qBTC Testnet Node – Installer           ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
echo ""

if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    docker_install
else
    warn "Docker not found or not running. Falling back to native build."
    native_install
fi
