#!/usr/bin/env bash
# surge_72hr_falcon.sh — 72-hour endurance test with 100% Falcon-padded-512 PQC signing
#
# Runs INDEPENDENTLY on each node.  Deploy with per-node env vars:
#
#   N1 (falcon-hybrid): TX_PER_ROUND=5  TX_SLEEP=2  SURGE_TX=20  SURGE_SLEEP=1
#   N2 (falcon-hybrid): TX_PER_ROUND=5  TX_SLEEP=2  SURGE_TX=20  SURGE_SLEEP=1
#   N3 (falcon-hybrid): TX_PER_ROUND=5  TX_SLEEP=2  SURGE_TX=20  SURGE_SLEEP=1
#
# Combined baseline: N1≈2.5 + N2≈2.5 + N3≈2.5 = ~7.5 tx/s
# Combined surge:    N1≈20  + N2≈20  + N3≈20  = ~60 tx/s
#
# Falcon-512 witness is ~3.7× smaller than Dilithium, so higher baseline rates
# are sustainable on the same 4GB VPS hardware.
#
# CPU capped at 40% via cpulimit on bitcoind.
#
# Requires: daemon started with -pqcmode=hybrid -pqcsig=falcon
# Requires: commit >= cabf245 (IsPQCWitness() Falcon fix)
#
# Usage:
#   chmod +x surge_72hr_falcon.sh
#   nohup ./surge_72hr_falcon.sh [duration_hours] &
#
# Stop:  kill $(cat /tmp/surge72_falcon.pid)

set -o pipefail

# ── Per-node tunables (override via env) ─────────────────────────
DURATION_HOURS="${1:-72}"
DURATION_SECS=$((DURATION_HOURS * 3600))

NODE_LABEL="${NODE_LABEL:-$(hostname -s)}"
NODE_ROLE="${NODE_ROLE:-falcon-hybrid}"

# RPC (read from bitcoin.conf or env)
RPCPORT="${RPCPORT:-28332}"
RPCUSER="${RPCUSER:-qbtcseed}"
RPCPASSWORD="${RPCPASSWORD:-changeme}"

CLI="/root/QuantBTC/src/bitcoin-cli -chain=qbtctestnet \
     -rpcport=${RPCPORT} -rpcuser=${RPCUSER} -rpcpassword=${RPCPASSWORD}"

# Baseline rates — higher than Dilithium test due to smaller Falcon witness
BASE_TX_PER_ROUND="${TX_PER_ROUND:-5}"
BASE_TX_SLEEP="${TX_SLEEP:-2}"
BASE_MINE_SLEEP="${MINE_SLEEP:-5}"

# Surge rates
SURGE_TX_PER_ROUND="${SURGE_TX:-20}"
SURGE_TX_SLEEP="${SURGE_SLEEP:-1}"
SURGE_MINE_SLEEP="1"

# Surge schedule — same as prior 72hr tests for comparability
SURGE_INTERVAL=14400    # 4 hours between surges
SURGE_DURATION=1200     # 20 minutes per surge

# Wallet config
NUM_WALLETS=10
MINER_WALLET="miner"
FUND_AMOUNT="5.0"

# Files
LOGDIR="/root/surge72_falcon"
LOG="${LOGDIR}/surge_${NODE_LABEL}.log"
METRICS="${LOGDIR}/metrics_${NODE_LABEL}.csv"
WITNESS_STATS="${LOGDIR}/witness_stats_${NODE_LABEL}.csv"
MODEFILE="/tmp/surge72_falcon_mode"
PIDFILE="/tmp/surge72_falcon.pid"
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

