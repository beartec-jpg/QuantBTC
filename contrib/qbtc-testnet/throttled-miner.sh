#!/bin/bash
# QuantumBTC Testnet Throttled Miner
# - Mines only during scheduled windows (10 min on, 20 min off)
# - Sleeps between blocks to keep CPU < 50%
# - Stops automatically after MAX_BLOCKS per session
# - Only one instance allowed at a time

set -euo pipefail

CLI="/root/QuantBTC/src/bitcoin-cli -conf=/root/.bitcoin/bitcoin.conf"
LOCKFILE="/tmp/qbtc-miner.lock"
LOGFILE="/root/.bitcoin/qbtctestnet/miner.log"

# --- Tunables ---
BLOCKS_PER_CYCLE=5          # mine 5 blocks then pause
SLEEP_BETWEEN_BLOCKS=30     # 30s between each block
CYCLE_PAUSE=300             # 5 min pause between cycles
MAX_BLOCKS_PER_RUN=50       # stop after 50 blocks per run
RUN_DURATION_SECS=600       # mine for 10 minutes max per run
COOLDOWN_SECS=1200          # 20 minute cooldown between runs

# --- Single instance guard ---
if [ -f "$LOCKFILE" ]; then
    OLD_PID=$(cat "$LOCKFILE" 2>/dev/null)
    if kill -0 "$OLD_PID" 2>/dev/null; then
        echo "Miner already running (PID $OLD_PID). Exiting."
        exit 0
    fi
    rm -f "$LOCKFILE"
fi
echo $$ > "$LOCKFILE"
trap 'rm -f "$LOCKFILE"' EXIT

log() {
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') $*" >> "$LOGFILE"
    echo "$(date -u '+%Y-%m-%d %H:%M:%S') $*"
}

# --- Get or create mining address ---
get_address() {
    local addr
    addr=$($CLI -rpcwallet=miner getnewaddress 2>/dev/null) || {
        $CLI createwallet miner false false "" false false true >/dev/null 2>&1 || true
        addr=$($CLI -rpcwallet=miner getnewaddress 2>/dev/null)
    }
    echo "$addr"
}

# --- Main loop ---
log "=== Throttled miner starting (PID $$) ==="

while true; do
    # Check daemon is alive
    if ! $CLI getblockchaininfo >/dev/null 2>&1; then
        log "WARN: bitcoind not responding, waiting 60s..."
        sleep 60
        continue
    fi

    ADDR=$(get_address)
    log "Mining run starting. Address: $ADDR"

    RUN_START=$(date +%s)
    BLOCKS_MINED=0

    while true; do
        NOW=$(date +%s)
        ELAPSED=$((NOW - RUN_START))

        # Check time limit
        if [ "$ELAPSED" -ge "$RUN_DURATION_SECS" ]; then
            log "Time limit reached (${ELAPSED}s). Mined $BLOCKS_MINED blocks this run."
            break
        fi

        # Check block limit
        if [ "$BLOCKS_MINED" -ge "$MAX_BLOCKS_PER_RUN" ]; then
            log "Block limit reached ($BLOCKS_MINED). Stopping run."
            break
        fi

        # Mine a small cycle
        for i in $(seq 1 $BLOCKS_PER_CYCLE); do
            if [ "$BLOCKS_MINED" -ge "$MAX_BLOCKS_PER_RUN" ]; then
                break
            fi

            RESULT=$($CLI generatetoaddress 1 "$ADDR" 999999999 2>&1) || {
                log "WARN: generatetoaddress failed: $RESULT"
                sleep 30
                continue
            }

            BLOCKS_MINED=$((BLOCKS_MINED + 1))
            HEIGHT=$($CLI getblockcount 2>/dev/null || echo "?")
            TIPS=$($CLI getblockchaininfo 2>/dev/null | grep -o '"dag_tips": [0-9]*' | grep -o '[0-9]*' || echo "?")
            log "Block mined #$BLOCKS_MINED (height=$HEIGHT, dag_tips=$TIPS)"

            # Sleep between blocks
            sleep "$SLEEP_BETWEEN_BLOCKS"
        done

        # Pause between cycles
        if [ "$BLOCKS_MINED" -lt "$MAX_BLOCKS_PER_RUN" ]; then
            NOW=$(date +%s)
            ELAPSED=$((NOW - RUN_START))
            if [ "$ELAPSED" -lt "$RUN_DURATION_SECS" ]; then
                log "Cycle pause (${CYCLE_PAUSE}s)..."
                sleep "$CYCLE_PAUSE"
            fi
        fi
    done

    log "Run complete. $BLOCKS_MINED blocks mined. Cooldown ${COOLDOWN_SECS}s..."
    sleep "$COOLDOWN_SECS"
done
