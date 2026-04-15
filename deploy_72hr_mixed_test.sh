#!/usr/bin/env bash
# deploy_72hr_mixed_test.sh — Deploy and launch 72-hour 90/10 ECDSA/PQC test
#
# Orchestrates from the dev machine:
#   1. Logs start positions on all 3 nodes
#   2. Adds pqcmode=classical to N2/N3 configs (N1 stays hybrid)
#   3. Restarts N2/N3 daemons
#   4. Applies cpulimit (40%) to all 3 daemons
#   5. Deploys surge_72hr_mixed.sh to all 3 nodes
#   6. Launches test in screen sessions on all 3

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEST_SCRIPT="$SCRIPT_DIR/surge_72hr_mixed.sh"

# ── Node definitions ─────────────────────────────────────────────
declare -A N1=( [ip]="46.62.156.169" [pass]="rmKPEg3HrnHf"
                [rpcuser]="qbtcseed"  [rpcpass]="seednode1_rpc_2026"
                [label]="hel1-2"      [role]="hybrid" )

declare -A N2=( [ip]="37.27.47.236"  [pass]="9rPdmic9Nf7X"
                [rpcuser]="qbtcseed"  [rpcpass]="seednode2_rpc_2026"
                [label]="hel1-3"      [role]="classical" )

declare -A N3=( [ip]="89.167.109.241" [pass]="meMjm7s9kPqb"
                [rpcuser]="qbtcverify"  [rpcpass]="verify_node3_2026"
                [label]="hel1-4"      [role]="classical" )

SSH_OPTS="-o StrictHostKeyChecking=no -o ConnectTimeout=10"

ssh_cmd() {
    local ip="$1" pass="$2"; shift 2
    sshpass -p "$pass" ssh $SSH_OPTS "root@${ip}" "$@"
}

scp_cmd() {
    local ip="$1" pass="$2" src="$3" dst="$4"
    sshpass -p "$pass" scp $SSH_OPTS "$src" "root@${ip}:${dst}"
}

echo "============================================================"
echo "  Deploy 72-Hour Mixed Test (90% ECDSA / 10% ML-DSA)"
echo "  $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "============================================================"

# ── 1. Log start positions ───────────────────────────────────────
echo ""
echo "▸ [1/6] Logging start positions..."

for node_var in N1 N2 N3; do
    declare -n node=$node_var
    echo ""
    echo "  --- ${node[label]} (${node[ip]}) ---"
    ssh_cmd "${node[ip]}" "${node[pass]}" "
        CLI='/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet'
        echo \"  Height:  \$(\$CLI getblockcount 2>/dev/null)\"
        echo \"  Hash:    \$(\$CLI getbestblockhash 2>/dev/null)\"
        echo \"  Peers:   \$(\$CLI getconnectioncount 2>/dev/null)\"
        echo \"  Mempool: \$(\$CLI getmempoolinfo 2>/dev/null | grep '\"size\"' | head -1)\"
        echo \"  Balance: \$(\$CLI -rpcwallet=miner getbalance 2>/dev/null)\"
        echo \"  PQCMode: \$(\$CLI getpqcinfo 2>/dev/null | grep pqc_mode)\"
        echo \"  Uptime:  \$(\$CLI uptime 2>/dev/null)s\"
    " 2>&1 | sed 's/^/  /'
done

# ── 2. Configure N2/N3 for classical mode ────────────────────────
echo ""
echo "▸ [2/6] Configuring N2 and N3 for pqcmode=classical..."

for node_var in N2 N3; do
    declare -n node=$node_var
    echo "  ${node[label]} (${node[ip]}):"

    ssh_cmd "${node[ip]}" "${node[pass]}" '
        CONF="/root/.bitcoin/bitcoin.conf"
        # Remove any existing pqcmode line
        sed -i "/^pqcmode=/d" "$CONF"
        # Add pqcmode=classical after the chain= line
        sed -i "/^chain=qbtctestnet/a pqcmode=classical" "$CONF"
        echo "  Added pqcmode=classical to bitcoin.conf"
        grep -n "pqcmode" "$CONF"
    ' 2>&1 | sed 's/^/    /'
done

# ── 3. Restart N2/N3 daemons ────────────────────────────────────
echo ""
echo "▸ [3/6] Restarting N2 and N3 daemons..."

for node_var in N2 N3; do
    declare -n node=$node_var
    echo "  ${node[label]} (${node[ip]}):"

    ssh_cmd "${node[ip]}" "${node[pass]}" '
        # Stop existing mining screens
        for s in $(screen -ls 2>/dev/null | grep -oP "\d+\.\S+"); do
            screen -S "$s" -X quit 2>/dev/null || true
        done
        pkill -f "generatetoaddress" 2>/dev/null || true

        # Graceful stop
        /root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet stop 2>/dev/null || true
        echo "    Stopping daemon..."
        sleep 10

        # Kill if still running
        pkill -f bitcoind 2>/dev/null || true
        sleep 3

        # Restart
        echo "    Starting daemon..."
        /root/QuantBTC/src/bitcoind -daemon -conf=/root/.bitcoin/bitcoin.conf
        sleep 10

        # Verify
        HEIGHT=$(/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet getblockcount 2>/dev/null || echo "FAIL")
        PQCMODE=$(/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet getpqcinfo 2>/dev/null | grep "pqc_mode" || echo "unknown")
        echo "    Restarted: height=$HEIGHT $PQCMODE"
    ' 2>&1 | sed 's/^/    /'
