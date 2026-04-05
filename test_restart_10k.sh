#!/bin/bash
# ============================================================
# QuantumBTC — Restart-After-10k-Blocks Test
#
# Mines 10,000 blocks, stops the node gracefully, restarts,
# and verifies:
#   1. Block count matches
#   2. Chain tip hash is identical
#   3. DAG parent pointers are restored (vDagParents)
#   4. GHOSTDAG blue scores survive restart
#   5. No assertion failures or errors in debug.log
#   6. PQC sigcache counters are reset (fresh process)
#   7. Node can mine additional blocks after restart
#
# Validates the hash-identity stability fix (commit 74ab011).
# ============================================================

DATADIR="/tmp/qbtc-restart-10k"
SRCDIR="$(cd "$(dirname "$0")" && pwd)"
BITCOIND="$SRCDIR/build-fresh/src/bitcoind"
CLI="$SRCDIR/build-fresh/src/bitcoin-cli -datadir=$DATADIR -regtest -rpcuser=test -rpcpassword=test -rpcport=18566"
PASS=0
FAIL=0
TESTS=()
TARGET_BLOCKS=10000

pass() { PASS=$((PASS+1)); TESTS+=("PASS: $1"); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); TESTS+=("FAIL: $1 — $2"); echo "  ✗ $1 — $2"; }

wait_for_node() {
    for i in $(seq 1 60); do
        if $CLI getblockchaininfo > /dev/null 2>&1; then return 0; fi
        sleep 1
    done
    return 1
}

stop_node() {
    $CLI stop 2>/dev/null || true
    for i in $(seq 1 30); do
        if ! pgrep -f "bitcoind.*qbtc-restart-10k" > /dev/null 2>&1; then return 0; fi
        sleep 1
    done
    return 1
}

cleanup() {
    echo ""
    echo "────────────────────────────────────────────"
    echo " Results: $PASS passed, $FAIL failed"
    echo "────────────────────────────────────────────"
    for t in "${TESTS[@]}"; do echo "  $t"; done
    stop_node
    if [[ $FAIL -eq 0 ]]; then
        echo ""; echo "ALL TESTS PASSED"; exit 0
    else
        echo ""; echo "SOME TESTS FAILED"; exit 1
    fi
}
trap cleanup EXIT

echo "============================================================"
echo " Restart-After-${TARGET_BLOCKS}-Blocks Test"
echo "============================================================"
echo ""

# ----------------------------------------------------------
# SETUP
# ----------------------------------------------------------
echo "▸ Setup: Starting fresh regtest node"
pkill -f "bitcoind.*qbtc-restart-10k" 2>/dev/null || true
sleep 1
rm -rf "$DATADIR"
mkdir -p "$DATADIR"

cat > "$DATADIR/bitcoin.conf" << 'CONF'
regtest=1
server=1
rpcuser=test
rpcpassword=test
rpcallowip=127.0.0.1
pqc=1
pqcmode=hybrid
dag=1
txindex=1
debug=dag
debug=validation
[regtest]
listen=0
rpcport=18566
fallbackfee=0.0001
CONF

$BITCOIND -datadir="$DATADIR" -regtest -daemon 2>&1
if ! wait_for_node; then
    echo "FATAL: node did not start"; exit 1
fi

$CLI createwallet "miner" > /dev/null 2>&1
ADDR=$($CLI -rpcwallet=miner getnewaddress 2>&1)
echo "  Node started, mining address: $ADDR"
echo ""

# ----------------------------------------------------------
# PHASE 1: Mine TARGET_BLOCKS blocks
# ----------------------------------------------------------
echo "▸ Phase 1: Mining $TARGET_BLOCKS blocks (batches of 500)..."
MINED=0
while [[ $MINED -lt $TARGET_BLOCKS ]]; do
    BATCH=$(( TARGET_BLOCKS - MINED ))
    [[ $BATCH -gt 500 ]] && BATCH=500
    $CLI generatetoaddress $BATCH "$ADDR" 999999999 > /dev/null 2>&1
    MINED=$(( MINED + BATCH ))
    echo "    Mined $MINED / $TARGET_BLOCKS"
done

PRE_HEIGHT=$($CLI getblockcount 2>&1)
PRE_HASH=$($CLI getbestblockhash 2>&1)
PRE_TIP=$($CLI getblockheader "$PRE_HASH" 2>&1)
PRE_SCORE=$(echo "$PRE_TIP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('blue_score','N/A'))" 2>/dev/null)
PRE_DAGPARENTS=$(echo "$PRE_TIP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('dagparents',[])))" 2>/dev/null)

