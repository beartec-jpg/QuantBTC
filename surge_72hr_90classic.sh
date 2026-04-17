#!/usr/bin/env bash
# surge_72hr_90classic.sh — 72-hour endurance test with 90% classical / 10% hybrid
#
# IDENTICAL to the previous 72hr full-hybrid test structure, but uses the new
# per-tx `pqc` RPC parameter to send 90% classical + 10% hybrid signatures.
#
# Runs on N1 (hybrid node) as sole tx sender.  N2/N3 run miner-only variant.
#
# Parameters match previous 72h test exactly:
#   Baseline:  5 tx/round,  3s sleep, 1.5s mine sleep
#   Surge:    50 tx/round,  0.5s sleep, 0.1s mine sleep
#   Surges: 20 min every 4 hours (18 surges over 72h)
#   Wallets: 12
#
# Usage:
#   N1:  NODE_ROLE=sender   ./surge_72hr_90classic.sh 72
#   N2:  NODE_ROLE=miner    ./surge_72hr_90classic.sh 72
#   N3:  NODE_ROLE=miner    ./surge_72hr_90classic.sh 72
#
# Stop:  kill $(cat /tmp/surge72_90c.pid)

set -o pipefail

# ── Per-node tunables (override via env) ─────────────────────────
DURATION_HOURS="${1:-72}"
DURATION_SECS=$((DURATION_HOURS * 3600))

NODE_LABEL="${NODE_LABEL:-$(hostname -s)}"
NODE_ROLE="${NODE_ROLE:-sender}"         # "sender" or "miner"

# RPC
RPCPORT="${RPCPORT:-28332}"
RPCUSER="${RPCUSER:-qbtcseed}"
RPCPASSWORD="${RPCPASSWORD:-changeme}"

CLI="/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet \
     -rpcport=${RPCPORT} -rpcuser=${RPCUSER} -rpcpassword=${RPCPASSWORD}"

# Match previous 72h test rates exactly
BASE_TX_PER_ROUND=5
BASE_TX_SLEEP=3
BASE_MINE_SLEEP="1.5"

SURGE_TX_PER_ROUND=50
SURGE_TX_SLEEP="0.5"
SURGE_MINE_SLEEP="0.1"

# Surge schedule — identical to previous test
SURGE_INTERVAL=14400    # 4 hours between surges
SURGE_DURATION=1200     # 20 minutes per surge

# PQC mix ratio
PQC_HYBRID_PCT=10       # 10% hybrid, 90% classical

# Wallet config — 12 wallets to match previous test
NUM_WALLETS=12
MINER_WALLET="miner"
FUND_AMOUNT="5.0"

# Files
LOGDIR="/root/surge72_90classic"
LOG="${LOGDIR}/surge_${NODE_LABEL}.log"
METRICS="${LOGDIR}/metrics_${NODE_LABEL}.csv"
MODEFILE="/tmp/surge72_90c_mode"
PIDFILE="/tmp/surge72_90c.pid"
STARTFILE="${LOGDIR}/start_state_${NODE_LABEL}.json"

CPU_LIMIT=50

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
    pkill -f "cpulimit.*-p ${pid}" 2>/dev/null || true
    sleep 1
    local limit=$((CPU_LIMIT * 2))
    cpulimit -p "$pid" -l "$limit" -b 2>/dev/null
    log "CPU limited: bitcoind pid=$pid capped at ${CPU_LIMIT}% total (cpulimit -l ${limit})"
}

# ── Wallet setup ─────────────────────────────────────────────────
declare -a WALLETS=()
declare -a ADDRS=()