# ── Verify Falcon is enabled ──────────────────────────────────────
check_falcon_mode() {
    local pqcinfo
    pqcinfo=$(cli getpqcinfo 2>/dev/null)
    if [[ -z "$pqcinfo" ]]; then
        log "WARN: getpqcinfo not available — proceeding; verify daemon has -pqcsig=falcon"
        return
    fi

    local active_sig
    active_sig=$(echo "$pqcinfo" | grep -oP '"active_pqcsig"\s*:\s*"\K[^"]+' || \
                 echo "$pqcinfo" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('active_pqcsig','unknown'))" 2>/dev/null || \
                 echo "unknown")
    log "PQC mode: $active_sig"

    if [[ "$active_sig" != *"falcon"* ]]; then
        log "WARN: Expected falcon signature mode, got: $active_sig — check daemon -pqcsig=falcon flag"
    else
        log "Falcon signature mode confirmed: $active_sig"
    fi
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
    log "Setting up $NUM_WALLETS wallets in Falcon signature mode..."
    for i in $(seq 1 "$NUM_WALLETS"); do
        local WNAME="falcon72_${NODE_LABEL}_w${i}"
        if ! cliw "$WNAME" getwalletinfo >/dev/null 2>&1; then
            cli createwallet "$WNAME" >/dev/null 2>&1 || \
            cli loadwallet  "$WNAME" >/dev/null 2>&1 || true
        fi
        WALLETS+=("$WNAME")
        # bech32 addresses map to the active PQC key type (Falcon-512 when -pqcsig=falcon)
        local ADDR
        ADDR=$(cliw "$WNAME" getnewaddress "" bech32)
        ADDRS+=("$ADDR")
    done
    log "Wallets ready: ${#WALLETS[@]} (Falcon-padded-512 signatures)"

    # Fund each wallet from miner
    log "Funding wallets (${FUND_AMOUNT} QBTC each)..."
    local MINE_ADDR
    MINE_ADDR=$(cliw "$MINER_WALLET" getnewaddress "" bech32)
    local funded=0
    for ADDR in "${ADDRS[@]}"; do
        if cliw "$MINER_WALLET" sendtoaddress "$ADDR" "$FUND_AMOUNT" "" "" false true >/dev/null 2>&1; then
            ((funded++))
        fi
    done
    cli generatetoaddress 1 "$MINE_ADDR" 999999999 >/dev/null 2>&1
    sleep 2
    log "Funded $funded/${#WALLETS[@]} wallets and confirmed"
}

# ── Record start state ───────────────────────────────────────────
record_start_state() {
    local blocks best_hash utxo_count supply mempool_size peers balance pqcinfo
    blocks=$(cli getblockcount 2>/dev/null || echo 0)
    best_hash=$(cli getbestblockhash 2>/dev/null || echo "unknown")
    utxo_count=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
    supply=$(cli gettxoutsetinfo 2>/dev/null | grep '"total_amount"' | grep -oP '[\d.]+' || echo 0)
    mempool_size=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | head -1 | grep -o '[0-9]*' || echo 0)
    peers=$(cli getconnectioncount 2>/dev/null || echo 0)
    balance=$(cliw "$MINER_WALLET" getbalance 2>/dev/null || echo 0)
    pqcinfo=$(cli getpqcinfo 2>/dev/null | tr -d '\n' | tr '"' "'" || echo '{}')

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
  "pqc_info": "$pqcinfo",
  "cpu_limit_pct": $CPU_LIMIT,
  "baseline_tx_per_round": $BASE_TX_PER_ROUND,
  "baseline_tx_sleep": $BASE_TX_SLEEP,
  "baseline_mine_sleep": $BASE_MINE_SLEEP,
  "surge_tx_per_round": $SURGE_TX_PER_ROUND,
  "surge_tx_sleep": $SURGE_TX_SLEEP,
  "surge_mine_sleep": $SURGE_MINE_SLEEP,
  "duration_hours": $DURATION_HOURS,
  "pqcsig": "falcon-padded-512",
  "falcon_sig_size_bytes": 666,
  "falcon_pk_size_bytes": 897
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
        echo "$mined" > /tmp/surge72_falcon_mined_count
        sleep "$sleep_s"
    done
}

