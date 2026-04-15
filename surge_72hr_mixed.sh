#!/usr/bin/env bash
# surge_72hr_mixed.sh — 72-hour endurance test with 90% ECDSA / 10% ML-DSA
#
# Runs INDEPENDENTLY on each node.  Deploy with per-node env vars:
#
#   N1 (hybrid):   TX_PER_ROUND=1   TX_SLEEP=3   SURGE_TX=5   SURGE_SLEEP=1
#   N2 (classical):TX_PER_ROUND=5   TX_SLEEP=3   SURGE_TX=20  SURGE_SLEEP=1
#   N3 (classical):TX_PER_ROUND=5   TX_SLEEP=3   SURGE_TX=20  SURGE_SLEEP=1
#
# Combined baseline: N1≈0.33 + N2≈1.67 + N3≈1.67 = ~3.7 tx/s (N1≈9%)
# Combined surge:    N1≈5    + N2≈20   + N3≈20   = ~45 tx/s   (N1≈11%)
#
# CPU capped at 40% via cpulimit on bitcoind.
#
# Usage:
#   chmod +x surge_72hr_mixed.sh
#   nohup ./surge_72hr_mixed.sh [duration_hours] &
#
# Stop:  kill $(cat /tmp/surge72_mixed.pid)

set -o pipefail

# ── Per-node tunables (override via env) ─────────────────────────
DURATION_HOURS="${1:-72}"
DURATION_SECS=$((DURATION_HOURS * 3600))

NODE_LABEL="${NODE_LABEL:-$(hostname -s)}"
NODE_ROLE="${NODE_ROLE:-hybrid}"        # "hybrid" or "classical"

# RPC (read from bitcoin.conf or env)
RPCPORT="${RPCPORT:-28332}"
RPCUSER="${RPCUSER:-qbtcseed}"
RPCPASSWORD="${RPCPASSWORD:-changeme}"

CLI="/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet \
     -rpcport=${RPCPORT} -rpcuser=${RPCUSER} -rpcpassword=${RPCPASSWORD}"

# Baseline rates
BASE_TX_PER_ROUND="${TX_PER_ROUND:-1}"
BASE_TX_SLEEP="${TX_SLEEP:-3}"
BASE_MINE_SLEEP="${MINE_SLEEP:-5}"

# Surge rates
SURGE_TX_PER_ROUND="${SURGE_TX:-5}"
SURGE_TX_SLEEP="${SURGE_SLEEP:-1}"
SURGE_MINE_SLEEP="1"

# Surge schedule (same as original 72hr test)
SURGE_INTERVAL=14400    # 4 hours between surges
SURGE_DURATION=1200     # 20 minutes per surge

# Wallet config
NUM_WALLETS=10
MINER_WALLET="miner"
FUND_AMOUNT="5.0"

# Files
LOGDIR="/root/surge72_mixed"
LOG="${LOGDIR}/surge_${NODE_LABEL}.log"
METRICS="${LOGDIR}/metrics_${NODE_LABEL}.csv"
MODEFILE="/tmp/surge72_mode"
PIDFILE="/tmp/surge72_mixed.pid"
STARTFILE="${LOGDIR}/start_state_${NODE_LABEL}.json"

CPU_LIMIT=40

# ── Helpers ──────────────────────────────────────────────────────
cli() {
    $CLI "$@" 2>/dev/null
}

cliw() {
    local w="$1"; shift
    $CLI -rpcwallet="$w" "$@" 2>/dev/null
}

log() {
    printf '[%s] [%s] [%s] %s\n' \
        "$(date -u '+%Y-%m-%d %H:%M:%S UTC')" "$NODE_LABEL" "$NODE_ROLE" "$*" \
        | tee -a "$LOG"
}

get_mode() {
    cat "$MODEFILE" 2>/dev/null || echo "baseline"
}

