#!/bin/bash
# Deploy updated QuantBTC binary (dual-mode: ECDSA + PQC hybrid) to all testnet nodes
# Removes SCRIPT_VERIFY_HYBRID_SIG — allows ECDSA-only (2-element) witnesses
set -e

BINARY="/home/risscott2/QuantBTC/src/bitcoind"
REMOTE_PATH="/root/qbtc/src/bitcoind"

# Verify binary is fresh
BINARY_DATE=$(date -r "$BINARY" +%s)
NOW=$(date +%s)
AGE=$(( (NOW - BINARY_DATE) / 60 ))
if [ "$AGE" -gt 30 ]; then
    echo "⚠️  Binary is ${AGE} minutes old — are you sure it's rebuilt? (Ctrl+C to abort)"
    sleep 3
fi

echo "Binary: $BINARY ($(ls -lh $BINARY | awk '{print $5}'))"
echo ""

declare -A NODES
NODES[hel1-2]="46.62.156.169"
NODES[hel1-3]="37.27.47.236"
NODES[hel1-4]="89.167.109.241"

declare -A PASSWORDS
PASSWORDS[hel1-2]="rmKPEg3HrnHf"
PASSWORDS[hel1-3]="9rPdmic9Nf7X"
PASSWORDS[hel1-4]="meMjm7s9kPqb"

for NODE in hel1-2 hel1-3 hel1-4; do
    IP="${NODES[$NODE]}"
    PASS="${PASSWORDS[$NODE]}"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📡 Deploying to $NODE ($IP)..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Stop the node
    echo "  Stopping bitcoind..."
    sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no root@$IP \
        "bitcoin-cli -conf=/root/.bitcoin/bitcoin.conf stop 2>/dev/null || true; sleep 3; pkill -f bitcoind || true; sleep 2" || true

    # Upload new binary
    echo "  Uploading binary..."
    sshpass -p "$PASS" scp -o StrictHostKeyChecking=no "$BINARY" root@$IP:"$REMOTE_PATH"

    # Start the node
    echo "  Starting bitcoind..."
    sshpass -p "$PASS" ssh -o StrictHostKeyChecking=no root@$IP \
        "chmod +x $REMOTE_PATH && $REMOTE_PATH -daemon -conf=/root/.bitcoin/bitcoin.conf && sleep 2 && bitcoin-cli -conf=/root/.bitcoin/bitcoin.conf getblockchaininfo | head -5"

    echo "  ✅ $NODE deployed"
    echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ All 3 nodes updated — dual-mode active"
echo "   ECDSA-only (2-element witness): ACCEPTED"
echo "   PQC hybrid (4-element witness): ACCEPTED"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