# ── Transaction loop ─────────────────────────────────────────────
tx_loop() {
    local total_sent=0
    local total_fail=0
    local total_witness_bytes=0  # accumulated estimate

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

        local sent_round=0 fail_round=0
        for ((i = 0; i < txr; i++)); do
            local src_idx=$((RANDOM % ${#WALLETS[@]}))
            local dst_idx=$((RANDOM % ${#WALLETS[@]}))
            while [[ $dst_idx -eq $src_idx ]]; do
                dst_idx=$((RANDOM % ${#WALLETS[@]}))
            done

            local src_wallet="${WALLETS[$src_idx]}"
            local dst_addr="${ADDRS[$dst_idx]}"
            local amount
            amount=$(awk "BEGIN{srand(); printf \"%.8f\", 0.001 + rand() * 0.009}")

            local txid
            txid=$(cliw "$src_wallet" sendtoaddress "$dst_addr" "$amount" "" "" false true 2>/dev/null)
            if [[ -n "$txid" ]]; then
                ((sent_round++))
                # Estimate Falcon witness overhead: sig=666B + pk=897B + 2 ECDSA elements (~104B)
                total_witness_bytes=$((total_witness_bytes + 1667))
            else
                ((fail_round++))
            fi
        done

        total_sent=$((total_sent + sent_round))
        total_fail=$((total_fail + fail_round))
        echo "$total_sent" > /tmp/surge72_falcon_tx_count
        echo "$total_fail"  > /tmp/surge72_falcon_tx_fail
        echo "$total_witness_bytes" > /tmp/surge72_falcon_witness_bytes

        sleep "$txs"
    done
}

# ── Witness stats sampler ────────────────────────────────────────
# Periodically decode a mempool tx and measure actual witness sizes
witness_sampler() {
    echo "timestamp,txid,witness_elements,ecdsa_sig_bytes,ecdsa_pk_bytes,falcon_sig_bytes,falcon_pk_bytes,total_witness_bytes" > "$WITNESS_STATS"
    local samples=0

    while true; do
        sleep 300   # sample every 5 minutes
        local txid
        txid=$(cli getrawmempool 2>/dev/null | grep -oP '"[0-9a-f]{64}"' | head -1 | tr -d '"')
        if [[ -z "$txid" ]]; then continue; fi

        local rawtx
        rawtx=$(cli getrawtransaction "$txid" true 2>/dev/null)
        if [[ -z "$rawtx" ]]; then continue; fi

        # Extract witness data lengths (each element in hex = 2 chars per byte)
        local w0 w1 w2 w3
        w0=$(echo "$rawtx" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    vin = d['vin'][0] if d.get('vin') else {}
    tx = vin.get('txinwitness', [])
    for i,el in enumerate(tx): print(f'{i}:{len(el)//2}')
except: pass
" 2>/dev/null)

        if [[ -n "$w0" ]]; then
            local e0 e1 e2 e3
            e0=$(echo "$w0" | grep '^0:' | cut -d: -f2 || echo 0)
            e1=$(echo "$w0" | grep '^1:' | cut -d: -f2 || echo 0)
            e2=$(echo "$w0" | grep '^2:' | cut -d: -f2 || echo 0)
            e3=$(echo "$w0" | grep '^3:' | cut -d: -f2 || echo 0)
            local total_w=$(( e0 + e1 + e2 + e3 ))
            echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ'),${txid},4,${e0},${e1},${e2},${e3},${total_w}" >> "$WITNESS_STATS"
            ((samples++))
            if (( samples % 10 == 0 )); then
                log "WITNESS SAMPLE #${samples}: ecdsa_sig=${e0}B pk=${e1}B falcon_sig=${e2}B falcon_pk=${e3}B total=${total_w}B"
            fi
        fi
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
            ((surge_num++))
            echo "surge" > "$MODEFILE"
            log "══════ SURGE #${surge_num} START (${elapsed}s elapsed) ══════"

            local surge_end=$((elapsed + SURGE_DURATION))
            while (( SECONDS - start_time < surge_end && SECONDS - start_time < DURATION_SECS )); do
                sleep 10
            done

            echo "baseline" > "$MODEFILE"
            local tx_count mined_count
            tx_count=$(cat /tmp/surge72_falcon_tx_count 2>/dev/null || echo 0)
            mined_count=$(cat /tmp/surge72_falcon_mined_count 2>/dev/null || echo 0)
            log "══════ SURGE #${surge_num} END (tx=${tx_count} mined=${mined_count}) ══════"

            next_surge=$((elapsed + SURGE_INTERVAL))
        fi

        sleep 30
    done
}

# ── Metrics collector ────────────────────────────────────────────
metrics_loop() {
    echo "timestamp,elapsed_h,mode,blocks,dag_tips,mempool_size,mempool_bytes,tx_sent,tx_fail,mined,witness_bytes_est,cpu_user,peers" > "$METRICS"

    local start_time=$SECONDS
    while true; do
        sleep 60
        local elapsed_h
        elapsed_h=$(awk "BEGIN{printf \"%.2f\", ($SECONDS - $start_time) / 3600.0}")
        local mode blocks dag_tips mp_size mp_bytes tx_sent tx_fail mined_count witness_bytes cpu_user peers
        mode=$(get_mode)
        blocks=$(cli getblockcount 2>/dev/null || echo -1)
        dag_tips=$(cli getblockchaininfo 2>/dev/null | grep -o '"dag_tips":[0-9]*' | grep -o '[0-9]*' || echo 0)
        mp_size=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | head -1 | grep -o '[0-9]*' || echo 0)
        mp_bytes=$(cli getmempoolinfo 2>/dev/null | grep '"bytes"' | head -1 | grep -o '[0-9]*' || echo 0)
        tx_sent=$(cat /tmp/surge72_falcon_tx_count 2>/dev/null || echo 0)
        tx_fail=$(cat /tmp/surge72_falcon_tx_fail 2>/dev/null || echo 0)
        mined_count=$(cat /tmp/surge72_falcon_mined_count 2>/dev/null || echo 0)
        witness_bytes=$(cat /tmp/surge72_falcon_witness_bytes 2>/dev/null || echo 0)
        cpu_user=$(top -bn1 | grep "Cpu" | awk '{print $2}' 2>/dev/null || echo 0)
        peers=$(cli getconnectioncount 2>/dev/null || echo 0)

        echo "$(date -u '+%Y-%m-%dT%H:%M:%SZ'),${elapsed_h},${mode},${blocks},${dag_tips},${mp_size},${mp_bytes},${tx_sent},${tx_fail},${mined_count},${witness_bytes},${cpu_user},${peers}" >> "$METRICS"
    done
}

# ── Health watchdog ──────────────────────────────────────────────
watchdog() {
    while true; do
        sleep 120
        if ! cli getblockcount >/dev/null 2>&1; then
            log "WATCHDOG: daemon not responding — restarting..."
            /root/QuantBTC/src/bitcoind -daemon \
                -chain=qbtctestnet \
                -pqcmode=hybrid \
                -pqcsig=falcon \
                -conf=/root/.bitcoin/bitcoin.conf 2>/dev/null
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

        # Re-check cpulimit
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
    log "  72-HOUR FALCON ENDURANCE TEST — ${NODE_LABEL}"
    log "  PQC mode:      ${NODE_ROLE} (-pqcmode=hybrid -pqcsig=falcon)"
    log "  Signature:     Falcon-padded-512 (NIST Level 1, 128-bit PQ)"
    log "  Sig size:      666 bytes  |  PK size: 897 bytes"
    log "  Duration:      ${DURATION_HOURS}h"
    log "  CPU limit:     ${CPU_LIMIT}%"
    log "  Baseline:      ${BASE_TX_PER_ROUND} tx/round, sleep ${BASE_TX_SLEEP}s, mine sleep ${BASE_MINE_SLEEP}s"
    log "  Surge:         ${SURGE_TX_PER_ROUND} tx/round, sleep ${SURGE_TX_SLEEP}s, mine sleep ${SURGE_MINE_SLEEP}s"
    log "  Surge sched:   ${SURGE_DURATION}s every ${SURGE_INTERVAL}s"
    log "  Wallets:       ${NUM_WALLETS}"
    log "  Log:           ${LOG}"
    log "  Metrics:       ${METRICS}"
    log "  Witness stats: ${WITNESS_STATS}"
    log "  Stop:          kill \$(cat ${PIDFILE})"
    log "============================================================"

    # Verify Falcon is active
    check_falcon_mode

    # Stop existing mining sessions
    log "Stopping existing mining screen sessions..."
    screen -ls 2>/dev/null | grep -oP '\d+\.\S+' | grep -v 'falcon72' | while read s; do screen -S "$s" -X quit 2>/dev/null || true; done || true
    pkill -f "generatetoaddress" 2>/dev/null || true
    sleep 2

    apply_cpu_limit
    record_start_state
    setup_wallets

    # Zero counters
    echo 0 > /tmp/surge72_falcon_mined_count
    echo 0 > /tmp/surge72_falcon_tx_count
    echo 0 > /tmp/surge72_falcon_tx_fail
    echo 0 > /tmp/surge72_falcon_witness_bytes

    # Launch all loops
    mining_loop &
    local MINE_PID=$!
    tx_loop &
    local TX_PID=$!
    refund_loop &
    local REFUND_PID=$!
    metrics_loop &
    local METRICS_PID=$!
    witness_sampler &
    local WITNESS_PID=$!
    watchdog &
    local WATCH_PID=$!

    log "All loops started: mine=$MINE_PID tx=$TX_PID refund=$REFUND_PID metrics=$METRICS_PID witness=$WITNESS_PID watchdog=$WATCH_PID"

    # Surge scheduler runs in foreground until duration expires
    surge_scheduler

    # ── Final report ──────────────────────────────────────────────
    log "============================================================"
    log "  FINAL REPORT — ${NODE_LABEL} (${NODE_ROLE})"
    log "============================================================"
    local end_block start_block end_utxo end_supply total_mined total_tx total_fail total_witness_bytes
    end_block=$(cli getblockcount 2>/dev/null || echo 0)
    start_block=$(grep -o '"block_height": [0-9]*' "$STARTFILE" | grep -o '[0-9]*')
    end_utxo=$(cli gettxoutsetinfo 2>/dev/null | grep '"txouts"' | grep -o '[0-9]*' || echo 0)
    end_supply=$(cli gettxoutsetinfo 2>/dev/null | grep '"total_amount"' | grep -oP '[\d.]+' || echo 0)
    total_mined=$(cat /tmp/surge72_falcon_mined_count 2>/dev/null || echo 0)
    total_tx=$(cat /tmp/surge72_falcon_tx_count 2>/dev/null || echo 0)
    total_fail=$(cat /tmp/surge72_falcon_tx_fail 2>/dev/null || echo 0)
    total_witness_bytes=$(cat /tmp/surge72_falcon_witness_bytes 2>/dev/null || echo 0)

    log "  Blocks:          ${start_block} → ${end_block} (+$(( end_block - start_block )))"
    log "  UTXO count:      ${end_utxo}"
    log "  Supply:          ${end_supply} QBTC"
    log "  TX sent:         ${total_tx} (failed: ${total_fail})"
    log "  Mined blocks:    ${total_mined}"
    log "  Witness bytes:   ${total_witness_bytes} (est. Falcon overhead)"
    log "  Avg witness/tx:  $( [[ $total_tx -gt 0 ]] && echo "$((total_witness_bytes / total_tx)) bytes" || echo "n/a" )"
    log "  PQC sig:         Falcon-padded-512"
    log "  Role:            ${NODE_ROLE}"
    log "============================================================"

    # Cleanup
    echo "baseline" > "$MODEFILE"
    kill $MINE_PID $TX_PID $REFUND_PID $METRICS_PID $WITNESS_PID $WATCH_PID 2>/dev/null
    log "All loops stopped. Test finished."
}

trap 'echo "baseline" > "$MODEFILE"; log "SIGNAL — stopping..."; kill 0; exit 0' INT TERM

main
