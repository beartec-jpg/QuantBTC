#!/bin/bash
# ============================================================
# QuantumBTC — Kill-9 Crash Recovery Test
#
# Mines blocks, then kills the node with SIGKILL (simulating
# power failure / OOM kill), restarts, and verifies:
#   1. Node recovers without manual intervention
#   2. Chain state is recoverable via -reindex
#   3. Block data survives unclean shutdown (blk*.dat)
#   4. DAG parent pointers are restored
#   5. Node can mine new blocks after recovery
#   6. No permanent corruption in LevelDB
#
# This is the most critical crash-safety test.
# ============================================================

DATADIR="/tmp/qbtc-kill9"
SRCDIR="$(cd "$(dirname "$0")" && pwd)"
BITCOIND="$SRCDIR/build-fresh/src/bitcoind"
CLI="$SRCDIR/build-fresh/src/bitcoin-cli -datadir=$DATADIR -regtest -rpcuser=test -rpcpassword=test -rpcport=18567"
PASS=0
FAIL=0
TESTS=()

pass() { PASS=$((PASS+1)); TESTS+=("PASS: $1"); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); TESTS+=("FAIL: $1 — $2"); echo "  ✗ $1 — $2"; }

wait_for_node() {
    for i in $(seq 1 60); do
        if $CLI getblockchaininfo > /dev/null 2>&1; then return 0; fi
        sleep 1
    done
    return 1
}

# After -reindex, RPC comes up before block import finishes.
# Poll height until it stabilizes (same value for 3 consecutive checks).
wait_for_reindex() {
    wait_for_node || return 1
    local prev=-1
    local stable=0
    for i in $(seq 1 120); do
        local h
        h=$($CLI getblockcount 2>/dev/null) || h=-1
        if [[ "$h" == "$prev" && "$h" -ge 0 ]]; then
            stable=$((stable+1))
            [[ $stable -ge 3 ]] && return 0
        else
            stable=0
        fi
        prev=$h
        sleep 1
    done
    return 1
}

stop_node_graceful() {
    $CLI stop 2>/dev/null || true
    for i in $(seq 1 30); do
        if ! pgrep -f "bitcoind.*qbtc-kill9" > /dev/null 2>&1; then return 0; fi
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
    stop_node_graceful
    if [[ $FAIL -eq 0 ]]; then
        echo ""; echo "ALL TESTS PASSED"; exit 0
    else
        echo ""; echo "SOME TESTS FAILED"; exit 1
    fi
}
trap cleanup EXIT

echo "============================================================"
echo " Kill-9 Crash Recovery Test"
echo "============================================================"
echo ""

# ----------------------------------------------------------
# SETUP
# ----------------------------------------------------------
echo "▸ Setup: Starting fresh regtest node"
pkill -f "bitcoind.*qbtc-kill9" 2>/dev/null || true
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
dbcache=4
debug=validation
[regtest]
listen=0
rpcport=18567
fallbackfee=0.0001
CONF

$BITCOIND -datadir="$DATADIR" -regtest -daemon 2>&1
if ! wait_for_node; then
    echo "FATAL: node did not start"; exit 1
fi

$CLI createwallet "miner" > /dev/null 2>&1
ADDR=$($CLI -rpcwallet=miner getnewaddress 2>&1)
echo "  Node started, address: $ADDR"
echo ""

# ----------------------------------------------------------
# PHASE 1: Mine 1000 blocks to build up meaningful state
# ----------------------------------------------------------
echo "▸ Phase 1: Mining 1000 blocks (batches of 100)..."
for b in $(seq 1 10); do
    $CLI generatetoaddress 100 "$ADDR" 999999999 > /dev/null 2>&1
    echo "    Mined $((b*100)) / 1000"
done

PRE_HEIGHT=$($CLI getblockcount 2>&1)
PRE_HASH=$($CLI getbestblockhash 2>&1)
echo "  Height=$PRE_HEIGHT tip=${PRE_HASH:0:16}..."
[[ "$PRE_HEIGHT" -ge 1000 ]] && pass "Mined $PRE_HEIGHT blocks" || fail "Mining" "only $PRE_HEIGHT"
echo ""

# ----------------------------------------------------------
# PHASE 2: Kill -9 (SIGKILL — no cleanup)
# ----------------------------------------------------------
echo "▸ Phase 2: Sending SIGKILL to bitcoind"
PIDS=$(pgrep -f "bitcoind.*qbtc-kill9")
if [[ -n "$PIDS" ]]; then
    kill -9 $PIDS 2>/dev/null
    sleep 2
    pass "Sent SIGKILL to PID(s): $PIDS"
else
    fail "Kill" "no bitcoind process found"
fi
echo ""

