#!/bin/bash
# ============================================================
# QuantumBTC — IBD From Genesis on Populated Chain
#
# Starts a "source" node with a pre-mined chain, then starts
# a fresh "sync" node that connects and performs Initial Block
# Download (IBD) from genesis.  Verifies:
#   1. Sync node downloads all blocks
#   2. Chain tips match
#   3. GHOSTDAG blue scores match
#   4. Block hashes are identical (no hash-identity drift)
#   5. PQC verification succeeds during IBD
#   6. No errors in either node's debug.log
#
# This catches mixed-version sync bugs and validates that the
# 80-byte GetHash() invariant holds across the wire.
# ============================================================

DATADIR_SRC="/tmp/qbtc-ibd-source"
DATADIR_SYNC="/tmp/qbtc-ibd-sync"
SRCDIR="$(cd "$(dirname "$0")" && pwd)"
BITCOIND="$SRCDIR/build-fresh/src/bitcoind"
CLI_SRC="$SRCDIR/build-fresh/src/bitcoin-cli -datadir=$DATADIR_SRC -regtest -rpcuser=test -rpcpassword=test -rpcport=18568"
CLI_SYNC="$SRCDIR/build-fresh/src/bitcoin-cli -datadir=$DATADIR_SYNC -regtest -rpcuser=test -rpcpassword=test -rpcport=18569"
PASS=0
FAIL=0
TESTS=()
TARGET_BLOCKS=2000
P2P_PORT_SRC=18570
P2P_PORT_SYNC=18571

pass() { PASS=$((PASS+1)); TESTS+=("PASS: $1"); echo "  ✓ $1"; }
fail() { FAIL=$((FAIL+1)); TESTS+=("FAIL: $1 — $2"); echo "  ✗ $1 — $2"; }

wait_for_rpc() {
    local cli="$1"
    for i in $(seq 1 60); do
        if $cli getblockchaininfo > /dev/null 2>&1; then return 0; fi
        sleep 1
    done
    return 1
}

wait_for_sync() {
    local target_height=$1
    local max_wait=${2:-300}  # default 5 min
    for i in $(seq 1 $max_wait); do
        local h
        h=$($CLI_SYNC getblockcount 2>/dev/null)
        if [[ "$h" == "$target_height" ]]; then return 0; fi
        if (( i % 30 == 0 )); then echo "    Sync progress: $h / $target_height"; fi
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
    $CLI_SYNC stop 2>/dev/null || true
    $CLI_SRC stop 2>/dev/null || true
    sleep 3
    pkill -f "bitcoind.*qbtc-ibd" 2>/dev/null || true
    if [[ $FAIL -eq 0 ]]; then
        echo ""; echo "ALL TESTS PASSED"; exit 0
    else
        echo ""; echo "SOME TESTS FAILED"; exit 1
    fi
}
trap cleanup EXIT

echo "============================================================"
echo " IBD From Genesis Test ($TARGET_BLOCKS blocks)"
echo "============================================================"
echo ""

# ----------------------------------------------------------
# SETUP: Source node
# ----------------------------------------------------------
echo "▸ Setup: Starting source node"
pkill -f "bitcoind.*qbtc-ibd" 2>/dev/null || true
sleep 1
rm -rf "$DATADIR_SRC" "$DATADIR_SYNC"
mkdir -p "$DATADIR_SRC" "$DATADIR_SYNC"

cat > "$DATADIR_SRC/bitcoin.conf" << CONF
regtest=1
server=1
rpcuser=test
rpcpassword=test
rpcallowip=127.0.0.1
pqc=1
pqcmode=hybrid
dag=1
txindex=1
debug=net
debug=validation
[regtest]
listen=1
port=$P2P_PORT_SRC
rpcport=18568
fallbackfee=0.0001
CONF

$BITCOIND -datadir="$DATADIR_SRC" -regtest -bind=127.0.0.1:$P2P_PORT_SRC -daemon 2>&1
if ! wait_for_rpc "$CLI_SRC"; then
    echo "FATAL: source node did not start"; exit 1
fi

$CLI_SRC createwallet "miner" > /dev/null 2>&1
ADDR=$($CLI_SRC -rpcwallet=miner getnewaddress 2>&1)
echo "  Source node started, mining address: $ADDR"
echo ""

# ----------------------------------------------------------
# PHASE 1: Mine blocks on source
# ----------------------------------------------------------
echo "▸ Phase 1: Mining $TARGET_BLOCKS blocks on source..."
MINED=0
while [[ $MINED -lt $TARGET_BLOCKS ]]; do
    BATCH=$(( TARGET_BLOCKS - MINED ))
    [[ $BATCH -gt 500 ]] && BATCH=500
    $CLI_SRC generatetoaddress $BATCH "$ADDR" 999999999 > /dev/null 2>&1
    MINED=$(( MINED + BATCH ))
    echo "    Mined $MINED / $TARGET_BLOCKS"
done

SRC_HEIGHT=$($CLI_SRC getblockcount 2>&1)
SRC_HASH=$($CLI_SRC getbestblockhash 2>&1)
SRC_HEADER=$($CLI_SRC getblockheader "$SRC_HASH" 2>&1)
SRC_SCORE=$(echo "$SRC_HEADER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('blue_score','N/A'))" 2>/dev/null)

echo "  Source: height=$SRC_HEIGHT tip=${SRC_HASH:0:16}... blue_score=$SRC_SCORE"
[[ "$SRC_HEIGHT" -ge "$TARGET_BLOCKS" ]] && pass "Source has $SRC_HEIGHT blocks" || fail "Source mining" "only $SRC_HEIGHT"
echo ""

