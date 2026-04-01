#!/usr/bin/env python3
"""
DAG fork/merge test on qbtctestnet using generateblock(submit=false) + submitblock.
Adapted from the proven regtest test (run_ghostdag_test_v2.py).
"""
import subprocess, json, sys, time

CLI = ["./src/bitcoin-cli", "-qbtctestnet"]
DESC = "raw(51)#8lvh9jxk"

def rpc(*args):
    r = subprocess.run(CLI + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"  ERR {' '.join(args[:2])}: {r.stderr.strip()}")
        return None
    if not r.stdout.strip():
        return None
    try:
        return json.loads(r.stdout)
    except:
        return r.stdout.strip()

def mine():
    result = rpc("generateblock", DESC, "[]")
    return result["hash"] if result and "hash" in result else None

def mine_nosub():
    """Create a block without submitting. Returns (hash, hex)."""
    result = rpc("generateblock", DESC, "[]", "false")
    if result and "hash" in result:
        return result["hash"], result["hex"]
    return None, None

def submit(hex_data):
    return rpc("submitblock", hex_data)

# --- Step 1: Base chain ---
info = rpc("getblockchaininfo")
base_height = info["blocks"]
print(f"Base: height={base_height}")

# Mine a few blocks to ensure solid base
for _ in range(3):
    mine()
info = rpc("getblockchaininfo")
fork_height = info["blocks"]
fork_hash = info["bestblockhash"]
print(f"Fork point: height={fork_height} hash={fork_hash[:16]}...")

# --- Step 2: Create fork blocks using submit=false ---
NUM_FORKS = 22
fork_blocks = []  # list of (hash, hex)

print(f"\nCreating {NUM_FORKS} fork blocks (submit=false, with 1s delays)...")
for i in range(NUM_FORKS):
    time.sleep(1.1)  # Must differ timestamps to avoid "duplicate" rejection
    h, hx = mine_nosub()
    if h and hx:
        fork_blocks.append((h, hx))
        print(f"  Fork {i:2d}: {h[:16]}... ({len(hx)} hex bytes)")
    else:
        print(f"  Fork {i:2d}: FAILED")

print(f"\nCreated {len(fork_blocks)} fork blocks")

# --- Step 3: Submit all fork blocks ---
print(f"\nSubmitting {len(fork_blocks)} fork blocks...")
accepted = 0
for i, (h, hx) in enumerate(fork_blocks):
    result = submit(hx)
    status = "OK" if result is None or result == "None" else result
    if status in ("OK", "None", None, "inconclusive"):
        accepted += 1
    print(f"  Submit {i:2d}: {h[:16]}... -> {status}")

print(f"\nAccepted: {accepted}/{len(fork_blocks)}")

time.sleep(1)

# --- Step 4: Check state ---
info = rpc("getblockchaininfo")
print(f"\nAfter submissions: height={info['blocks']} dag_tips={info['dag_tips']}")

# --- Step 5: Mine merge block ---
print("\nMining merge block...")
merge_hash = mine()
if merge_hash:
    hdr = rpc("getblockheader", merge_hash)
    if hdr:
        dp = hdr.get('dagparents', 0)
        if isinstance(dp, list):
            dp = len(dp)
        print(f"\n{'='*50}")
        print(f"  MERGE BLOCK")
        print(f"{'='*50}")
        print(f"  hash:           {merge_hash}")
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

# --- Step 6: Stabilize and final state ---
mine()
mine()
info = rpc("getblockchaininfo")
best_hdr = rpc("getblockheader", info["bestblockhash"])
print(f"\n{'='*50}")
print(f"  FINAL STATE")
print(f"{'='*50}")
print(f"  chain:           {info['chain']}")
print(f"  blocks:          {info['blocks']}")
print(f"  dagmode:         {info['dagmode']}")
print(f"  dag_tips:        {info['dag_tips']}")
print(f"  best blue_score: {best_hdr.get('blue_score', 'N/A')}")
print(f"  warnings:        {info.get('warnings', [])}")
print(f"\nTest complete.")