done

# Wait for N2/N3 to sync back up
echo "  Waiting 30s for sync..."
sleep 30

# Verify all 3 nodes are synced
echo "  Verifying sync:"
for node_var in N1 N2 N3; do
    declare -n node=$node_var
    H=$(ssh_cmd "${node[ip]}" "${node[pass]}" '/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet getblockcount 2>/dev/null')
    P=$(ssh_cmd "${node[ip]}" "${node[pass]}" '/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet getconnectioncount 2>/dev/null')
    echo "    ${node[label]}: height=$H peers=$P"
done

# ── 4. Stop existing mining on N1 ───────────────────────────────
echo ""
echo "▸ [4/6] Stopping existing mining on N1..."
ssh_cmd "${N1[ip]}" "${N1[pass]}" '
    for s in $(screen -ls 2>/dev/null | grep -oP "\d+\.\S+"); do
        screen -S "$s" -X quit 2>/dev/null || true
    done
    pkill -f "generatetoaddress" 2>/dev/null || true
    echo "  Mining stopped"
' 2>&1 | sed 's/^/  /'

# ── 5. Deploy test script to all nodes ──────────────────────────
echo ""
echo "▸ [5/6] Deploying test script..."

for node_var in N1 N2 N3; do
    declare -n node=$node_var
    scp_cmd "${node[ip]}" "${node[pass]}" "$TEST_SCRIPT" "/root/surge_72hr_mixed.sh"
    ssh_cmd "${node[ip]}" "${node[pass]}" 'chmod +x /root/surge_72hr_mixed.sh'
    echo "  ${node[label]} ✓"
done

# ── 6. Launch test on all 3 nodes ───────────────────────────────
echo ""
echo "▸ [6/6] Launching 72-hour test..."

# N1: hybrid — 10% of txs (low rate)
echo "  N1 (hybrid, ~10% of total tx volume):"
ssh_cmd "${N1[ip]}" "${N1[pass]}" "
    screen -dmS surge72 bash -c '
        export NODE_LABEL=\"${N1[label]}\"
        export NODE_ROLE=\"hybrid\"
        export RPCPORT=28332
        export RPCUSER=\"${N1[rpcuser]}\"
        export RPCPASSWORD=\"${N1[rpcpass]}\"
        export TX_PER_ROUND=1
        export TX_SLEEP=3
        export MINE_SLEEP=5
        export SURGE_TX=5
        export SURGE_SLEEP=1
        /root/surge_72hr_mixed.sh 72
    '
    echo \"    Screen session started\"
    screen -ls
" 2>&1 | sed 's/^/    /'

sleep 5

# N2: classical — 45% of txs (high rate)
echo "  N2 (classical, ~45% of total tx volume):"
ssh_cmd "${N2[ip]}" "${N2[pass]}" "
    screen -dmS surge72 bash -c '
        export NODE_LABEL=\"${N2[label]}\"
        export NODE_ROLE=\"classical\"
        export RPCPORT=28332
        export RPCUSER=\"${N2[rpcuser]}\"
        export RPCPASSWORD=\"${N2[rpcpass]}\"
        export TX_PER_ROUND=5
        export TX_SLEEP=3
        export MINE_SLEEP=5
        export SURGE_TX=20
        export SURGE_SLEEP=1
        /root/surge_72hr_mixed.sh 72
    '
    echo \"    Screen session started\"
    screen -ls
" 2>&1 | sed 's/^/    /'

sleep 5

# N3: classical — 45% of txs (high rate)
echo "  N3 (classical, ~45% of total tx volume):"
ssh_cmd "${N3[ip]}" "${N3[pass]}" "
    screen -dmS surge72 bash -c '
        export NODE_LABEL=\"${N3[label]}\"
        export NODE_ROLE=\"classical\"
        export RPCPORT=28332
        export RPCUSER=\"${N3[rpcuser]}\"
        export RPCPASSWORD=\"${N3[rpcpass]}\"
        export TX_PER_ROUND=5
        export TX_SLEEP=3
        export MINE_SLEEP=5
        export SURGE_TX=20
        export SURGE_SLEEP=1
        /root/surge_72hr_mixed.sh 72
    '
    echo \"    Screen session started\"
    screen -ls
" 2>&1 | sed 's/^/    /'

echo ""
echo "============================================================"
echo "  72-HOUR MIXED TEST LAUNCHED"
echo "  Started: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo "  Ends:    $(date -u -d '+72 hours' '+%Y-%m-%d %H:%M:%S UTC' 2>/dev/null || echo 'in 72 hours')"
echo ""
echo "  N1 (${N1[ip]}): hybrid  — ~10% of txs (baseline 0.33 tx/s)"
echo "  N2 (${N2[ip]}): classical — ~45% of txs (baseline 1.67 tx/s)"
echo "  N3 (${N3[ip]}): classical — ~45% of txs (baseline 1.67 tx/s)"
echo "  CPU limit: 40% per node"
echo ""
echo "  Monitor:"
echo "    ssh root@${N1[ip]}  # pass: ${N1[pass]}"
echo "    screen -r surge72   # attach to test"
echo "    tail -f /root/surge72_mixed/surge_hel1-2.log"
echo "    cat /root/surge72_mixed/metrics_hel1-2.csv | tail -5"
echo ""
echo "  Stop all:"
echo "    for each node: kill \$(cat /tmp/surge72_mixed.pid)"
echo "============================================================"
