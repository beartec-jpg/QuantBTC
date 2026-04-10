#!/usr/bin/env bash
# surge_control.sh — Deploy, start, monitor the 72-hour surge test across all nodes
#
# Usage:
#   ./surge_control.sh deploy    — SCP script to all 3 nodes
#   ./surge_control.sh start     — Stop old scripts, start 72hr test on all nodes
#   ./surge_control.sh status    — Show CPU, block height, mode, recent logs
#   ./surge_control.sh metrics   — Download metrics CSV from all nodes
#   ./surge_control.sh stop      — Kill test on all nodes, revert to baseline mine_and_tx
#   ./surge_control.sh report    — Collect final report from all nodes

set -uo pipefail

# ── Node inventory ───────────────────────────────────────────────
declare -A NODE_IP=( [S1]="46.62.156.169" [S2]="37.27.47.236" [S3]="89.167.109.241" )
declare -A NODE_PW=( [S1]="P9gismTbVhjn" [S2]="nUXtncccj44b" [S3]="aqwUsaVpWjeV" )
declare -A NODE_RPCUSER=( [S1]="qbtcseed" [S2]="qbtcseed" [S3]="qbtcverify" )
declare -A NODE_RPCPASS=( [S1]="seednode1_rpc_2026" [S2]="seednode2_rpc_2026" [S3]="verify_node3_2026" )
NODES=(S1 S2 S3)

SCRIPT_PATH="$(cd "$(dirname "$0")" && pwd)/surge_test_72hr.sh"

ssh_node() {
    local node="$1"; shift
    sshpass -p "${NODE_PW[$node]}" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 "root@${NODE_IP[$node]}" "$@"
}

scp_node() {
    local node="$1" src="$2" dst="$3"
    sshpass -p "${NODE_PW[$node]}" scp -o StrictHostKeyChecking=no "$src" "root@${NODE_IP[$node]}:$dst"
}

# ── Commands ─────────────────────────────────────────────────────
cmd_deploy() {
    echo "Deploying surge_test_72hr.sh to all nodes..."
    for n in "${NODES[@]}"; do
        scp_node "$n" "$SCRIPT_PATH" "/root/surge_test_72hr.sh"
        ssh_node "$n" "chmod +x /root/surge_test_72hr.sh"
        echo "  $n (${NODE_IP[$n]}): deployed"
    done
    echo "Done."
}

cmd_start() {
    echo "Starting 72-hour surge test on all nodes..."
    for n in "${NODES[@]}"; do
        # Kill any existing mine_and_tx or surge_test
        ssh_node "$n" 'kill $(cat /tmp/surge_test.pid 2>/dev/null) 2>/dev/null; kill $(cat /tmp/mine_and_tx.pid 2>/dev/null) 2>/dev/null; pkill -f "mine_and_tx\|surge_test" 2>/dev/null; sleep 1' 2>/dev/null || true

        # Start surge test
        ssh_node "$n" "nohup env RPCUSER=${NODE_RPCUSER[$n]} RPCPASSWORD=${NODE_RPCPASS[$n]} /root/surge_test_72hr.sh 72 > /dev/null 2>&1 & disown"
        sleep 2
        local pid
        pid=$(ssh_node "$n" "cat /tmp/surge_test.pid 2>/dev/null || echo NONE")
        echo "  $n (${NODE_IP[$n]}): started (PID=${pid})"
    done
    echo ""
    echo "Test running. Check status with: $0 status"
}