# ── CPU cap ──────────────────────────────────────────────────────
apply_cpu_limit() {
    local pid
    pid=$(pgrep -f '/root/QuantBTC/src/bitcoind' | head -1)
    if [[ -z "$pid" ]]; then
        log "WARN: bitcoind not found for cpulimit"
        return
    fi
    # Kill any existing cpulimit on this PID
    pkill -f "cpulimit.*-p ${pid}" 2>/dev/null || true
    sleep 1
    # 40% of total CPU (2 cores = 200% max, so 40% = 80% of cpulimit scale)
    local limit=$((CPU_LIMIT * 2))
    cpulimit -p "$pid" -l "$limit" -b 2>/dev/null
    log "CPU limited: bitcoind pid=$pid capped at ${CPU_LIMIT}% total (cpulimit -l ${limit})"
}

# ── Wallet setup ─────────────────────────────────────────────────
declare -a WALLETS=()
declare -a ADDRS=()

setup_wallets() {
    log "Setting up $NUM_WALLETS wallets for ${NODE_ROLE} mode..."
    for i in $(seq 1 "$NUM_WALLETS"); do
        local WNAME="mix72_${NODE_LABEL}_w${i}"
        if ! cliw "$WNAME" getwalletinfo >/dev/null 2>&1; then
            cli createwallet "$WNAME" >/dev/null 2>&1 || \
            cli loadwallet "$WNAME" >/dev/null 2>&1 || true
        fi
        WALLETS+=("$WNAME")
        local ADDR
        ADDR=$(cliw "$WNAME" getnewaddress "" bech32)
        ADDRS+=("$ADDR")
    done
    log "Wallets ready: ${#WALLETS[@]} (${NODE_ROLE} signatures)"

    # Fund each wallet
    log "Funding wallets (${FUND_AMOUNT} QBTC each)..."
    local MINE_ADDR
    MINE_ADDR=$(cliw "$MINER_WALLET" getnewaddress "" bech32)
    local funded=0
    for ADDR in "${ADDRS[@]}"; do
        if cliw "$MINER_WALLET" sendtoaddress "$ADDR" "$FUND_AMOUNT" "" "" false true >/dev/null 2>&1; then
            ((funded++))
        fi
    done
    # Mine to confirm funding
    cli generatetoaddress 1 "$MINE_ADDR" 999999999 >/dev/null 2>&1
    sleep 2
    log "Funded $funded/${#WALLETS[@]} wallets and confirmed"
}

# ── Record start state ───────────────────────────────────────────
record_start_state() {
    local blocks height utxo_count supply mempool_size disk_usage
    blocks=$(cli getblockcount 2>/dev/null || echo 0)
    local best_hash
    best_hash=$(cli getbestblockhash 2>/dev/null || echo "unknown")
    utxo_count=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
    supply=$(cli gettxoutsetinfo 2>/dev/null | grep '"total_amount"' | grep -oP '[\d.]+' || echo 0)
    mempool_size=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | head -1 | grep -o '[0-9]*' || echo 0)
    local peers
    peers=$(cli getconnectioncount 2>/dev/null || echo 0)
    local balance
    balance=$(cliw "$MINER_WALLET" getbalance 2>/dev/null || echo 0)

    cat > "$STARTFILE" <<EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "node": "$NODE_LABEL",
  "role": "$NODE_ROLE",
  "block_height": $blocks,
  "best_block_hash": "$best_hash",
  "utxo_count": $utxo_count,
  "total_supply": "$supply",
  "mempool_size": $mempool_size,
  "peers": $peers,
  "miner_balance": "$balance",
  "cpu_limit_pct": $CPU_LIMIT,
  "baseline_tx_per_round": $BASE_TX_PER_ROUND,
  "baseline_tx_sleep": $BASE_TX_SLEEP,
  "baseline_mine_sleep": $BASE_MINE_SLEEP,
  "surge_tx_per_round": $SURGE_TX_PER_ROUND,
  "surge_tx_sleep": $SURGE_TX_SLEEP,
  "surge_mine_sleep": $SURGE_MINE_SLEEP,
  "duration_hours": $DURATION_HOURS
}
EOF

    log "START STATE recorded:"
    log "  Block height:  $blocks"
    log "  Best hash:     $best_hash"
    log "  UTXO count:    $utxo_count"
    log "  Supply:        $supply QBTC"
    log "  Mempool:       $mempool_size"
    log "  Peers:         $peers"
    log "  Miner balance: $balance QBTC"
}