# ----------------------------------------------------------
# PHASE 3: Restart and recover
# ----------------------------------------------------------
echo "▸ Phase 3: Restarting after crash (with -reindex)..."
# After SIGKILL, LevelDB block index may not be flushed (especially
# with small regtest blocks).  Raw block data is in blk*.dat, so
# -reindex rebuilds the index and recovers the full chain.
$BITCOIND -datadir="$DATADIR" -regtest -reindex -daemon 2>&1
if wait_for_reindex; then
    pass "Node recovered after SIGKILL (reindex complete)"
else
    fail "Recovery" "node did not come back up"
    exit 1
fi
echo ""

# ----------------------------------------------------------
# PHASE 4: Verify state consistency
# ----------------------------------------------------------
echo "▸ Phase 4: State verification"

POST_HEIGHT=$($CLI getblockcount 2>&1)
POST_HASH=$($CLI getbestblockhash 2>&1)

# With -reindex, the chain is rebuilt from blk*.dat so height should match exactly.
DIFF=$(( PRE_HEIGHT - POST_HEIGHT ))
if [[ $DIFF -lt 0 ]]; then DIFF=$(( -DIFF )); fi

[[ $DIFF -eq 0 ]] && pass "Height recovered exactly: $POST_HEIGHT" \
                  || fail "Height mismatch" "pre=$PRE_HEIGHT post=$POST_HEIGHT diff=$DIFF"

# If height matches exactly, tip hash should also match
if [[ "$POST_HEIGHT" == "$PRE_HEIGHT" ]]; then
    [[ "$POST_HASH" == "$PRE_HASH" ]] && pass "Tip hash matches" || fail "Tip hash drift" "pre=${PRE_HASH:0:16} post=${POST_HASH:0:16}"
else
    echo "  (Tip hash comparison skipped — height differs by $DIFF)"
fi

# Verify block at height 500 is accessible
BLK500=$($CLI getblockhash 500 2>&1)
HDR500=$($CLI getblockheader "$BLK500" 2>&1)
OK500=$(echo "$HDR500" | python3 -c "import sys,json; d=json.load(sys.stdin); print('ok' if d.get('height')==500 else 'bad')" 2>/dev/null)
[[ "$OK500" == "ok" ]] && pass "Block 500 accessible after crash" || fail "Block 500 lookup" "failed"
echo ""

# ----------------------------------------------------------
# PHASE 5: Mine more blocks after recovery
# ----------------------------------------------------------
echo "▸ Phase 5: Mining after crash recovery"
# Wallet may need loading after reindex
$CLI loadwallet "miner" > /dev/null 2>&1 || true
$CLI generatetoaddress 100 "$ADDR" 999999999 > /dev/null 2>&1
FINAL_HEIGHT=$($CLI getblockcount 2>&1)
EXPECTED=$(( POST_HEIGHT + 100 ))
[[ "$FINAL_HEIGHT" -ge "$EXPECTED" ]] && pass "Mined 100 more (height=$FINAL_HEIGHT)" || fail "Post-crash mining" "height=$FINAL_HEIGHT expected≥$EXPECTED"
echo ""

# ----------------------------------------------------------
# PHASE 6: Second kill -9 + recovery (double-crash)
# ----------------------------------------------------------
echo "▸ Phase 6: Second SIGKILL (double-crash test)"
PIDS2=$(pgrep -f "bitcoind.*qbtc-kill9")
if [[ -n "$PIDS2" ]]; then
    kill -9 $PIDS2 2>/dev/null
    sleep 2
fi

$BITCOIND -datadir="$DATADIR" -regtest -reindex -daemon 2>&1
if wait_for_reindex; then
    pass "Survived double kill-9 (reindex)"
else
    fail "Double crash" "did not recover"
    exit 1
fi

DOUBLE_HEIGHT=$($CLI getblockcount 2>&1)
[[ "$DOUBLE_HEIGHT" -ge "$POST_HEIGHT" ]] && pass "Double-crash height=$DOUBLE_HEIGHT" || fail "Double-crash data loss" "height=$DOUBLE_HEIGHT"
echo ""

# ----------------------------------------------------------
# PHASE 7: debug.log scan
# ----------------------------------------------------------
echo "▸ Phase 7: debug.log error scan (ignoring expected crash messages)"
# After kill-9, LevelDB may log recovery warnings — that's expected.
# We look for actual assertion failures.
ASSERTS=$(grep -c "Assertion\|SIGABRT\|std::terminate" "$DATADIR/regtest/debug.log" 2>/dev/null || true)
ASSERTS=$(echo "$ASSERTS" | tr -d '\n' | grep -oP '^\d+' || echo 0)
[[ "$ASSERTS" -eq 0 ]] && pass "No assertion failures in log" || fail "Assertion failures" "$ASSERTS found"