cmd_status() {
    printf '%-4s %-16s %-8s %-7s %-6s %-8s %-8s %-6s %s\n' \
        "Node" "IP" "CPU%" "Mode" "Block" "Mined" "TX" "Pool" "Last Log"
    printf '%-4s %-16s %-8s %-7s %-6s %-8s %-8s %-6s %s\n' \
        "----" "----------------" "--------" "-------" "------" "--------" "--------" "------" "--------"
    for n in "${NODES[@]}"; do
        local data
        data=$(ssh_node "$n" '
            cpu=$(top -bn1 | sed -n "3p" | grep -oP "[\d.]+ id" | cut -d" " -f1)
            used=$(echo "100 - ${cpu:-0}" | bc 2>/dev/null || echo "?")
            mode=$(cat /tmp/surge_mode 2>/dev/null || echo "?")
            block=$(bitcoin-cli -rpcport=28332 -rpcuser='"${NODE_RPCUSER[$n]}"' -rpcpassword='"${NODE_RPCPASS[$n]}"' getblockcount 2>/dev/null || echo "?")
            mined=$(cat /tmp/surge_mined_count 2>/dev/null || echo "?")
            tx=$(cat /tmp/surge_tx_count 2>/dev/null || echo "?")
            pool=$(bitcoin-cli -rpcport=28332 -rpcuser='"${NODE_RPCUSER[$n]}"' -rpcpassword='"${NODE_RPCPASS[$n]}"' getmempoolinfo 2>/dev/null | grep "\"size\"" | grep -o "[0-9]*" || echo "?")
            lastlog=$(tail -1 /tmp/surge_test.log 2>/dev/null | cut -c1-60 || echo "no log")
            echo "${used}|${mode}|${block}|${mined}|${tx}|${pool}|${lastlog}"
        ' 2>/dev/null || echo "?|?|?|?|?|?|unreachable")
        IFS='|' read -r cpu mode block mined tx pool lastlog <<< "$data"
        printf '%-4s %-16s %-8s %-7s %-6s %-8s %-8s %-6s %s\n' \
            "$n" "${NODE_IP[$n]}" "${cpu}%" "$mode" "$block" "$mined" "$tx" "$pool" "$lastlog"
    done
}

cmd_metrics() {
    mkdir -p /tmp/surge_metrics
    for n in "${NODES[@]}"; do
        local dest="/tmp/surge_metrics/${n}_metrics.csv"
        scp_node "$n" "/tmp/surge_metrics.csv" "$dest" 2>/dev/null && \
            echo "  $n: $(wc -l < "$dest") rows → $dest" || \
            echo "  $n: no metrics file yet"
    done
}

cmd_stop() {
    echo "Stopping surge test on all nodes..."
    for n in "${NODES[@]}"; do
        ssh_node "$n" '
            echo "baseline" > /tmp/surge_mode 2>/dev/null
            kill $(cat /tmp/surge_test.pid 2>/dev/null) 2>/dev/null
            pkill -f surge_test 2>/dev/null
            sleep 1
            ps aux | grep -c "[s]urge_test"
        ' 2>/dev/null
        echo "  $n: stopped"
    done
    echo ""
    echo "To restart baseline mining: use mine_and_tx.sh manually or run '$0 start'"
}

cmd_report() {
    echo "=== 72-HOUR SURGE TEST FINAL REPORT ==="
    echo ""
    for n in "${NODES[@]}"; do
        echo "--- $n (${NODE_IP[$n]}) ---"
        ssh_node "$n" '
            if [ -f /tmp/surge_test.log ]; then
                grep -E "FINAL REPORT|Blocks:|UTXO|Supply:|Mined:|TX sent:|Disk:|SURGE.*END|START STATE" /tmp/surge_test.log | tail -20
            else
                echo "  No test log found"
            fi
            echo ""
        ' 2>/dev/null || echo "  Unreachable"
        echo ""
    done
}

# ── Main ─────────────────────────────────────────────────────────
CMD="${1:-status}"
case "$CMD" in
    deploy)  cmd_deploy ;;
    start)   cmd_start ;;
    status)  cmd_status ;;
    metrics) cmd_metrics ;;
    stop)    cmd_stop ;;
    report)  cmd_report ;;
    *)
        echo "Usage: $0 {deploy|start|status|metrics|stop|report}"
        exit 1
        ;;
esac