setup_wallets() {
    log "Setting up $NUM_WALLETS wallets..."
    for i in $(seq 1 "$NUM_WALLETS"); do
        local WNAME="s90c_${NODE_LABEL}_w${i}"
        if ! cliw "$WNAME" getwalletinfo >/dev/null 2>&1; then
            cli createwallet "$WNAME" >/dev/null 2>&1 || \
            cli loadwallet "$WNAME" >/dev/null 2>&1 || true
        fi
        WALLETS+=("$WNAME")
        local ADDR
        ADDR=$(cliw "$WNAME" getnewaddress "" bech32)
        ADDRS+=("$ADDR")
    done
    log "Wallets ready: ${#WALLETS[@]}"

    # Fund each wallet from miner
    log "Funding wallets (${FUND_AMOUNT} QBTC each)..."
    cliw "$MINER_WALLET" getwalletinfo >/dev/null 2>&1 || \
        cli loadwallet "$MINER_WALLET" >/dev/null 2>&1 || true

    local funded=0
    for ADDR in "${ADDRS[@]}"; do
        # Fund with hybrid sig (default) since miner has hybrid UTXOs
        if cliw "$MINER_WALLET" sendtoaddress "$ADDR" "$FUND_AMOUNT" "" "" false true >/dev/null 2>&1; then
            ((funded++))
        fi
    done
    # Mine to confirm funding
    local mine_addr
    mine_addr=$(cliw "$MINER_WALLET" getnewaddress "" bech32 2>/dev/null)
    cli generatetoaddress 2 "$mine_addr" 999999999 >/dev/null 2>&1
    sleep 3
    log "Funded $funded/${#WALLETS[@]} wallets and confirmed"
}

# ── Record start state ───────────────────────────────────────────
record_start_state() {
    local blocks best_hash utxo_count supply mempool_size peers balance
    blocks=$(cli getblockcount 2>/dev/null || echo 0)
    best_hash=$(cli getbestblockhash 2>/dev/null || echo "unknown")
    utxo_count=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
    supply=$(cli gettxoutsetinfo 2>/dev/null | grep '"total_amount"' | grep -oP '[\d.]+' || echo 0)
    mempool_size=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | head -1 | grep -o '[0-9]*' || echo 0)
    peers=$(cli getconnectioncount 2>/dev/null || echo 0)
    balance=$(cliw "$MINER_WALLET" getbalance 2>/dev/null || echo 0)

    cat > "$STARTFILE" <<EOF
{
  "timestamp": "$(date -u '+%Y-%m-%dT%H:%M:%SZ')",
  "node": "$NODE_LABEL",
  "role": "$NODE_ROLE",
  "test_type": "90classic_10hybrid",
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
  "pqc_hybrid_pct": $PQC_HYBRID_PCT,
  "num_wallets": $NUM_WALLETS,
  "duration_hours": $DURATION_HOURS,
  "comparison_baseline": "TESTREPORT-2026-04-14-72HR-FINAL (100% hybrid, same rates)"
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
        local mode sleep_s
        mode=$(get_mode)
        if [[ "$mode" == "surge" ]]; then
            sleep_s=$SURGE_MINE_SLEEP
        else
            sleep_s=$BASE_MINE_SLEEP
        fi

        cli generatetoaddress 1 "$mine_addr" 999999999 >/dev/null 2>&1 && ((mined++))
        echo "$mined" > /tmp/surge72_90c_mined
        sleep "$sleep_s"
    done
}

# ── Transaction loop (90% classical / 10% hybrid) ───────────────
tx_loop() {
    local total_sent=0
    local total_fail=0
    local total_classical=0
    local total_hybrid=0

    while true; do
        local mode txr txs
        mode=$(get_mode)

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

            # 90% classical / 10% hybrid via pqc parameter
            local use_pqc="false"
            if (( RANDOM % 100 < PQC_HYBRID_PCT )); then
                use_pqc="true"
            fi

            if cliw "$src_wallet" -named sendtoaddress address="$dst_addr" amount="$amount" replaceable=true pqc="$use_pqc" 2>/dev/null | grep -q '^[0-9a-f]\{64\}$'; then
                ((sent_round++))
                if [[ "$use_pqc" == "true" ]]; then
                    ((total_hybrid++))
                else
                    ((total_classical++))
                fi
            else
                ((fail_round++))
            fi
        done

        total_sent=$((total_sent + sent_round))
        total_fail=$((total_fail + fail_round))
        echo "$total_sent" > /tmp/surge72_90c_tx
        echo "$total_fail" > /tmp/surge72_90c_fail
        echo "$total_classical" > /tmp/surge72_90c_classical
        echo "$total_hybrid" > /tmp/surge72_90c_hybrid

        sleep "$txs"
    done
}

