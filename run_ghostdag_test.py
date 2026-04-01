#!/usr/bin/env python3
"""QuantumBTC GHOSTDAG 50+ block robustness test."""
import subprocess, json, sys

CLI = ["./src/bitcoin-cli", "-regtest"]
DESC = "raw(51)#8lvh9jxk"

def rpc(*args):
    r = subprocess.run(CLI + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        return None
    if not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except:
        return r.stdout.strip()

def mine():
    result = rpc("generateblock", DESC, "[]")
    if result and "hash" in result:
        return result["hash"]
    return None

def header(h):
    return rpc("getblockheader", h)

print("=" * 72)
print("QuantumBTC GHOSTDAG Robustness Test")
print("=" * 72)

# Phase 1: Mine 50 blocks linearly
print("\n[Phase 1] Mining 50 blocks linearly...")
for i in range(1, 51):
    h = mine()
    if not h:
        print(f"  ERROR: Failed to mine block {i}")
        sys.exit(1)
    if i % 10 == 0:
        info = rpc("getblockchaininfo")
        print(f"  Block {i:2d}: height={info['blocks']}  dag_tips={info.get('dag_tips','?')}  hash={h[:20]}...")

info = rpc("getblockchaininfo")
print(f"\n  Phase 1 result: height={info['blocks']}  dagmode={info['dagmode']}  "
      f"ghostdag_k={info['ghostdag_k']}  dag_tips={info.get('dag_tips','?')}")

# Phase 2: Create forks using invalidateblock / generateblock / reconsiderblock
print("\n[Phase 2] Creating 5 parallel forks...")
for fork_id in range(1, 6):
    fork_height = 50 - fork_id * 2
    next_h = fork_height + 1
    
    next_hash = rpc("getblockhash", str(next_h))
    if not next_hash:
        print(f"  Fork {fork_id}: SKIP (can't get hash at h{next_h})")
        continue
    
    # Invalidate the block after fork point
    rpc("invalidateblock", next_hash)
    
    # Check current state
    cur_info = rpc("getblockchaininfo")
    cur_height = cur_info["blocks"] if cur_info else "?"
    
    # Mine 2 fork blocks
    fh1 = mine()
    fh2 = mine()
    
    if fh2:
        hdr = header(fh2)
        bs = hdr.get('blue_score', '?') if hdr else '?'
        dp = len(hdr.get('dagparents', [])) if hdr else 0
        print(f"  Fork {fork_id}: base=h{fork_height}  rewound_to={cur_height}  "
              f"tip={fh2[:16]}...  blue_score={bs}  dagparents={dp}")
    else:
        print(f"  Fork {fork_id}: base=h{fork_height}  mining failed at height={cur_height}")
    
    # Reconsider to restore main chain
    rpc("reconsiderblock", next_hash)

info = rpc("getblockchaininfo")
print(f"\n  After forks: height={info['blocks']}  dag_tips={info.get('dag_tips','?')}")

# Phase 3: Mine 10 more
print("\n[Phase 3] Mining 10 more blocks...")
for i in range(10):
    mine()
info = rpc("getblockchaininfo")
print(f"  After extension: height={info['blocks']}  dag_tips={info.get('dag_tips','?')}")

# Phase 4: Force >18 concurrent forks
print("\n[Phase 4] Creating 22 concurrent forks (K=18 red block test)...")
current_best = rpc("getbestblockhash")
current_height = rpc("getblockchaininfo")["blocks"]

# Invalidate tip
rpc("invalidateblock", current_best)
base_info = rpc("getblockchaininfo")
base_height = base_info["blocks"] if base_info else "?"
print(f"  Base height after invalidation: {base_height}")

fork_hashes = []
for f in range(1, 23):
    h = mine()
    if h:
        fork_hashes.append(h)
        # Invalidate this to go back to base
        rpc("invalidateblock", h)
    if f % 5 == 0:
        print(f"  Created {f}/22 fork blocks...")

print(f"  Total fork blocks created: {len(fork_hashes)}")

# Reconsider all forks + original tip
for h in fork_hashes:
    rpc("reconsiderblock", h)
rpc("reconsiderblock", current_best)

info = rpc("getblockchaininfo")
print(f"  After reconsider: height={info['blocks']}  dag_tips={info.get('dag_tips','?')}")

# Mine merge block
print("  Mining merge block...")
merge_hash = mine()
if merge_hash:
    hdr = header(merge_hash)
    blues = hdr.get('mergeset_blues', [])
    reds = hdr.get('mergeset_reds', [])
    dp = hdr.get('dagparents', [])
    print(f"\n  MERGE BLOCK GHOSTDAG DATA:")
    print(f"    hash:           {merge_hash[:40]}...")
    print(f"    height:         {hdr.get('height','?')}")
    print(f"    blue_score:     {hdr.get('blue_score','?')}")
    print(f"    blue_work:      {hdr.get('blue_work','?')}")
    print(f"    selected_parent:{hdr.get('selected_parent','?')[:40]}...")
    print(f"    dagparents:     {len(dp)}")
    print(f"    mergeset_blues: {len(blues)}")
    print(f"    mergeset_reds:  {len(reds)}")
    if reds:
        print(f"    *** RED BLOCKS DETECTED (anticone > K=18) ***")
        for r in reds[:5]:
            print(f"      red: {r[:40]}...")
    else:
        print(f"    (no red blocks in this merge)")

# Phase 5: Scan all blocks
print("\n[Phase 5] Scanning all blocks for GHOSTDAG data...")
final_info = rpc("getblockchaininfo")
final_height = final_info["blocks"]

total_blues = 0
total_reds = 0
max_reds = 0
max_reds_h = 0
max_parents = 0
max_parents_h = 0
samples = {}

for h in range(1, final_height + 1):
    bh = rpc("getblockhash", str(h))
    if not bh:
        continue
    hdr = header(bh)
    if not hdr:
        continue
    bl = len(hdr.get('mergeset_blues', []))
    rd = len(hdr.get('mergeset_reds', []))
    dp = len(hdr.get('dagparents', []))
    total_blues += bl
    total_reds += rd
    if rd > max_reds:
        max_reds = rd
        max_reds_h = h
    if dp > max_parents:
        max_parents = dp
        max_parents_h = h
    if h in [1, 10, 25, 50, final_height - 1, final_height]:
        samples[h] = hdr

print(f"  Total blocks scanned: {final_height}")
print(f"  Total mergeset_blues: {total_blues}")
print(f"  Total mergeset_reds:  {total_reds}")
print(f"  Max dagparents:       {max_parents} (height {max_parents_h})")
if max_reds > 0:
    print(f"  Max reds in one block:{max_reds} (height {max_reds_h})")
else:
    print(f"  No red blocks found")

print(f"\n  Sample headers:")
print(f"  {'h':>4}  {'blue_score':>10}  {'blue_work':>10}  {'parents':>7}  {'blues':>5}  {'reds':>4}")
print(f"  {'----':>4}  {'----------':>10}  {'----------':>10}  {'-------':>7}  {'-----':>5}  {'----':>4}")
for h in sorted(samples.keys()):
    hdr = samples[h]
    print(f"  {h:4d}  {hdr.get('blue_score','?'):>10}  {hdr.get('blue_work','?'):>10}  "
          f"{len(hdr.get('dagparents',[])):>7}  {len(hdr.get('mergeset_blues',[])):>5}  "
          f"{len(hdr.get('mergeset_reds',[])):>4}")

# Phase 6: Final output
print("\n" + "=" * 72)
print("[Final] getblockchaininfo:")
print("=" * 72)
info = rpc("getblockchaininfo")
print(json.dumps(info, indent=2))

print("\n" + "=" * 72)
print("[Final] Best block header:")
print("=" * 72)
best = rpc("getbestblockhash")
print(json.dumps(header(best), indent=2))

print("\n" + "=" * 72)
print("[Final] getmininginfo:")
print("=" * 72)
mi = rpc("getmininginfo")
print(json.dumps(mi, indent=2))

print("\n" + "=" * 72)
print("GHOSTDAG ROBUSTNESS TEST COMPLETE")
print("=" * 72)
