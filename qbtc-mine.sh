#!/usr/bin/env bash
# qbtc-mine.sh — Mine blocks on QuantumBTC testnet
#
# Usage:
#   ./qbtc-mine.sh [count] [chain]
#   ./qbtc-mine.sh 10              # mine 10 blocks on qbtctestnet
#   ./qbtc-mine.sh 5 regtest       # mine 5 blocks on regtest
#   ./qbtc-mine.sh                 # mine 1 block on qbtctestnet
#   ./qbtc-mine.sh status          # show chain info only

set -euo pipefail

COUNT="${1:-1}"
CHAIN="${2:-qbtctestnet}"
DATADIR="${DATADIR:-}"
WALLET_NAME="${WALLET_NAME:-miner}"
RPCUSER="${RPCUSER:-}"
RPCPASSWORD="${RPCPASSWORD:-}"

CLI=("./src/bitcoin-cli" "-${CHAIN}")
if [ -n "$DATADIR" ]; then
    CLI+=("-datadir=$DATADIR")
fi
if [ -n "$RPCUSER" ]; then
    CLI+=("-rpcuser=$RPCUSER")
fi
if [ -n "$RPCPASSWORD" ]; then
    CLI+=("-rpcpassword=$RPCPASSWORD")
fi

cli() {
    "${CLI[@]}" "$@"
}

ensure_wallet() {
    if ! cli -rpcwallet="$WALLET_NAME" getwalletinfo >/dev/null 2>&1; then
        cli createwallet "$WALLET_NAME" >/dev/null 2>&1 || true
    fi
}

get_mining_address() {
    local addr
    ensure_wallet
    addr=$(cli -rpcwallet="$WALLET_NAME" getnewaddress "" "bech32")
    printf '%s\n' "$addr"
}

status() {
    cli getblockchaininfo | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"  chain={d['chain']}  blocks={d['blocks']}  tips={d['dag_tips']}  \")
print(f\"  ticker={d['ticker']}  dag={d['dagmode']}  pqc={d['pqc']}  k={d['ghostdag_k']}\")
"
}

if [ "$COUNT" = "status" ]; then
    status
    exit 0
fi

echo "Mining $COUNT block(s) on $CHAIN..."
ADDR="$(get_mining_address)"
for i in $(seq 1 "$COUNT"); do
    RESULT=$(cli generatetoaddress 1 "$ADDR")
    HASH=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)[0][:16])" 2>/dev/null)
    HEIGHT=$(cli getblockcount)
    echo "  [$i/$COUNT] height=$HEIGHT  hash=${HASH}..."
    [ "$i" -lt "$COUNT" ] && sleep 1
done

echo ""
status
