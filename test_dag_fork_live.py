#!/usr/bin/env python3
"""DAG fork/merge test on qbtctestnet using generateblock + submitblock.
This is the proven approach from the regtest test."""
import subprocess, json, time, sys

CLI = ["./src/bitcoin-cli", "-qbtctestnet"]
DESC = "raw(51)#8lvh9jxk"  # OP_TRUE descriptor

def rpc(cmd, *args):
    r = subprocess.run(CLI + [cmd] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  RPC {cmd} failed: {r.stderr.strip()}")
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout.strip()

def mine_raw(n=1):
    """Mine n blocks using generateblock (raw descriptor, no wallet needed)."""
    hashes = []
    for _ in range(n):
        result = rpc("generateblock", DESC, "[]")
        if result and "hash" in result:
            hashes.append(result["hash"])
    return hashes

# --- Step 1: Record base state ---
info = rpc("getblockchaininfo")
base_height = info["blocks"]
base_hash = info["bestblockhash"]
print(f"Base: height={base_height} hash={base_hash[:16]}...")

# Mine one block to establish a fork point
mine_raw(1)
info = rpc("getblockchaininfo")
fork_point = info["bestblockhash"]
fork_height = info["blocks"]
print(f"Fork point: height={fork_height} hash={fork_point[:16]}...")

# --- Step 2: Create fork blocks ---
NUM_FORKS = 20
fork_tip_hashes = []

print(f"\nCreating {NUM_FORKS} fork branches from height {fork_height}...")

for i in range(NUM_FORKS):
    # Invalidate current tip to go back to fork point
    cur = rpc("getblockchaininfo")
    cur_tip = cur["bestblockhash"]
    
    if cur_tip != fork_point:
        rpc("invalidateblock", cur_tip)
        time.sleep(0.2)
    
    # Verify we're at the fork point
    cur2 = rpc("getblockchaininfo")
    if cur2["bestblockhash"] != fork_point:
        print(f"  Fork {i:2d}: NOT at fork point (at {cur2['bestblockhash'][:16]}), skipping")
        if cur_tip != fork_point:
            rpc("reconsiderblock", cur_tip)
        continue
    
    # Mine a new block using generateblock
    result = rpc("generateblock", DESC, "[]")
    if result and "hash" in result:
        new_hash = result["hash"]
        fork_tip_hashes.append(new_hash)
        print(f"  Fork {i:2d}: {new_hash[:16]}...")
    else:
        print(f"  Fork {i:2d}: FAILED to mine")
    
    time.sleep(0.1)

# Reconsider ALL invalidated blocks
print(f"\nReconsider all {len(fork_tip_hashes)} fork tips...")
for h in fork_tip_hashes:
    rpc("reconsiderblock", h)
    time.sleep(0.1)

time.sleep(1)

# --- Step 3: Check state after forks ---
info = rpc("getblockchaininfo")
print(f"\nAfter forks: height={info['blocks']} dag_tips={info['dag_tips']}")

# --- Step 4: Mine merge block ---
print("\nMining merge block...")
result = rpc("generateblock", DESC, "[]")
if result and "hash" in result:
    merge_hash = result["hash"]
    print(f"Merge block: {merge_hash[:16]}...")
    
    hdr = rpc("getblockheader", merge_hash)
    if hdr:
        dp = hdr.get('dagparents', hdr.get('num_dag_parents', 0))
        print(f"\n=== MERGE BLOCK HEADER ===")
        print(f"  height:         {hdr.get('height')}")
        print(f"  dagparents:     {dp}")
        print(f"  blue_score:     {hdr.get('blue_score', 'N/A')}")
        print(f"  blue_work:      {hdr.get('blue_work', 'N/A')}")
        print(f"  mergeset_blues: {hdr.get('mergeset_blues', 'N/A')}")
        print(f"  mergeset_reds:  {hdr.get('mergeset_reds', 'N/A')}")
        
        if 'dagparenthashes' in hdr:
            print(f"\n  DAG parent hashes ({len(hdr['dagparenthashes'])}):")
            for ph in hdr['dagparenthashes']:
                print(f"    {ph}")
else:
    print("Failed to mine merge block!")

# --- Step 5: Stabilize ---
mine_raw(3)

# --- Step 6: Final state ---
info = rpc("getblockchaininfo")
print(f"\n=== FINAL STATE ===")
print(f"  chain:      {info['chain']}")
print(f"  blocks:     {info['blocks']}")
print(f"  dagmode:    {info['dagmode']}")
print(f"  dag_tips:   {info['dag_tips']}")
print(f"  warnings:   {info.get('warnings', [])}")

best_hdr = rpc("getblockheader", info["bestblockhash"])
if best_hdr:
    print(f"  best blue_score: {best_hdr.get('blue_score', 'N/A')}")

print(f"\nTest complete.")
