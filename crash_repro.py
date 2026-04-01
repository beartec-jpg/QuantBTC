#!/usr/bin/env python3
"""Minimal crash reproducer: 10 linear blocks then 10 concurrent forks."""
import subprocess, json, time, sys

CLI = ["./src/bitcoin-cli", "-regtest"]
DESC = "raw(51)#8lvh9jxk"

def rpc(*args):
    r = subprocess.run(CLI + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except:
        return r.stdout.strip()

def mine():
    result = rpc("generateblock", DESC, "[]")
    return result["hash"] if result and "hash" in result else None

def mine_nosub():
    result = rpc("generateblock", DESC, "[]", "false")
    if result and "hash" in result:
        return result["hash"], result["hex"]
    return None, None

# Phase 1: Mine 10 linear blocks
print("Mining 10 linear blocks...")
for i in range(10):
    h = mine()
    if not h:
        print(f"  FAILED at block {i+1}")
        sys.exit(1)
print(f"  Done. Height={rpc('getblockcount')}")

# Phase 2: Generate 10 concurrent fork templates
print("Generating 10 fork templates (with 1s sleep each)...")
forks = []
for i in range(10):
    fh, fx = mine_nosub()
    if fh and fx:
        forks.append((i+1, fh, fx))
    time.sleep(1)
    if (i+1) % 5 == 0:
        print(f"  {i+1}/10 templates ready")

# Advance main chain
time.sleep(1)
main = mine()
print(f"Main chain advanced: {main[:16] if main else 'FAIL'}...")

# Submit all forks
print(f"Submitting {len(forks)} fork blocks...")
for i, (n, fh, fx) in enumerate(forks):
    result = rpc("submitblock", fx)
    status = "OK" if result is None or result == "" else result
    print(f"  Fork {n}: {status}")

    # Check if node is still alive
    alive = rpc("getblockcount")
    if alive is None:
        print(f"  *** NODE CRASHED after fork {n} ***")
        sys.exit(1)

print(f"\nFinal height: {rpc('getblockcount')}")
d = rpc("getblockchaininfo")
if d:
    print(f"dag_tips: {d.get('dag_tips','?')}")
print("Node survived!")
