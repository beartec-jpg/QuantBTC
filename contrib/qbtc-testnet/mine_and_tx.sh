#!/usr/bin/env bash
# mine_and_tx.sh — Continuous mining + transaction stress test
# Runs mining loop (1 core) + tx spray loop in background
# Targets ~50% CPU on a 2-core machine (1 core mining, tx loop is IO-bound)
#
# Usage: RPCUSER=x RPCPASSWORD=y ./mine_and_tx.sh [num_wallets] [tx_per_round]
#   num_wallets   — wallets to create/cycle through (default: 8)
#   tx_per_round  — transactions per batch before next block (default: 5)
#
# To stop: kill the PID written to /tmp/mine_and_tx.pid  (or: kill %1 %2)

set -uo pipefail

NUM_WALLETS="${1:-8}"
TX_PER_ROUND="${2:-5}"
RPCPORT="${RPCPORT:-28332}"
RPCUSER="${RPCUSER:?need RPCUSER}"
RPCPASSWORD="${RPCPASSWORD:?need RPCPASSWORD}"
MINER_WALLET="miner"
LOG="/tmp/mine_and_tx.log"

cli() {
    bitcoin-cli -rpcport="$RPCPORT" -rpcuser="$RPCUSER" -rpcpassword="$RPCPASSWORD" "$@" 2>/dev/null
}

cliw() {
    local w="$1"; shift
    cli -rpcwallet="$w" "$@" 2>/dev/null
}

log() {
    printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" | tee -a "$LOG"
}

# ── Create wallet array ──────────────────────────────────────────
declare -a WALLETS=()
log "Setting up $NUM_WALLETS wallets..."
for i in $(seq 1 "$NUM_WALLETS"); do
    WNAME="txtest_${i}"
    if ! cliw "$WNAME" getwalletinfo >/dev/null 2>&1; then
        cli createwallet "$WNAME" >/dev/null 2>&1 || cli loadwallet "$WNAME" >/dev/null 2>&1 || true
    fi
    WALLETS+=("$WNAME")
done
log "Wallets ready: ${WALLETS[*]}"

# ── Pre-generate one address per wallet ──────────────────────────
declare -a ADDRS=()
for w in "${WALLETS[@]}"; do
    ADDR=$(cliw "$w" getnewaddress "" bech32)
    ADDRS+=("$ADDR")
done
log "Addresses: ${ADDRS[*]:0:3} ... (${#ADDRS[@]} total)"

# ── Fund wallets from miner wallet ──────────────────────────────
MINER_BAL=$(cliw "$MINER_WALLET" getbalance | awk '{printf "%.0f", $1}')
log "Miner balance: ~${MINER_BAL} qBTC"

FUND_AMT="2.0"
for ADDR in "${ADDRS[@]}"; do
    # Check if wallet already has funds
    BAL=$(cli -rpcwallet="" getreceivedbyaddress "$ADDR" 0 2>/dev/null || echo "0")
    if (( $(echo "$BAL < 1" | bc -l 2>/dev/null || echo 1) )); then
        cliw "$MINER_WALLET" sendtoaddress "$ADDR" "$FUND_AMT" "" "" false true >/dev/null 2>&1 && \
            log "Funded $ADDR with $FUND_AMT qBTC" || true
    fi
done

# ── Mine 1 block to confirm funding txs ─────────────────────────
MINE_ADDR=$(cliw "$MINER_WALLET" getnewaddress "" bech32)
cli generatetoaddress 1 "$MINE_ADDR" >/dev/null 2>&1
log "Mined 1 block to confirm funding"

# ── Write PID file ──────────────────────────────────────────────
echo $$ > /tmp/mine_and_tx.pid

# ── Mining loop (background — this is the CPU-bound part) ────────
mining_loop() {
    local addr
    addr=$(cliw "$MINER_WALLET" getnewaddress "" bech32)
    local count=0
    while true; do
        RESULT=$(cli generatetoaddress 1 "$addr" 2>&1)
        if echo "$RESULT" | grep -q '"'; then
            count=$((count + 1))
            HEIGHT=$(cli getblockcount 2>/dev/null || echo "?")
            if (( count % 10 == 0 )); then
                log "MINE: block #${HEIGHT} (${count} mined this session)"
            fi
        else
            sleep 2  # brief backoff on error
        fi
        sleep 1.5  # ~50% duty cycle on 2-core — mine, pause, mine
    done
}

# ── Transaction spray loop (background — IO-bound) ──────────────
tx_loop() {
    local round=0
    local total_tx=0
    sleep 10  # let mining get a head start
    while true; do
        round=$((round + 1))
        local sent=0
        for _t in $(seq 1 "$TX_PER_ROUND"); do
            # Pick random source and dest wallets
            SRC_IDX=$(( RANDOM % NUM_WALLETS ))
            DST_IDX=$(( (SRC_IDX + 1 + RANDOM % (NUM_WALLETS - 1)) % NUM_WALLETS ))
            SRC_W="${WALLETS[$SRC_IDX]}"
            DST_ADDR="${ADDRS[$DST_IDX]}"

            # Random small amount 0.001 – 0.1 qBTC
            AMT=$(printf '0.%03d' $(( RANDOM % 100 + 1 )) )

            TXID=$(cliw "$SRC_W" sendtoaddress "$DST_ADDR" "$AMT" "" "" false true 2>&1)
            if [[ "$TXID" =~ ^[0-9a-f]{64}$ ]]; then
                sent=$((sent + 1))
                total_tx=$((total_tx + 1))
            fi
        done

        if (( round % 5 == 0 )); then
            POOLED=$(cli getmempoolinfo 2>/dev/null | grep '"size"' | grep -o '[0-9]*' || echo "?")
            log "TX: round=${round} sent=${sent}/${TX_PER_ROUND} total=${total_tx} mempool=${POOLED}"
        fi
        sleep 3  # pace the tx spray
    done
}

# ── Refund loop: periodically sweep back to miner ───────────────
refund_loop() {
    sleep 300  # wait 5 min before first sweep
    while true; do
        for w in "${WALLETS[@]}"; do
            BAL=$(cliw "$w" getbalance 2>/dev/null || echo "0")
            # If wallet has > 5 qBTC, sweep half back to miner
            if (( $(echo "$BAL > 5" | bc -l 2>/dev/null || echo 0) )); then
                HALF=$(echo "$BAL / 2" | bc -l 2>/dev/null | head -c 10)
                cliw "$w" sendtoaddress "$MINE_ADDR" "$HALF" "" "" false true >/dev/null 2>&1 && \
                    log "SWEEP: ${w} → miner ${HALF} qBTC" || true
            fi
        done
        sleep 600  # sweep every 10 min
    done
}

# ── Launch loops ─────────────────────────────────────────────────
log "Starting mining loop + tx spray (PID $$)..."
log "  Mining: continuous with 0.5s pause (50% duty)"
log "  TX spray: ${TX_PER_ROUND} tx every 2s across ${NUM_WALLETS} wallets"
log "  To stop: kill \$(cat /tmp/mine_and_tx.pid)"

mining_loop &
MINE_PID=$!
tx_loop &
TX_PID=$!
refund_loop &
REFUND_PID=$!

trap "kill $MINE_PID $TX_PID $REFUND_PID 2>/dev/null; log 'Stopped.'; exit 0" INT TERM

wait
