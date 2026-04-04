#!/usr/bin/env bash
# docker-entrypoint.sh – Entrypoint for the qBTC testnet Docker image.
#
# Supported environment variables:
#   SEEDNODE      – Address of a bootstrap seed node (host:port).
#                   If set, -seednode=<SEEDNODE> is appended to the command.
#   RPCUSER       – RPC username (optional; passed via -rpcuser=).
#   RPCPASSWORD   – RPC password (optional; passed via -rpcpassword=).
#
# Any additional arguments are forwarded verbatim to bitcoind.

set -euo pipefail

CMD=(
    bitcoind
    -qbtctestnet
    -conf=/etc/qbtc/bitcoin.conf
    -datadir=/data
    -printtoconsole
)

if [[ -n "${SEEDNODE:-}" ]]; then
    CMD+=("-seednode=${SEEDNODE}")
fi

if [[ -n "${RPCUSER:-}" ]]; then
    CMD+=("-rpcuser=${RPCUSER}")
fi

if [[ -n "${RPCPASSWORD:-}" ]]; then
    CMD+=("-rpcpassword=${RPCPASSWORD}")
fi

# Forward any extra arguments passed to the container
CMD+=("$@")

exec "${CMD[@]}"