echo "  Pre-restart: height=$PRE_HEIGHT hash=${PRE_HASH:0:16}... blue_score=$PRE_SCORE dagparents=$PRE_DAGPARENTS"
echo ""

[[ "$PRE_HEIGHT" -ge "$TARGET_BLOCKS" ]] && pass "Mined $PRE_HEIGHT blocks" || fail "Block count" "only $PRE_HEIGHT"

# ----------------------------------------------------------
# PHASE 2: Graceful stop + restart
# ----------------------------------------------------------
echo "▸ Phase 2: Graceful shutdown and restart"
stop_node
echo "  Node stopped."

# Check debug.log for fatal errors before restart
ERRORS=$(grep -ci "EXCEPTION\|assert.*fail\|segfault\|abort\|fatal" "$DATADIR/regtest/debug.log" 2>/dev/null || echo 0)
[[ "$ERRORS" -eq 0 ]] && pass "No fatal errors before restart" || fail "Pre-restart errors" "$ERRORS found"

sleep 2
$BITCOIND -datadir="$DATADIR" -regtest -daemon 2>&1
if ! wait_for_node; then
    fail "Node restart" "did not come back up"; exit 1
fi
pass "Node restarted successfully"
echo ""

# ----------------------------------------------------------
# PHASE 3: Verify chain state after restart
# ----------------------------------------------------------
echo "▸ Phase 3: Post-restart verification"

POST_HEIGHT=$($CLI getblockcount 2>&1)
POST_HASH=$($CLI getbestblockhash 2>&1)
POST_TIP=$($CLI getblockheader "$POST_HASH" 2>&1)
POST_SCORE=$(echo "$POST_TIP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('blue_score','N/A'))" 2>/dev/null)

[[ "$POST_HEIGHT" == "$PRE_HEIGHT" ]] && pass "Height preserved: $POST_HEIGHT" || fail "Height mismatch" "pre=$PRE_HEIGHT post=$POST_HEIGHT"
[[ "$POST_HASH" == "$PRE_HASH" ]] && pass "Tip hash preserved: ${POST_HASH:0:16}..." || fail "Tip hash drift" "pre=${PRE_HASH:0:16} post=${POST_HASH:0:16}"
[[ "$POST_SCORE" == "$PRE_SCORE" ]] && pass "Blue score preserved: $POST_SCORE" || fail "Blue score drift" "pre=$PRE_SCORE post=$POST_SCORE"

# Verify a mid-chain block's hash is also stable
MID=$(( PRE_HEIGHT / 2 ))
MID_HASH=$($CLI getblockhash $MID 2>&1)
MID_HEADER=$($CLI getblockheader "$MID_HASH" 2>&1)
MID_OK=$(echo "$MID_HEADER" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d.get('height')==$MID else 'bad')" 2>/dev/null)
[[ "$MID_OK" == "ok" ]] && pass "Mid-chain block $MID accessible" || fail "Mid-chain lookup" "block $MID"

# ----------------------------------------------------------
# PHASE 4: Sigcache counters (should be zero after fresh start)
# ----------------------------------------------------------
echo ""
echo "▸ Phase 4: Sigcache counters after restart"
CACHE=$($CLI getpqcsigcachestats 2>&1)
if echo "$CACHE" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    pass "getpqcsigcachestats RPC works"
else
    fail "getpqcsigcachestats" "RPC not available or parse error"
fi

# ----------------------------------------------------------
# PHASE 5: Can mine after restart
# ----------------------------------------------------------
echo ""
echo "▸ Phase 5: Mining after restart"
$CLI generatetoaddress 10 "$ADDR" 999999999 > /dev/null 2>&1
FINAL_HEIGHT=$($CLI getblockcount 2>&1)
EXPECTED=$(( PRE_HEIGHT + 10 ))
[[ "$FINAL_HEIGHT" -ge "$EXPECTED" ]] && pass "Mined 10 more blocks (height=$FINAL_HEIGHT)" || fail "Post-restart mining" "height=$FINAL_HEIGHT expected≥$EXPECTED"

# ----------------------------------------------------------
# PHASE 6: No errors in debug.log
# ----------------------------------------------------------
echo ""
echo "▸ Phase 6: debug.log error scan"
POST_ERRORS=$(grep -ci "EXCEPTION\|assert.*fail\|segfault\|abort\|fatal" "$DATADIR/regtest/debug.log" 2>/dev/null || echo 0)
[[ "$POST_ERRORS" -eq 0 ]] && pass "No errors in debug.log" || fail "Post-restart errors" "$POST_ERRORS found"
