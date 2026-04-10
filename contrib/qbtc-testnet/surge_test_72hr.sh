#!/usr/bin/env bash
# surge_test_72hr.sh — 72-hour sustained + surge stress test (per-node)
#
# Runs on each node independently. Alternates between:
#   BASELINE: 50% CPU, 5 tx/3s, mining with 1.5s sleep
#   SURGE:    90% CPU, 50 tx/0.5s, mining with 0.1s sleep
#
# Surge schedule: 20-min surge every 4 hours (18 surges over 72h)
#
# Usage:
#   RPCUSER=x RPCPASSWORD=y ./surge_test_72hr.sh [duration_hours]
#
# Metrics written to /tmp/surge_metrics.csv every 60s
# Full log at /tmp/surge_test.log
# Stop: kill $(cat /tmp/surge_test.pid)

set -uo pipefail

# ── Configuration ────────────────────────────────────────────────
DURATION_HOURS="${1:-72}"
DURATION_SECS=$((DURATION_HOURS * 3600))
NUM_WALLETS=12
RPCPORT="${RPCPORT:-28332}"
RPCUSER="${RPCUSER:?need RPCUSER}"
RPCPASSWORD="${RPCPASSWORD:?need RPCPASSWORD}"
MINER_WALLET="miner"

# Baseline settings
BASE_MINE_SLEEP=1.5
BASE_TX_PER_ROUND=5
BASE_TX_SLEEP=3

# Surge settings
SURGE_MINE_SLEEP=0.1
SURGE_TX_PER_ROUND=50
SURGE_TX_SLEEP=0.5

# Surge timing
SURGE_INTERVAL=14400    # 4 hours between surges
SURGE_DURATION=1200     # 20 minutes per surge

# File paths
LOG="/tmp/surge_test.log"
METRICS="/tmp/surge_metrics.csv"
MODEFILE="/tmp/surge_mode"       # "baseline" or "surge"
PIDFILE="/tmp/surge_test.pid"
HOSTNAME_TAG=$(hostname -s 2>/dev/null || echo "node")

# ── Helpers ──────────────────────────────────────────────────────
cli() {
    bitcoin-cli -rpcport="$RPCPORT" -rpcuser="$RPCUSER" -rpcpassword="$RPCPASSWORD" "$@" 2>/dev/null
}

cliw() {
    local w="$1"; shift
    cli -rpcwallet="$w" "$@" 2>/dev/null
}

log() {
    printf '[%s] [%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$HOSTNAME_TAG" "$*" | tee -a "$LOG"
}

get_mode() {
    cat "$MODEFILE" 2>/dev/null || echo "baseline"
}

# ── Setup wallets ────────────────────────────────────────────────
declare -a WALLETS=()
declare -a ADDRS=()

setup_wallets() {
    log "Setting up $NUM_WALLETS wallets..."
    for i in $(seq 1 "$NUM_WALLETS"); do
        local WNAME="surge_w${i}"
        if ! cliw "$WNAME" getwalletinfo >/dev/null 2>&1; then
            cli createwallet "$WNAME" >/dev/null 2>&1 || cli loadwallet "$WNAME" >/dev/null 2>&1 || true
        fi
        WALLETS+=("$WNAME")
        local ADDR
        ADDR=$(cliw "$WNAME" getnewaddress "" bech32)
        ADDRS+=("$ADDR")
    done
    log "Wallets: ${#WALLETS[@]} ready"

    # Fund each wallet with 5 qBTC
    local MINE_ADDR
    MINE_ADDR=$(cliw "$MINER_WALLET" getnewaddress "" bech32)
    for ADDR in "${ADDRS[@]}"; do
        cliw "$MINER_WALLET" sendtoaddress "$ADDR" "5.0" "" "" false true >/dev/null 2>&1 || true
    done
    cli generatetoaddress 1 "$MINE_ADDR" >/dev/null 2>&1
    log "Wallets funded (5 qBTC each) and confirmed"
}

