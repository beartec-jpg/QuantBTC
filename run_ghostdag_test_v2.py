#!/usr/bin/env python3
"""
QuantumBTC GHOSTDAG Robustness Test v2
Uses generateblock(submit=false) + submitblock to create real DAG forks.
Key insight: must sleep(1) between template generation so timestamps differ,
otherwise identical inputs produce identical blocks ("duplicate" rejection).
"""
import subprocess, json, sys, time, os

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
    """Mine and submit a block, return hash."""
    result = rpc("generateblock", DESC, "[]")
    return result["hash"] if result and "hash" in result else None

def mine_nosub():
    """Create a block but don't submit. Returns (hash, hex)."""
    result = rpc("generateblock", DESC, "[]", "false")
    if result and "hash" in result:
        return result["hash"], result["hex"]
    return None, None

def submit(hex_data):
    """Submit a previously generated block."""
    return rpc("submitblock", hex_data)

def header(h):
    return rpc("getblockheader", h)

def info():
    return rpc("getblockchaininfo")

print("=" * 72)
print("QuantumBTC GHOSTDAG Robustness Test v2")
print("=" * 72)

# ================================================================
# Phase 1: Mine 50 blocks linearly
# ================================================================
print("\n[Phase 1] Mining 50 blocks linearly...")
for i in range(1, 51):
    h = mine()
    if not h:
        print(f"  ERROR: Failed to mine block {i}")
        sys.exit(1)
    if i % 10 == 0:
        d = info()
        print(f"  Block {i:2d}: height={d['blocks']}  dag_tips={d.get('dag_tips','?')}")

d = info()
print(f"\n  Result: height={d['blocks']}  dagmode={d['dagmode']}  "
      f"ghostdag_k={d['ghostdag_k']}  dag_tips={d.get('dag_tips','?')}")

# ================================================================
# Phase 2: Create 5 forks using generate(submit=false)
# Strategy: generate a stale block (don't submit), sleep 1s so
# the next block has a different timestamp, mine on main chain,
# repeat. Then submit all stale blocks → they become DAG forks.
# ================================================================
print("\n[Phase 2] Creating 5 DAG forks with stale block submission...")
stale_blocks = []

for fork_id in range(1, 6):
    # Generate a block but DON'T submit it
    fork_hash, fork_hex = mine_nosub()
    if fork_hash and fork_hex:
        stale_blocks.append((fork_id, fork_hash, fork_hex))
        # Sleep so the next block gets a different timestamp
        time.sleep(1)
        # Mine a block on the main chain (this advances the tip)
        main_hash = mine()
        print(f"  Fork {fork_id}: stale={fork_hash[:16]}...  main={main_hash[:16]}...")
    else:
        print(f"  Fork {fork_id}: FAILED to generate template")

# Now submit all stale blocks - they should be accepted as DAG blocks
print(f"\n  Submitting {len(stale_blocks)} stale fork blocks...")
for fork_id, fork_hash, fork_hex in stale_blocks:
    result = submit(fork_hex)
    if result is None or result == "":
        hdr = header(fork_hash)
        bs = hdr.get('blue_score', '?') if hdr else '?'
        dp = len(hdr.get('dagparents', [])) if hdr else 0
        bl = len(hdr.get('mergeset_blues', [])) if hdr else 0
        rd = len(hdr.get('mergeset_reds', [])) if hdr else 0
        print(f"    Fork {fork_id} ACCEPTED: hash={fork_hash[:16]}...  blue_score={bs}  "
              f"dagparents={dp}  blues={bl}  reds={rd}")
    else:
        print(f"    Fork {fork_id} REJECTED: {result}")

d = info()
print(f"\n  After forks: height={d['blocks']}  dag_tips={d.get('dag_tips','?')}")

# ================================================================
# Phase 3: Mine 5 merge blocks to absorb the forks
# ================================================================
print("\n[Phase 3] Mining 5 merge blocks...")
for i in range(5):
    merge = mine()
    if merge:
        hdr = header(merge)
        dp = len(hdr.get('dagparents', []))
        bl = len(hdr.get('mergeset_blues', []))
        rd = len(hdr.get('mergeset_reds', []))
        print(f"  Merge {i+1}: hash={merge[:16]}...  dagparents={dp}  blues={bl}  reds={rd}")

d = info()
print(f"\n  After merges: height={d['blocks']}  dag_tips={d.get('dag_tips','?')}")

# ================================================================
# Phase 4: Create >18 concurrent forks (K=18 red block test)
# Generate 22 competing blocks from the same tip, with sleep(1)
# between each so they have different timestamps / different hashes.
# Then mine one main block and submit all 22 stale blocks.
# ================================================================
print("\n[Phase 4] Creating 22 concurrent forks from same tip (K=18 red block test)...")
print(f"  GHOSTDAG K=18: blocks with anticone > 18 should be marked RED")
print(f"  NOTE: generating 22 templates with 1s delay each (~22s)...")