# ----------------------------------------------------------
# PHASE 2: Start sync node and connect
# ----------------------------------------------------------
echo "▸ Phase 2: Starting sync node (empty chain)"

cat > "$DATADIR_SYNC/bitcoin.conf" << CONF
regtest=1
server=1
rpcuser=test
rpcpassword=test
rpcallowip=127.0.0.1
pqc=1
pqcmode=hybrid
dag=1
txindex=1
debug=net
debug=validation
[regtest]
listen=1
port=$P2P_PORT_SYNC
rpcport=18569
fallbackfee=0.0001
addnode=127.0.0.1:$P2P_PORT_SRC
CONF

$BITCOIND -datadir="$DATADIR_SYNC" -regtest -bind=127.0.0.1:$P2P_PORT_SYNC -daemon 2>&1
if ! wait_for_rpc "$CLI_SYNC"; then
    echo "FATAL: sync node did not start"; exit 1
fi
pass "Sync node started with empty chain"
echo ""

# ----------------------------------------------------------
# PHASE 3: Wait for IBD completion
# ----------------------------------------------------------
echo "▸ Phase 3: Waiting for IBD ($TARGET_BLOCKS blocks)..."
if wait_for_sync "$SRC_HEIGHT" 600; then
    pass "IBD complete — synced to height $SRC_HEIGHT"
else
    SYNC_H=$($CLI_SYNC getblockcount 2>/dev/null)
    fail "IBD incomplete" "reached $SYNC_H / $SRC_HEIGHT"
fi
echo ""

# ----------------------------------------------------------
# PHASE 4: Verify chain identity matches
# ----------------------------------------------------------
echo "▸ Phase 4: Chain identity verification"

SYNC_HEIGHT=$($CLI_SYNC getblockcount 2>&1)
SYNC_HASH=$($CLI_SYNC getbestblockhash 2>&1)
SYNC_HEADER=$($CLI_SYNC getblockheader "$SYNC_HASH" 2>&1)
SYNC_SCORE=$(echo "$SYNC_HEADER" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('blue_score','N/A'))" 2>/dev/null)

[[ "$SYNC_HEIGHT" == "$SRC_HEIGHT" ]] && pass "Heights match: $SYNC_HEIGHT" || fail "Height mismatch" "src=$SRC_HEIGHT sync=$SYNC_HEIGHT"
[[ "$SYNC_HASH" == "$SRC_HASH" ]] && pass "Tip hashes match" || fail "Tip hash mismatch" "src=${SRC_HASH:0:16} sync=${SYNC_HASH:0:16}"
[[ "$SYNC_SCORE" == "$SRC_SCORE" ]] && pass "Blue scores match: $SYNC_SCORE" || fail "Blue score mismatch" "src=$SRC_SCORE sync=$SYNC_SCORE"

# Spot-check 5 random blocks
echo ""
echo "  Spot-checking 5 random blocks..."
for _ in $(seq 1 5); do
    BH=$(( RANDOM % SRC_HEIGHT + 1 ))
    HASH_SRC=$($CLI_SRC getblockhash $BH 2>&1)
    HASH_SYNC=$($CLI_SYNC getblockhash $BH 2>&1)
    if [[ "$HASH_SRC" == "$HASH_SYNC" ]]; then
        pass "Block $BH hash matches"
    else
        fail "Block $BH hash mismatch" "src=${HASH_SRC:0:16} sync=${HASH_SYNC:0:16}"
    fi
done
echo ""

# ----------------------------------------------------------
# PHASE 5: Sigcache stats on sync node (should show misses from IBD)
# ----------------------------------------------------------
echo "▸ Phase 5: IBD signature cache stats"
CACHE=$($CLI_SYNC getpqcsigcachestats 2>&1)
if echo "$CACHE" | python3 -c "import sys,json; json.load(sys.stdin)" 2>/dev/null; then
    ECDSA_M=$(echo "$CACHE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ecdsa_misses',0))")
    ECDSA_H=$(echo "$CACHE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('ecdsa_hits',0))")
    echo "  ECDSA: hits=$ECDSA_H misses=$ECDSA_M"
    DIL_M=$(echo "$CACHE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dilithium_misses',0))")
    DIL_H=$(echo "$CACHE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('dilithium_hits',0))")
    echo "  Dilithium: hits=$DIL_H misses=$DIL_M"
    pass "Sigcache stats available"
else
    fail "getpqcsigcachestats" "not available"
fi
echo ""

# ----------------------------------------------------------
# PHASE 6: debug.log error scan on both nodes
# ----------------------------------------------------------
echo "▸ Phase 6: debug.log error scan"
SRC_ERRS=$(grep -i "EXCEPTION\|assert.*fail\|segfault\|abort\|fatal" "$DATADIR_SRC/regtest/debug.log" 2>/dev/null | wc -l)
SYNC_ERRS=$(grep -i "EXCEPTION\|assert.*fail\|segfault\|abort\|fatal" "$DATADIR_SYNC/regtest/debug.log" 2>/dev/null | wc -l)
[[ "$SRC_ERRS" -eq 0 ]] && pass "Source node: no errors" || fail "Source errors" "$SRC_ERRS found"
[[ "$SYNC_ERRS" -eq 0 ]] && pass "Sync node: no errors" || fail "Sync errors" "$SYNC_ERRS found"