# ── Metrics collector (runs every 60s) ───────────────────────────
metrics_loop() {
    # Write CSV header
    echo "timestamp,elapsed_h,mode,blocks,dag_tips,mempool_size,mempool_bytes,utxo_count,total_supply,disk_blocks_mb,chainstate_mb,cpu_idle,mined_session,tx_session" > "$METRICS"

    local start_time=$SECONDS
    while true; do
        local elapsed=$(( (SECONDS - start_time) ))
        local elapsed_h
        elapsed_h=$(echo "scale=2; $elapsed / 3600" | bc)
        local mode
        mode=$(get_mode)

        # Gather metrics
        local blocks dag_tips mempool_size mempool_bytes utxo_count total_supply disk_blocks chainstate cpu_idle
        blocks=$(cli getblockcount 2>/dev/null || echo 0)
        dag_tips=$(cli getblockchaininfo 2>/dev/null | grep -o '"dag_tips": [0-9]*' | grep -o '[0-9]*' || echo 0)
        mempool_size=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | grep -o '[0-9]*' || echo 0)
        mempool_bytes=$(cli getmempoolinfo 2>/dev/null | grep '"bytes"' | grep -o '[0-9]*' || echo 0)
        utxo_count=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
        total_supply=$(cli gettxoutsetinfo 2>/dev/null | grep '"total_amount"' | grep -oP '[\d.]+' || echo 0)
        disk_blocks=$(du -sm /root/.bitcoin/qbtctestnet/blocks/ 2>/dev/null | cut -f1 || echo 0)
        chainstate=$(du -sm /root/.bitcoin/qbtctestnet/chainstate/ 2>/dev/null | cut -f1 || echo 0)
        cpu_idle=$(top -bn1 | sed -n '3p' | grep -oP '[\d.]+(?= id)' || echo 0)

        # Read cumulative counters from temp files
        local mined_session tx_session
        mined_session=$(cat /tmp/surge_mined_count 2>/dev/null || echo 0)
        tx_session=$(cat /tmp/surge_tx_count 2>/dev/null || echo 0)

        echo "${elapsed_h},${mode},${blocks},${dag_tips},${mempool_size},${mempool_bytes},${utxo_count},${total_supply},${disk_blocks},${chainstate},${cpu_idle},${mined_session},${tx_session}" >> "$METRICS"

        # Log summary every 5 min
        if (( $(echo "$elapsed % 300 < 60" | bc) )); then
            log "METRIC: h=${elapsed_h} mode=${mode} blk=${blocks} tips=${dag_tips} pool=${mempool_size} utxo=${utxo_count} supply=${total_supply} disk=${disk_blocks}MB mined=${mined_session} tx=${tx_session} idle=${cpu_idle}%"
        fi

        sleep 60
    done
}

# ── Mining loop (reads mode file for sleep duration) ─────────────
mining_loop() {
    local addr
    addr=$(cliw "$MINER_WALLET" getnewaddress "" bech32)
    local count=0
    echo 0 > /tmp/surge_mined_count

    while true; do
        local mode
        mode=$(get_mode)
        local sleep_time="$BASE_MINE_SLEEP"
        [[ "$mode" == "surge" ]] && sleep_time="$SURGE_MINE_SLEEP"

        RESULT=$(cli generatetoaddress 1 "$addr" 2>&1)
        if echo "$RESULT" | grep -q '"'; then
            count=$((count + 1))
            echo "$count" > /tmp/surge_mined_count
            if (( count % 20 == 0 )); then
                local height
                height=$(cli getblockcount 2>/dev/null || echo "?")
                log "MINE: block #${height} (${count} this session, mode=${mode})"
            fi
        else
            sleep 2
        fi
        sleep "$sleep_time"
    done
}

# ── TX spray loop (reads mode file for tx rate) ─────────────────
tx_loop() {
    local round=0
    local total_tx=0
    echo 0 > /tmp/surge_tx_count
    sleep 15  # let mining get ahead

    while true; do
        local mode
        mode=$(get_mode)
        local tx_count="$BASE_TX_PER_ROUND"
        local tx_sleep="$BASE_TX_SLEEP"
        [[ "$mode" == "surge" ]] && tx_count="$SURGE_TX_PER_ROUND" && tx_sleep="$SURGE_TX_SLEEP"

        round=$((round + 1))
        local sent=0
        for _t in $(seq 1 "$tx_count"); do
            SRC_IDX=$(( RANDOM % NUM_WALLETS ))
            DST_IDX=$(( (SRC_IDX + 1 + RANDOM % (NUM_WALLETS - 1)) % NUM_WALLETS ))
            SRC_W="${WALLETS[$SRC_IDX]}"
            DST_ADDR="${ADDRS[$DST_IDX]}"
            AMT=$(printf '0.%03d' $(( RANDOM % 100 + 1 )) )

            TXID=$(cliw "$SRC_W" sendtoaddress "$DST_ADDR" "$AMT" "" "" false true 2>&1)
            if [[ "$TXID" =~ ^[0-9a-f]{64}$ ]]; then
                sent=$((sent + 1))
                total_tx=$((total_tx + 1))
                echo "$total_tx" > /tmp/surge_tx_count
            fi
        done

        if (( round % 10 == 0 )); then
            local pooled
            pooled=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | grep -o '[0-9]*' || echo "?")
            log "TX: round=${round} sent=${sent}/${tx_count} total=${total_tx} mempool=${pooled} mode=${mode}"
        fi
        sleep "$tx_sleep"
    done
}

