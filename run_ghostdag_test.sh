#!/bin/bash
# QuantumBTC GHOSTDAG 50+ Block Robustness Test
# Mines blocks, creates forks, and checks GHOSTDAG scoring
set -e

CLI="./src/bitcoin-cli -regtest"
DESC='raw(51)#8lvh9jxk'

mine() {
    $CLI generateblock "$DESC" '[]' 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin)['hash'])"
}

echo "========================================================================"
echo "QuantumBTC GHOSTDAG Robustness Test"
echo "========================================================================"

# Phase 1: Mine 50 blocks linearly
echo ""
echo "[Phase 1] Mining 50 blocks linearly..."
for i in $(seq 1 50); do
    HASH=$(mine)
    if [ $((i % 10)) -eq 0 ]; then
        HEIGHT=$($CLI getblockchaininfo | python3 -c "import sys,json; print(json.load(sys.stdin)['blocks'])")
        TIPS=$($CLI getblockchaininfo | python3 -c "import sys,json; print(json.load(sys.stdin).get('dag_tips','?'))")
        echo "  Mined block $i  height=$HEIGHT  dag_tips=$TIPS"
    fi
done

echo ""
echo "[Phase 1 Result]"
$CLI getblockchaininfo | python3 -c "
import sys, json
info = json.load(sys.stdin)
print(f\"  height:     {info['blocks']}\")
print(f\"  dagmode:    {info['dagmode']}\")
print(f\"  ghostdag_k: {info['ghostdag_k']}\")
print(f\"  dag_tips:   {info['dag_tips']}\")
print(f\"  chainwork:  {info['chainwork'][:16]}...\")
"

# Phase 2: Create 5 short forks at different heights
echo ""
echo "[Phase 2] Creating 5 parallel forks..."
BEST=$($CLI getbestblockhash)

for fork in $(seq 1 5); do
    # Get a block a few behind tip to invalidate from
    FORK_HEIGHT=$((50 - fork * 2))
    FORK_BASE=$($CLI getblockhash $FORK_HEIGHT 2>/dev/null)
    NEXT_HASH=$($CLI getblockhash $((FORK_HEIGHT + 1)) 2>/dev/null)
    
    if [ -z "$NEXT_HASH" ]; then
        echo "  Fork $fork: SKIP (can't find block at h$((FORK_HEIGHT + 1)))"
        continue
    fi
    
    # Invalidate to create fork point
    $CLI invalidateblock "$NEXT_HASH" 2>/dev/null || true
    
    # Mine 2 blocks on the fork
    H1=$(mine 2>/dev/null || echo "")
    H2=$(mine 2>/dev/null || echo "")
    
    if [ -n "$H2" ]; then
        # Get GHOSTDAG data for the fork tip
        HDR=$($CLI getblockheader "$H2" 2>/dev/null || echo "{}")
        BLUE_SCORE=$(echo "$HDR" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('blue_score','?'))" 2>/dev/null || echo "?")
        DAG_PARENTS=$(echo "$HDR" | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d.get('dagparents',[])))" 2>/dev/null || echo "?")
        echo "  Fork $fork: base=h$FORK_HEIGHT  tip=${H2:0:16}...  blue_score=$BLUE_SCORE  dagparents=$DAG_PARENTS"
    else
        echo "  Fork $fork: base=h$FORK_HEIGHT  (mining failed)"
    fi
    
    # Reconsider original chain 
    $CLI reconsiderblock "$NEXT_HASH" 2>/dev/null || true
done

echo ""
TIPS=$($CLI getblockchaininfo | python3 -c "import sys,json; print(json.load(sys.stdin).get('dag_tips','?'))")
HEIGHT=$($CLI getblockchaininfo | python3 -c "import sys,json; print(json.load(sys.stdin)['blocks'])")
echo "  After forks: height=$HEIGHT  dag_tips=$TIPS"

# Phase 3: Mine 10 more blocks to extend and merge
echo ""
echo "[Phase 3] Mining 10 more blocks to extend chain..."
for i in $(seq 1 10); do
    mine > /dev/null
done
TIPS=$($CLI getblockchaininfo | python3 -c "import sys,json; print(json.load(sys.stdin).get('dag_tips','?'))")
HEIGHT=$($CLI getblockchaininfo | python3 -c "import sys,json; print(json.load(sys.stdin)['blocks'])")
echo "  After extension: height=$HEIGHT  dag_tips=$TIPS"

# Phase 4: Force >18 concurrent forks (red block test)
echo ""
echo "[Phase 4] Creating 22 concurrent forks from same base (K=18 red block test)..."
CURRENT_HEIGHT=$($CLI getblockchaininfo | python3 -c "import sys,json; print(json.load(sys.stdin)['blocks'])")
CURRENT_BEST=$($CLI getbestblockhash)

# Invalidate the tip
$CLI invalidateblock "$CURRENT_BEST" 2>/dev/null || true

FORK_HASHES=""
for f in $(seq 1 22); do
    H=$(mine)
    FORK_HASHES="$FORK_HASHES $H"
    # Invalidate this fork block to go back to the base
    $CLI invalidateblock "$H" 2>/dev/null || true
done
echo "  Created 22 competing blocks from same base"

# Reconsider ALL fork blocks + original tip
for H in $FORK_HASHES; do
    $CLI reconsiderblock "$H" 2>/dev/null || true
done
$CLI reconsiderblock "$CURRENT_BEST" 2>/dev/null || true

# Mine a merge block
echo "  Mining merge block..."
MERGE=$(mine)
echo "  Merge block: $MERGE"

# Check GHOSTDAG data on merge block
echo ""
echo "[Phase 4 Result] Merge block GHOSTDAG data:"
$CLI getblockheader "$MERGE" | python3 -c "
import sys, json
hdr = json.load(sys.stdin)
print(f\"  hash:            {hdr['hash'][:40]}...\")
print(f\"  height:          {hdr['height']}\")
print(f\"  blue_score:      {hdr.get('blue_score', '?')}\")
print(f\"  blue_work:       {hdr.get('blue_work', '?')}\")
print(f\"  selected_parent: {hdr.get('selected_parent', '?')[:40]}...\")
print(f\"  dagparents:      {len(hdr.get('dagparents', []))}\")
blues = hdr.get('mergeset_blues', [])
reds = hdr.get('mergeset_reds', [])
print(f\"  mergeset_blues:  {len(blues)}\")
print(f\"  mergeset_reds:   {len(reds)}\")
if reds:
    print(f\"  *** RED BLOCKS DETECTED (anticone > K=18) ***\")
    for r in reds[:5]:
        print(f\"    red: {r[:40]}...\")
else:
    print(f\"  (no red blocks in this merge)\")
"

# Phase 5: Scan all blocks for red entries
echo ""
echo "[Phase 5] Scanning all blocks for GHOSTDAG red entries..."
FINAL_HEIGHT=$($CLI getblockchaininfo | python3 -c "import sys,json; print(json.load(sys.stdin)['blocks'])")

python3 -c "
import subprocess, json

def rpc(method, *args):
    cmd = ['./src/bitcoin-cli', '-regtest', method] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return json.loads(r.stdout) if r.stdout.strip() else None

height = $FINAL_HEIGHT
total_blues = 0
total_reds = 0
max_reds = 0
max_reds_h = 0
max_parents = 0
max_parents_h = 0
sample_headers = []

for h in range(1, height + 1):
    bh = rpc('getblockhash', h)
    hdr = rpc('getblockheader', bh)
    blues = len(hdr.get('mergeset_blues', []))
    reds = len(hdr.get('mergeset_reds', []))
    parents = len(hdr.get('dagparents', []))
    total_blues += blues
    total_reds += reds
    if reds > max_reds:
        max_reds = reds
        max_reds_h = h
    if parents > max_parents:
        max_parents = parents
        max_parents_h = h
    if h in [1, 10, 25, 50, height - 1, height]:
        sample_headers.append((h, hdr))

print(f'  Total blocks scanned: {height}')
print(f'  Total mergeset_blues: {total_blues}')
print(f'  Total mergeset_reds:  {total_reds}')
print(f'  Max dagparents in one block: {max_parents} (height {max_parents_h})')
if max_reds > 0:
    print(f'  Max red blocks in one merge: {max_reds} (height {max_reds_h})')
else:
    print(f'  No red blocks found across all blocks')

print()
print('  Sample block headers:')
print(f'  {\"h\":>4}  {\"blue_score\":>10}  {\"blue_work\":>10}  {\"parents\":>7}  {\"blues\":>5}  {\"reds\":>4}')
print(f'  {\"----\":>4}  {\"----------\":>10}  {\"----------\":>10}  {\"-------\":>7}  {\"-----\":>5}  {\"----\":>4}')
for h, hdr in sample_headers:
    bs = hdr.get('blue_score', '?')
    bw = hdr.get('blue_work', '?')
    dp = len(hdr.get('dagparents', []))
    bl = len(hdr.get('mergeset_blues', []))
    rd = len(hdr.get('mergeset_reds', []))
    print(f'  {h:4d}  {bs:>10}  {bw:>10}  {dp:>7}  {bl:>5}  {rd:>4}')
"

# Phase 6: Final output
echo ""
echo "========================================================================"
echo "[Final] getblockchaininfo:"
echo "========================================================================"
$CLI getblockchaininfo

echo ""
echo "========================================================================"
echo "[Final] Best block header:"
echo "========================================================================"
$CLI getblockheader $($CLI getbestblockhash)

echo ""
echo "========================================================================"
echo "[Final] getmininginfo:"
echo "========================================================================"
$CLI getmininginfo

echo ""
echo "========================================================================"
echo "GHOSTDAG ROBUSTNESS TEST COMPLETE"
echo "========================================================================"