# ── UTXO refund/consolidation loop ──────────────────────────────
refund_loop() {
    while true; do
        sleep 600   # every 10 minutes
        local mine_addr
        mine_addr=$(cliw "$MINER_WALLET" getnewaddress "" bech32 2>/dev/null)
        for i in $(seq 0 $(( ${#WALLETS[@]} - 1 ))); do
            local bal
            bal=$(cliw "${WALLETS[$i]}" getbalance 2>/dev/null || echo "0")
            if awk "BEGIN{exit !($bal < 1.0)}" 2>/dev/null; then
                # Fund with default hybrid sig (miner wallet has hybrid UTXOs)
                cliw "$MINER_WALLET" sendtoaddress "${ADDRS[$i]}" "2.0" "" "" false true >/dev/null 2>&1 || true
            fi
        done
        cli generatetoaddress 1 "$mine_addr" 999999999 >/dev/null 2>&1 || true
        local cls hyb
        cls=$(cat /tmp/surge72_90c_classical 2>/dev/null || echo 0)
        hyb=$(cat /tmp/surge72_90c_hybrid 2>/dev/null || echo 0)
        log "REFUND sweep | classical=$cls hybrid=$hyb ratio=$(awk "BEGIN{t=$cls+$hyb; if(t>0) printf \"%.1f%%\",($cls/t)*100; else print \"N/A\"}")"
    done
}

# ── Surge scheduler ─────────────────────────────────────────────
surge_scheduler() {
    local start_time=$SECONDS
    local surge_num=0
    local next_surge=$SURGE_INTERVAL

    echo "baseline" > "$MODEFILE"
    log "Starting baseline mode (90% classical / 10% hybrid)"

    while (( SECONDS - start_time < DURATION_SECS )); do
        local elapsed=$((SECONDS - start_time))

        if (( elapsed >= next_surge )); then
            ((surge_num++))
            echo "surge" > "$MODEFILE"
            log "══════ SURGE #${surge_num} START (${elapsed}s / $((elapsed / 3600))h elapsed) ══════"

            local surge_end=$((elapsed + SURGE_DURATION))
            while (( SECONDS - start_time < surge_end && SECONDS - start_time < DURATION_SECS )); do
                sleep 10
            done

            echo "baseline" > "$MODEFILE"
            local tx_count cls hyb fail mined_count
            tx_count=$(cat /tmp/surge72_90c_tx 2>/dev/null || echo 0)
            cls=$(cat /tmp/surge72_90c_classical 2>/dev/null || echo 0)
            hyb=$(cat /tmp/surge72_90c_hybrid 2>/dev/null || echo 0)
            fail=$(cat /tmp/surge72_90c_fail 2>/dev/null || echo 0)
            mined_count=$(cat /tmp/surge72_90c_mined 2>/dev/null || echo 0)
            log "══════ SURGE #${surge_num} END (tx=${tx_count} cls=${cls} hyb=${hyb} fail=${fail} mined=${mined_count}) ══════"

            next_surge=$((elapsed + SURGE_INTERVAL))
        fi

        sleep 30
    done
}

# ── Metrics collector ────────────────────────────────────────────
metrics_loop() {
    echo "timestamp,elapsed_h,mode,blocks,dag_tips,mempool_size,mempool_bytes,tx_sent,tx_fail,tx_classical,tx_hybrid,mined,cpu_user,peers" > "$METRICS"

    local start_time=$SECONDS
    while true; do
        sleep 60
        local elapsed_h
        elapsed_h=$(awk "BEGIN{printf \"%.2f\", ($SECONDS - $start_time) / 3600.0}")
        local mode blocks dag_tips mp_size mp_bytes tx_sent tx_fail tx_cls tx_hyb mined_count cpu_user peers
        mode=$(get_mode)
        blocks=$(cli getblockcount 2>/dev/null || echo -1)
        dag_tips=$(cli getblockchaininfo 2>/dev/null | grep -o '"dag_tips":[0-9]*' | grep -o '[0-9]*' || echo 0)
        mp_size=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | head -1 | grep -o '[0-9]*' || echo 0)
        mp_bytes=$(cli getmempoolinfo 2>/dev/null | grep '"bytes"' | head -1 | grep -o '[0-9]*' || echo 0)
        tx_sent=$(cat /tmp/surge72_90c_tx 2>/dev/null || echo 0)
        tx_fail=$(cat /tmp/surge72_90c_fail 2>/dev/null || echo 0)
        tx_cls=$(cat /tmp/surge72_90c_classical 2>/dev/null || echo 0)
        tx_hyb=$(cat /tmp/surge72_90c_hybrid 2>/dev/null || echo 0)
        mined_count=$(cat /tmp/surge72_90c_mined 2>/dev/null || echo 0)
        cpu_user=$(top -bn1 | grep "Cpu" | awk '{print $2}' 2>/dev/null || echo 0)
        peers=$(cli getconnectioncount 2>/dev/null || echo 0)

        echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ'),${elapsed_h},${mode},${blocks},${dag_tips},${mp_size},${mp_bytes},${tx_sent},${tx_fail},${tx_cls},${tx_hyb},${mined_count},${cpu_user},${peers}" >> "$METRICS"
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

        local free_gb
        free_gb=$(df -BG /root/.bitcoin/ 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
        if (( free_gb < 5 )); then
            log "WATCHDOG: LOW DISK — ${free_gb}GB free"
        fi

        local daemon_pid
        daemon_pid=$(pgrep -f '/root/QuantBTC/src/bitcoind' | head -1)
        if [[ -n "$daemon_pid" ]] && ! pgrep -f "cpulimit.*${daemon_pid}" >/dev/null 2>&1; then
            log "WATCHDOG: cpulimit not running, reapplying..."
            apply_cpu_limit
        fi
    done
}

# ── Miner-only main (for N2/N3) ─────────────────────────────────
main_miner() {
    echo $$ > "$PIDFILE"
    mkdir -p "$LOGDIR"
    : > "$LOG"

    log "============================================================"
    log "  72-HOUR 90/10 TEST — ${NODE_LABEL} (MINER ONLY)"
    log "  Duration:      ${DURATION_HOURS}h"
    log "  CPU limit:     ${CPU_LIMIT}%"
    log "  Mine sleep:    baseline=${BASE_MINE_SLEEP}s surge=${SURGE_MINE_SLEEP}s"
    log "============================================================"

    cliw "$MINER_WALLET" getwalletinfo >/dev/null 2>&1 || \
        cli loadwallet "$MINER_WALLET" >/dev/null 2>&1 || true

    screen -ls 2>/dev/null | grep -oP '\d+\.\S+' | grep -v 'surge72' | while read s; do screen -S "$s" -X quit 2>/dev/null || true; done || true
    pkill -f "generatetoaddress" 2>/dev/null || true
    sleep 2

    apply_cpu_limit
    record_start_state

    echo 0 > /tmp/surge72_90c_mined

    mining_loop &
    local MINE_PID=$!
    watchdog &
    local WATCH_PID=$!

    log "Miner loops started: mine=$MINE_PID watchdog=$WATCH_PID"

    # Just sleep for the duration
    local start_time=$SECONDS
    while (( SECONDS - start_time < DURATION_SECS )); do
        sleep 300
        local mined_count
        mined_count=$(cat /tmp/surge72_90c_mined 2>/dev/null || echo 0)
        local blocks
        blocks=$(cli getblockcount 2>/dev/null || echo 0)
        local peers
        peers=$(cli getconnectioncount 2>/dev/null || echo 0)
        log "MINER status: mined=$mined_count height=$blocks peers=$peers"
    done

    log "Duration reached. Stopping."
    kill $MINE_PID $WATCH_PID 2>/dev/null
    log "Miner test complete."
}

# ── Sender main (for N1) ────────────────────────────────────────
main_sender() {
    echo $$ > "$PIDFILE"
    mkdir -p "$LOGDIR"
    : > "$LOG"

    log "============================================================"
    log "  72-HOUR 90/10 ENDURANCE TEST — ${NODE_LABEL}"
    log "  Test type:     90% classical / 10% hybrid (per-tx pqc param)"
    log "  Duration:      ${DURATION_HOURS}h"
    log "  CPU limit:     ${CPU_LIMIT}%"
    log "  Baseline:      ${BASE_TX_PER_ROUND} tx/round, sleep ${BASE_TX_SLEEP}s, mine sleep ${BASE_MINE_SLEEP}s"
    log "  Surge:         ${SURGE_TX_PER_ROUND} tx/round, sleep ${SURGE_TX_SLEEP}s, mine sleep ${SURGE_MINE_SLEEP}s"
    log "  Surge sched:   ${SURGE_DURATION}s every ${SURGE_INTERVAL}s"
    log "  PQC hybrid:    ${PQC_HYBRID_PCT}% of transactions"
    log "  Wallets:       ${NUM_WALLETS}"
    log "  Comparison:    TESTREPORT-2026-04-14-72HR-FINAL (100% hybrid)"
    log "  Log:           ${LOG}"
    log "  Metrics:       ${METRICS}"
    log "  Stop:          kill \$(cat ${PIDFILE})"
    log "============================================================"

    screen -ls 2>/dev/null | grep -oP '\d+\.\S+' | grep -v 'surge72' | while read s; do screen -S "$s" -X quit 2>/dev/null || true; done || true
    pkill -f "generatetoaddress" 2>/dev/null || true
    sleep 2

    apply_cpu_limit
    record_start_state
    setup_wallets

    echo 0 > /tmp/surge72_90c_mined
    echo 0 > /tmp/surge72_90c_tx
    echo 0 > /tmp/surge72_90c_fail
    echo 0 > /tmp/surge72_90c_classical
    echo 0 > /tmp/surge72_90c_hybrid

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

    surge_scheduler

    # ── Final report ──────────────────────────────────────────────
    log "============================================================"
    log "  FINAL REPORT — ${NODE_LABEL} (90% classical / 10% hybrid)"
    log "============================================================"
    local end_block start_block end_utxo end_supply
    end_block=$(cli getblockcount 2>/dev/null || echo 0)
    start_block=$(grep -o '"block_height": [0-9]*' "$STARTFILE" | grep -o '[0-9]*')
    end_utxo=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
    end_supply=$(cli gettxoutsetinfo 2>/dev/null | grep '"total_amount"' | grep -oP '[\d.]+' || echo 0)
    local total_mined total_tx total_fail total_cls total_hyb
    total_mined=$(cat /tmp/surge72_90c_mined 2>/dev/null || echo 0)
    total_tx=$(cat /tmp/surge72_90c_tx 2>/dev/null || echo 0)
    total_fail=$(cat /tmp/surge72_90c_fail 2>/dev/null || echo 0)
    total_cls=$(cat /tmp/surge72_90c_classical 2>/dev/null || echo 0)
    total_hyb=$(cat /tmp/surge72_90c_hybrid 2>/dev/null || echo 0)
    local actual_pct
    actual_pct=$(awk "BEGIN{t=$total_cls+$total_hyb; if(t>0) printf \"%.1f\",($total_cls/t)*100; else print \"N/A\"}")

    log "  Blocks:     ${start_block} → ${end_block} (+$(( end_block - start_block )))"
    log "  UTXO count: ${end_utxo}"
    log "  Supply:     ${end_supply} QBTC"
    log "  TX sent:    ${total_tx} (failed: ${total_fail})"
    log "    Classical: ${total_cls} (${actual_pct}%)"
    log "    Hybrid:    ${total_hyb}"
    log "  Mined:      ${total_mined} blocks"
    log "============================================================"
    log "  Comparison vs 100% hybrid (TESTREPORT-2026-04-14):"
    log "    Previous: ~340K tx, ~1.61 TPS, 25,736 blocks"
    log "    This run: ${total_tx} tx, $(awk "BEGIN{printf \"%.2f\", $total_tx / ($DURATION_HOURS * 3600)}") TPS, $(( end_block - start_block )) blocks"
    log "============================================================"

    echo "baseline" > "$MODEFILE"
    kill $MINE_PID $TX_PID $REFUND_PID $METRICS_PID $WATCH_PID 2>/dev/null
    log "All loops stopped. Test finished."
}

# ── Entry point ──────────────────────────────────────────────────
if [[ "$NODE_ROLE" == "miner" ]]; then
    main_miner
else
    main_sender
fi