# ── Refund loop: keep wallets solvent ────────────────────────────
refund_loop() {
    sleep 600
    local mine_addr
    mine_addr=$(cliw "$MINER_WALLET" getnewaddress "" bech32)
    while true; do
        # Top up wallets that are low
        for i in "${!WALLETS[@]}"; do
            local w="${WALLETS[$i]}"
            local bal
            bal=$(cliw "$w" getbalance 2>/dev/null || echo "0")
            # Refill if below 1 qBTC
            if (( $(echo "$bal < 1" | bc -l 2>/dev/null || echo 0) )); then
                cliw "$MINER_WALLET" sendtoaddress "${ADDRS[$i]}" "3.0" "" "" false true >/dev/null 2>&1 && \
                    log "REFILL: ${w} +3.0 qBTC (was ${bal})" || true
            fi
            # Sweep if over 20 qBTC
            if (( $(echo "$bal > 20" | bc -l 2>/dev/null || echo 0) )); then
                local sweep
                sweep=$(echo "$bal - 5" | bc -l 2>/dev/null | head -c 10)
                cliw "$w" sendtoaddress "$mine_addr" "$sweep" "" "" false true >/dev/null 2>&1 && \
                    log "SWEEP: ${w} → miner ${sweep} qBTC" || true
            fi
        done
        sleep 600
    done
}

# ── Surge scheduler ─────────────────────────────────────────────
surge_scheduler() {
    local start_time=$SECONDS
    local surge_num=0
    echo "baseline" > "$MODEFILE"
    log "SCHEDULE: Baseline started. Surges every ${SURGE_INTERVAL}s for ${SURGE_DURATION}s"

    while true; do
        local elapsed=$(( SECONDS - start_time ))
        if (( elapsed >= DURATION_SECS )); then
            log "SCHEDULE: 72-hour test COMPLETE (${elapsed}s elapsed)"
            echo "baseline" > "$MODEFILE"
            break
        fi

        # Wait until next surge
        sleep "$SURGE_INTERVAL"
        elapsed=$(( SECONDS - start_time ))
        if (( elapsed >= DURATION_SECS )); then break; fi

        # Enter surge
        surge_num=$((surge_num + 1))
        local hours_in
        hours_in=$(echo "scale=1; $elapsed / 3600" | bc)
        echo "surge" > "$MODEFILE"
        log ">>>>>> SURGE #${surge_num} START (h=${hours_in}) — 90% CPU, 50tx/round for ${SURGE_DURATION}s <<<<<<"

        # Surge snapshot before
        local blk_before
        blk_before=$(cli getblockcount 2>/dev/null || echo 0)
        local tx_before
        tx_before=$(cat /tmp/surge_tx_count 2>/dev/null || echo 0)
        local mined_before
        mined_before=$(cat /tmp/surge_mined_count 2>/dev/null || echo 0)

        sleep "$SURGE_DURATION"

        # Surge snapshot after
        local blk_after
        blk_after=$(cli getblockcount 2>/dev/null || echo 0)
        local tx_after
        tx_after=$(cat /tmp/surge_tx_count 2>/dev/null || echo 0)
        local mined_after
        mined_after=$(cat /tmp/surge_mined_count 2>/dev/null || echo 0)
        local pool_after
        pool_after=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | grep -o '[0-9]*' || echo "?")
        local tips_after
        tips_after=$(cli getblockchaininfo 2>/dev/null | grep -o '"dag_tips": [0-9]*' | grep -o '[0-9]*' || echo "?")

        echo "baseline" > "$MODEFILE"
        local delta_blk=$(( blk_after - blk_before ))
        local delta_tx=$(( tx_after - tx_before ))
        local delta_mined=$(( mined_after - mined_before ))
        log "<<<<<< SURGE #${surge_num} END — blocks+=${delta_blk} mined+=${delta_mined} tx+=${delta_tx} pool=${pool_after} tips=${tips_after} >>>>>>"
    done
}