concurrent = []
for f in range(1, 23):
    fh, fx = mine_nosub()
    if fh and fx:
        concurrent.append((f, fh, fx))
    else:
        print(f"  WARNING: fork {f} generation failed")
    if f < 22:
        time.sleep(1)  # ensure different timestamp → different block
    if f % 5 == 0:
        print(f"  Prepared {f}/22 fork templates...")

# Sleep before mining main block too
time.sleep(1)
# Mine ONE main block (so the 22 templates become stale)
main_block = mine()
print(f"  Main chain advanced: {main_block[:16]}...")

# Submit all 22 concurrent stale blocks
print(f"  Submitting {len(concurrent)} concurrent stale blocks...")
accepted = 0
rejected = 0
for f, fh, fx in concurrent:
    result = submit(fx)
    if result is None or result == "":
        accepted += 1
    else:
        rejected += 1
        if accepted + rejected <= 3 or result != "duplicate":
            print(f"    Fork {f} REJECTED: {result}")

print(f"  Accepted: {accepted}  Rejected: {rejected}")

d = info()
print(f"  After concurrent forks: height={d['blocks']}  dag_tips={d.get('dag_tips','?')}")

# Mine a merge block to absorb all
print("  Mining merge block to absorb all forks...")
merge = mine()
if merge:
    hdr = header(merge)
    dp = hdr.get('dagparents', [])
    bl = hdr.get('mergeset_blues', [])
    rd = hdr.get('mergeset_reds', [])
    print(f"\n  MERGE BLOCK GHOSTDAG DATA:")
    print(f"    hash:            {merge[:40]}...")
    print(f"    height:          {hdr.get('height','?')}")
    print(f"    blue_score:      {hdr.get('blue_score','?')}")
    print(f"    blue_work:       {hdr.get('blue_work','?')}")
    print(f"    selected_parent: {hdr.get('selected_parent','?')[:40]}...")
    print(f"    dagparents:      {len(dp)}")
    print(f"    mergeset_blues:  {len(bl)}")
    print(f"    mergeset_reds:   {len(rd)}")
    if rd:
        print(f"    *** RED BLOCKS DETECTED (anticone > K=18) ***")
        for r in rd[:5]:
            print(f"      red: {r[:40]}...")
    else:
        print(f"    (no red blocks in this merge)")

# ================================================================
# Phase 5: Scan all blocks
# ================================================================
print("\n[Phase 5] Scanning all blocks for GHOSTDAG data...")
d = info()
final_height = d["blocks"]

total_blues = 0
total_reds = 0
max_reds = 0
max_reds_h = 0
max_parents = 0
max_parents_h = 0
samples = {}

for h in range(1, final_height + 1):
    bh = rpc("getblockhash", str(h))
    if not bh: continue
    hdr = header(bh)
    if not hdr: continue
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
    if h in [1, 10, 25, 50, 55, 60, final_height-1, final_height]:
        samples[h] = hdr

print(f"  Total blocks scanned:    {final_height}")
print(f"  Total mergeset_blues:    {total_blues}")
print(f"  Total mergeset_reds:     {total_reds}")
print(f"  Max dagparents:          {max_parents} (height {max_parents_h})")
if max_reds > 0:
    print(f"  Max reds in one block:   {max_reds} (height {max_reds_h})")
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

# ================================================================
# Phase 6: Final output
# ================================================================
print("\n" + "=" * 72)
print("[Final] getblockchaininfo:")
print("=" * 72)
print(json.dumps(info(), indent=2))

print("\n" + "=" * 72)
print("[Final] Best block header:")
print("=" * 72)
best = rpc("getbestblockhash")
print(json.dumps(header(best), indent=2))

print("\n" + "=" * 72)
print("[Final] getmininginfo:")
print("=" * 72)
print(json.dumps(rpc("getmininginfo"), indent=2))

# Check GHOSTDAG log entries
print("\n" + "=" * 72)
print("[Bonus] Last 10 GHOSTDAG log entries:")
print("=" * 72)
logfile = os.path.expanduser("~/.bitcoin/regtest/debug.log")
with open(logfile) as f:
    lines = [l.strip() for l in f if "GHOSTDAG" in l]
for l in lines[-10:]:
    # Trim timestamp for readability
    print(f"  {l[22:]}")

print("\n" + "=" * 72)
print("GHOSTDAG ROBUSTNESS TEST COMPLETE")
print("=" * 72)
