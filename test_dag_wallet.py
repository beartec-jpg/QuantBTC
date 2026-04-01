#!/usr/bin/env python3
"""DAG fork/merge test on qbtctestnet with wallet (generatetoaddress)."""
import subprocess, json, time, sys

CLI = ["./src/bitcoin-cli", "-qbtctestnet"]

def rpc(cmd, *args):
    r = subprocess.run(CLI + [cmd] + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  RPC {cmd} failed: {r.stderr.strip()}")
        return None
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return r.stdout.strip()

def mine(n=1):
    addr = rpc("getnewaddress")
    return rpc("generatetoaddress", str(n), addr)

# --- Step 1: Record base state ---
info = rpc("getblockchaininfo")
base_height = info["blocks"]
base_hash = info["bestblockhash"]
print(f"Base: height={base_height} hash={base_hash[:16]}...")

# --- Step 2: Create fork blocks via invalidate/mine/reconsider ---
NUM_FORKS = 20
fork_hashes = []
tip_hash = base_hash

print(f"\nCreating {NUM_FORKS} fork blocks at height {base_height + 1}...")

for i in range(NUM_FORKS):
    # Mine one block to get a tip
    if i == 0:
        hashes = mine(1)
        if not hashes:
            print("  Failed to mine initial block"); sys.exit(1)
        tip_hash = hashes[0]
        fork_hashes.append(tip_hash)
        print(f"  Fork  0: {tip_hash[:16]}... (initial tip)")
    else:
        # Invalidate the current tip to roll back to base
        rpc("invalidateblock", tip_hash)
        time.sleep(0.3)
        
        # Mine a new competing block at the same height
        hashes = mine(1)
        if not hashes:
            print(f"  Fork {i:2d}: FAILED to mine")
            # Reconsider the invalidated block
            rpc("reconsiderblock", tip_hash)
            continue
        
        new_hash = hashes[0]
        fork_hashes.append(new_hash)
        print(f"  Fork {i:2d}: {new_hash[:16]}...")
        
        # Reconsider the previously invalidated tip
        rpc("reconsiderblock", tip_hash)
        time.sleep(0.3)
        
        # Update tip_hash to the new block for next iteration
        tip_hash = new_hash

print(f"\nCreated {len(fork_hashes)} fork blocks")

# --- Step 3: Check current state ---
info = rpc("getblockchaininfo")
print(f"After forks: height={info['blocks']} dag_tips={info['dag_tips']}")

# --- Step 4: Mine a merge block ---
print("\nMining merge block...")
merge_hashes = mine(1)
if merge_hashes:
    merge_hash = merge_hashes[0]
    print(f"Merge block: {merge_hash[:16]}...")
    
    # Get merge block header
    hdr = rpc("getblockheader", merge_hash)
    if hdr:
        print(f"\n=== MERGE BLOCK HEADER ===")
        print(f"  height:         {hdr.get('height')}")
        print(f"  dagparents:     {hdr.get('dagparents', 0)}")
        print(f"  blue_score:     {hdr.get('blue_score', 'N/A')}")
        print(f"  blue_work:      {hdr.get('blue_work', 'N/A')}")
        print(f"  mergeset_blues: {hdr.get('mergeset_blues', 'N/A')}")
        print(f"  mergeset_reds:  {hdr.get('mergeset_reds', 'N/A')}")
        
        # Show DAG parent hashes
        if 'dagparenthashes' in hdr:
            print(f"\n  DAG parent hashes ({len(hdr['dagparenthashes'])}):")
            for ph in hdr['dagparenthashes']:
                print(f"    {ph}")
else:
    print("Failed to mine merge block!")

# --- Step 5: Mine a few more to stabilize ---
mine(5)

# --- Step 6: Final state ---
info = rpc("getblockchaininfo")
print(f"\n=== FINAL STATE ===")
print(f"  chain:      {info['chain']}")
print(f"  blocks:     {info['blocks']}")
print(f"  dagmode:    {info['dagmode']}")
print(f"  dag_tips:   {info['dag_tips']}")
print(f"  warnings:   {info.get('warnings', [])}")

best = rpc("getblockheader", info["bestblockhash"])
print(f"  best block blue_score: {best.get('blue_score', 'N/A')}")
print(f"\nTest complete.")