# ── Health watchdog ──────────────────────────────────────────────
watchdog() {
    while true; do
        sleep 120
        # Check daemon is responsive
        if ! cli getblockcount >/dev/null 2>&1; then
            log "WATCHDOG: daemon not responding! Attempting restart..."
            bitcoind -conf=/root/.bitcoin/bitcoin.conf -daemon 2>/dev/null
            sleep 10
            if cli getblockcount >/dev/null 2>&1; then
                log "WATCHDOG: daemon recovered"
            else
                log "WATCHDOG: daemon still down — manual intervention needed"
            fi
        fi

        # Check disk space (warn if < 5GB free)
        local free_gb
        free_gb=$(df -BG /root/.bitcoin/ 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
        if (( free_gb < 5 )); then
            log "WATCHDOG: LOW DISK — ${free_gb}GB free"
        fi
    done
}

# ── Main ─────────────────────────────────────────────────────────
main() {
    echo $$ > "$PIDFILE"
    : > "$LOG"

    log "=============================================="
    log "  72-HOUR SURGE TEST — ${HOSTNAME_TAG}"
    log "  Duration: ${DURATION_HOURS}h"
    log "  Baseline: mine_sleep=${BASE_MINE_SLEEP}s tx=${BASE_TX_PER_ROUND}/round@${BASE_TX_SLEEP}s"
    log "  Surge:    mine_sleep=${SURGE_MINE_SLEEP}s tx=${SURGE_TX_PER_ROUND}/round@${SURGE_TX_SLEEP}s"
    log "  Surge schedule: ${SURGE_DURATION}s every ${SURGE_INTERVAL}s (~18 surges)"
    log "  Wallets: ${NUM_WALLETS}"
    log "  Metrics: ${METRICS} (every 60s)"
    log "  Stop: kill \$(cat ${PIDFILE})"
    log "=============================================="

    setup_wallets

    # Record starting state
    local start_block
    start_block=$(cli getblockcount 2>/dev/null || echo 0)
    local start_utxo
    start_utxo=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
    log "START STATE: block=${start_block} utxo=${start_utxo}"

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

    # Surge scheduler runs in foreground (blocks until done)
    surge_scheduler

    # Test complete — collect final report
    log "=============================================="
    log "  FINAL REPORT"
    log "=============================================="
    local end_block
    end_block=$(cli getblockcount 2>/dev/null || echo 0)
    local end_utxo
    end_utxo=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
    local end_supply
    end_supply=$(cli gettxoutsetinfo 2>/dev/null | grep '"total_amount"' | grep -oP '[\d.]+' || echo 0)
    local end_disk
    end_disk=$(du -sh /root/.bitcoin/ 2>/dev/null | cut -f1)
    local total_mined
    total_mined=$(cat /tmp/surge_mined_count 2>/dev/null || echo 0)
    local total_tx
    total_tx=$(cat /tmp/surge_tx_count 2>/dev/null || echo 0)

    log "  Blocks:     ${start_block} → ${end_block} (+$(( end_block - start_block )))"
    log "  UTXO set:   ${start_utxo} → ${end_utxo} (+$(( end_utxo - start_utxo )))"
    log "  Supply:     ${end_supply} qBTC"
    log "  Mined:      ${total_mined} blocks this session"
    log "  TX sent:    ${total_tx}"
    log "  Disk:       ${end_disk}"
    log "=============================================="

    # Cleanup — kill child loops, revert to baseline
    echo "baseline" > "$MODEFILE"
    kill $MINE_PID $TX_PID $REFUND_PID $METRICS_PID $WATCH_PID 2>/dev/null
    log "All loops stopped. Test finished."
}

trap 'echo "baseline" > "$MODEFILE"; log "SIGNAL received — stopping..."; kill 0; exit 0' INT TERM

main
