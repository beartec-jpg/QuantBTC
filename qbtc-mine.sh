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
CLI="./src/bitcoin-cli -${CHAIN}"

get_mining_descriptor() {
    local addr
    addr=$($CLI getnewaddress "" "bech32")
    $CLI getaddressinfo "$addr" | python3 -c 'import json,sys; print(json.load(sys.stdin)["desc"])'
}

status() {
    $CLI getblockchaininfo | python3 -c "
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
DESC="$(get_mining_descriptor)"
for i in $(seq 1 "$COUNT"); do
    RESULT=$($CLI generateblock "$ADDR" '[]' 2>&1)
    HASH=$(echo "$RESULT" | python3 -c "import sys,json; print(json.load(sys.stdin)['hash'][:16])" 2>/dev/null)
    HEIGHT=$($CLI getblockcount)
    echo "  [$i/$COUNT] height=$HEIGHT  hash=${HASH}..."
    [ "$i" -lt "$COUNT" ] && sleep 1
done

echo ""
status