# ── Mining loop ──────────────────────────────────────────────────
mining_loop() {
    local mined=0
    local mine_addr
    mine_addr=$(cliw "$MINER_WALLET" getnewaddress "" bech32 2>/dev/null)

    while true; do
        local mode
        mode=$(get_mode)
        local sleep_s
        if [[ "$mode" == "surge" ]]; then
            sleep_s=$SURGE_MINE_SLEEP
        else
            sleep_s=$BASE_MINE_SLEEP
        fi

        cli generatetoaddress 1 "$mine_addr" 999999999 >/dev/null 2>&1 && ((mined++))
        echo "$mined" > /tmp/surge72_mined_count
        sleep "$sleep_s"
    done
}

# ── Transaction loop ─────────────────────────────────────────────
tx_loop() {
    local total_sent=0
    local total_fail=0

    while true; do
        local mode
        mode=$(get_mode)

        local txr txs
        if [[ "$mode" == "surge" ]]; then
            txr=$SURGE_TX_PER_ROUND
            txs=$SURGE_TX_SLEEP
        else
            txr=$BASE_TX_PER_ROUND
            txs=$BASE_TX_SLEEP
        fi

        local sent_round=0
        local fail_round=0
        for ((i = 0; i < txr; i++)); do
            # Pick random source and destination wallets
            local src_idx=$((RANDOM % ${#WALLETS[@]}))
            local dst_idx=$((RANDOM % ${#WALLETS[@]}))
            while [[ $dst_idx -eq $src_idx ]]; do
                dst_idx=$((RANDOM % ${#WALLETS[@]}))
            done

            local src_wallet="${WALLETS[$src_idx]}"
            local dst_addr="${ADDRS[$dst_idx]}"

            # Random small amount (0.001 – 0.01 QBTC)
            local amount
            amount=$(awk "BEGIN{srand(); printf \"%.8f\", 0.001 + rand() * 0.009}")

            if cliw "$src_wallet" sendtoaddress "$dst_addr" "$amount" "" "" false true >/dev/null 2>&1; then
                ((sent_round++))
            else
                ((fail_round++))
            fi
        done

        total_sent=$((total_sent + sent_round))
        total_fail=$((total_fail + fail_round))
        echo "$total_sent" > /tmp/surge72_tx_count
        echo "$total_fail" > /tmp/surge72_tx_fail

        sleep "$txs"
    done
}

# ── UTXO refund/consolidation loop ──────────────────────────────
refund_loop() {
    while true; do
        sleep 600   # every 10 minutes
        # Top up any wallet below 1.0 QBTC from miner
        local mine_addr
        mine_addr=$(cliw "$MINER_WALLET" getnewaddress "" bech32 2>/dev/null)
        for i in $(seq 0 $(( ${#WALLETS[@]} - 1 ))); do
            local bal
            bal=$(cliw "${WALLETS[$i]}" getbalance 2>/dev/null || echo "0")
            if awk "BEGIN{exit !($bal < 1.0)}" 2>/dev/null; then
                cliw "$MINER_WALLET" sendtoaddress "${ADDRS[$i]}" "2.0" "" "" false true >/dev/null 2>&1 || true
            fi
        done
        cli generatetoaddress 1 "$mine_addr" 999999999 >/dev/null 2>&1 || true
    done
}

# ── Surge scheduler ─────────────────────────────────────────────
surge_scheduler() {
    local start_time=$SECONDS
    local surge_num=0
    local next_surge=$SURGE_INTERVAL

    echo "baseline" > "$MODEFILE"
    log "Starting baseline mode"

    while (( SECONDS - start_time < DURATION_SECS )); do
        local elapsed=$((SECONDS - start_time))

        if (( elapsed >= next_surge )); then
            # Enter surge
            ((surge_num++))
            echo "surge" > "$MODEFILE"
            log "══════ SURGE #${surge_num} START (${elapsed}s elapsed) ══════"

            local surge_end=$((elapsed + SURGE_DURATION))
            while (( SECONDS - start_time < surge_end && SECONDS - start_time < DURATION_SECS )); do
                sleep 10
            done

            # Exit surge
            echo "baseline" > "$MODEFILE"
            local tx_count
            tx_count=$(cat /tmp/surge72_tx_count 2>/dev/null || echo 0)
            local mined_count
            mined_count=$(cat /tmp/surge72_mined_count 2>/dev/null || echo 0)
            log "══════ SURGE #${surge_num} END (tx=${tx_count} mined=${mined_count}) ══════"

            next_surge=$((elapsed + SURGE_INTERVAL))
        fi

        sleep 30
    done
}

# ── Metrics collector ────────────────────────────────────────────
metrics_loop() {
    echo "timestamp,elapsed_h,mode,blocks,dag_tips,mempool_size,mempool_bytes,utxo_count,tx_sent,tx_fail,mined,cpu_user,peers" > "$METRICS"

    local start_time=$SECONDS
    while true; do
        sleep 60
        local elapsed_h
        elapsed_h=$(awk "BEGIN{printf \"%.2f\", ($SECONDS - $start_time) / 3600.0}")
        local mode
        mode=$(get_mode)
        local blocks dag_tips mp_size mp_bytes
        blocks=$(cli getblockcount 2>/dev/null || echo -1)
        dag_tips=$(cli getblockchaininfo 2>/dev/null | grep -o '"dag_tips":[0-9]*' | grep -o '[0-9]*' || echo 0)
        mp_size=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | head -1 | grep -o '[0-9]*' || echo 0)
        mp_bytes=$(cli getmempoolinfo 2>/dev/null | grep '"bytes"' | head -1 | grep -o '[0-9]*' || echo 0)
        local tx_sent tx_fail mined_count
        tx_sent=$(cat /tmp/surge72_tx_count 2>/dev/null || echo 0)
        tx_fail=$(cat /tmp/surge72_tx_fail 2>/dev/null || echo 0)
        mined_count=$(cat /tmp/surge72_mined_count 2>/dev/null || echo 0)
        local cpu_user
        cpu_user=$(top -bn1 | grep "Cpu" | awk '{print $2}' 2>/dev/null || echo 0)
        local peers
        peers=$(cli getconnectioncount 2>/dev/null || echo 0)

        echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ'),${elapsed_h},${mode},${blocks},${dag_tips},${mp_size},${mp_bytes},0,${tx_sent},${tx_fail},${mined_count},${cpu_user},${peers}" >> "$METRICS"
    done
}

# ── Health watchdog ──────────────────────────────────────────────
watchdog() {
    while true; do
        sleep 120
        if ! cli getblockcount >/dev/null 2>&1; then
            log "WATCHDOG: daemon not responding — restarting..."
            /root/QuantBTC/src/bitcoind -daemon -conf=/root/.bitcoin/bitcoin.conf 2>/dev/null
            sleep 15
            if cli getblockcount >/dev/null 2>&1; then
                log "WATCHDOG: daemon recovered"
                apply_cpu_limit
            else
                log "WATCHDOG: daemon still down — manual intervention needed"
            fi
        fi

        # Disk space check
        local free_gb
        free_gb=$(df -BG /root/.bitcoin/ 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
        if (( free_gb < 5 )); then
            log "WATCHDOG: LOW DISK — ${free_gb}GB free"
        fi

        # Re-check cpulimit is still running
        local daemon_pid
        daemon_pid=$(pgrep -f '/root/QuantBTC/src/bitcoind' | head -1)
        if [[ -n "$daemon_pid" ]] && ! pgrep -f "cpulimit.*${daemon_pid}" >/dev/null 2>&1; then
            log "WATCHDOG: cpulimit not running, reapplying..."
            apply_cpu_limit
        fi
    done
}

# ── Main ─────────────────────────────────────────────────────────
main() {
    echo $$ > "$PIDFILE"
    mkdir -p "$LOGDIR"
    : > "$LOG"

    log "============================================================"
    log "  72-HOUR MIXED ENDURANCE TEST — ${NODE_LABEL}"
    log "  Node role:     ${NODE_ROLE}"
    log "  Duration:      ${DURATION_HOURS}h"
    log "  CPU limit:     ${CPU_LIMIT}%"
    log "  Baseline:      ${BASE_TX_PER_ROUND} tx/round, sleep ${BASE_TX_SLEEP}s, mine sleep ${BASE_MINE_SLEEP}s"
    log "  Surge:         ${SURGE_TX_PER_ROUND} tx/round, sleep ${SURGE_TX_SLEEP}s, mine sleep ${SURGE_MINE_SLEEP}s"
    log "  Surge sched:   ${SURGE_DURATION}s every ${SURGE_INTERVAL}s"
    log "  Wallets:       ${NUM_WALLETS}"
    log "  Log:           ${LOG}"
    log "  Metrics:       ${METRICS}"
    log "  Stop:          kill \$(cat ${PIDFILE})"
    log "============================================================"

    # Stop existing mining (but NOT our own surge72 session)
    log "Stopping existing mining screen sessions..."
    screen -ls 2>/dev/null | grep -oP '\d+\.\S+' | grep -v 'surge72' | while read s; do screen -S "$s" -X quit 2>/dev/null || true; done || true
    pkill -f "generatetoaddress" 2>/dev/null || true
    sleep 2

    # Apply CPU limit
    apply_cpu_limit

    # Record start state
    record_start_state

    # Setup wallets
    setup_wallets

    # Zero counters
    echo 0 > /tmp/surge72_mined_count
    echo 0 > /tmp/surge72_tx_count
    echo 0 > /tmp/surge72_tx_fail

    # Launch all loops
    mining_loop &
    local MINE_PID=$!
    tx_loop &
    local TX_PID=$!
    refund_loop &
    local REFUND_PID=$!
    metrics_loop &
    local METRICS_PID=$!
    watchdog &
    local WATCH_PID=$!

    log "All loops started: mine=$MINE_PID tx=$TX_PID refund=$REFUND_PID metrics=$METRICS_PID watchdog=$WATCH_PID"

    # Surge scheduler runs in foreground (blocks until duration complete)
    surge_scheduler

    # ── Final report ──────────────────────────────────────────────
    log "============================================================"
    log "  FINAL REPORT — ${NODE_LABEL} (${NODE_ROLE})"
    log "============================================================"
    local end_block
    end_block=$(cli getblockcount 2>/dev/null || echo 0)
    local start_block
    start_block=$(grep -o '"block_height": [0-9]*' "$STARTFILE" | grep -o '[0-9]*')
    local end_utxo
    end_utxo=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
    local end_supply
    end_supply=$(cli gettxoutsetinfo 2>/dev/null | grep '"total_amount"' | grep -oP '[\d.]+' || echo 0)
    local total_mined
    total_mined=$(cat /tmp/surge72_mined_count 2>/dev/null || echo 0)
    local total_tx
    total_tx=$(cat /tmp/surge72_tx_count 2>/dev/null || echo 0)
    local total_fail
    total_fail=$(cat /tmp/surge72_tx_fail 2>/dev/null || echo 0)

    log "  Blocks:     ${start_block} → ${end_block} (+$(( end_block - start_block )))"
    log "  UTXO count: ${end_utxo}"
    log "  Supply:     ${end_supply} QBTC"
    log "  TX sent:    ${total_tx} (failed: ${total_fail})"
    log "  Mined:      ${total_mined} blocks"
    log "  Role:       ${NODE_ROLE}"
    log "============================================================"

    # Cleanup
    echo "baseline" > "$MODEFILE"
    kill $MINE_PID $TX_PID $REFUND_PID $METRICS_PID $WATCH_PID 2>/dev/null
    log "All loops stopped. Test finished."
}

trap 'echo "baseline" > "$MODEFILE"; log "SIGNAL — stopping..."; kill 0; exit 0' INT TERM

main
