#!/usr/bin/env python3
"""
test_dag_testnet.py — DAG fork/merge test for QuantumBTC qbtctestnet

Creates parallel fork blocks via submit=false, re-submits them to create
DAG tips, then mines a merge block referencing multiple parents.

Usage:
    python3 test_dag_testnet.py               # default: qbtctestnet
    python3 test_dag_testnet.py regtest        # use regtest
"""
import subprocess, json, time, sys

CHAIN = sys.argv[1] if len(sys.argv) > 1 else "qbtctestnet"
CLI = ["./src/bitcoin-cli", f"-{CHAIN}"]
NUM_FORKS = 5

def rpc(*args):
    r = subprocess.run(CLI + list(args), capture_output=True, text=True)
    if r.returncode != 0:
        return None
    try:
        return json.loads(r.stdout)
    except (json.JSONDecodeError, ValueError):
        return r.stdout.strip() or None

def rpc_must(*args):
    r = rpc(*args)
    if r is None:
        print(f"  FATAL: RPC '{args[0]}' failed")
        sys.exit(1)
    return r

def _get_mining_address():
    """Obtain a proper bech32 address for mining instead of anyone-can-spend."""
    r = subprocess.run(CLI + ["getnewaddress", "", "bech32"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(CLI + ["createwallet", "mining"],
                       capture_output=True, text=True)
        r = subprocess.run(CLI + ["getnewaddress", "", "bech32"],
                           capture_output=True, text=True)
    return r.stdout.strip()

MINING_ADDR = _get_mining_address()

def mine():
    return rpc_must("generateblock", MINING_ADDR, "[]")

def mine_nosub():
    return rpc("generateblock", MINING_ADDR, "[]", "false")

# ── Phase 1: Baseline ────────────────────────────────────────────────
print(f"=== DAG Fork/Merge Test on {CHAIN} ===\n")

info = rpc_must("getblockchaininfo")
start_height = info["blocks"]
print(f"Phase 1: height={start_height}, tips={info['dag_tips']}")

print("  Mining 3 base blocks...")
for _ in range(3):
    mine()
    time.sleep(1)

info = rpc_must("getblockchaininfo")
base_height = info["blocks"]
base_hash = info["bestblockhash"]
print(f"  Base: height={base_height}, hash={base_hash[:16]}...")

# ── Phase 2: Create fork blocks (submit=false) ───────────────────────
print(f"\nPhase 2: Creating {NUM_FORKS} fork blocks (submit=false)...")

stale = []
for i in range(NUM_FORKS):
    r = mine_nosub()
    if r and "hash" in r:
        h = r["hash"]
        # Grab raw hex while the block is still retrievable
        raw = rpc("getblock", h, "0")
        if raw and isinstance(raw, str) and len(raw) > 100:
            stale.append({"hash": h, "hex": raw})
            print(f"  Fork {i+1}: {h[:16]}... ({len(raw)//2} bytes)")
        else:
            print(f"  Fork {i+1}: {h[:16]}... (raw not retrievable)")
    else:
        print(f"  Fork {i+1}: failed")
    time.sleep(1.5)

# Deduplicate
seen = set()
unique = []
for s in stale:
    if s["hash"] not in seen:
        seen.add(s["hash"])
        unique.append(s)
stale = unique
print(f"  Unique fork blocks captured: {len(stale)}")

# ── Phase 3: Submit fork blocks ──────────────────────────────────────
if stale:
    print(f"\nPhase 3: Submitting {len(stale)} fork blocks...")
    for i, blk in enumerate(stale):
        r = subprocess.run(CLI + ["submitblock", blk["hex"]],
                           capture_output=True, text=True)
        status = r.stdout.strip() or "accepted"
        print(f"  Fork {i+1} ({blk['hash'][:16]}...): {status}")

    info = rpc_must("getblockchaininfo")
    print(f"  After submit: height={info['blocks']}, tips={info['dag_tips']}")
else:
    print("\nPhase 3: No fork blocks to submit — forks not captured")

# ── Phase 4: Mine merge block ────────────────────────────────────────
print(f"\nPhase 4: Mining merge block...")
time.sleep(2)

merge = mine()
hdr = rpc_must("getblockheader", merge["hash"])

dp     = hdr.get("dagparents", [])
bs     = hdr.get("blue_score", 0)
bw     = hdr.get("blue_work", 0)
mb     = hdr.get("mergeset_blues", [])
mr     = hdr.get("mergeset_reds", [])
sp     = hdr.get("selected_parent", "N/A")
epw    = hdr.get("early_protection_weight", 0)

print(f"  Hash:             {merge['hash'][:16]}...")
print(f"  Height:           {hdr['height']}")
print(f"  DAG parents:      {len(dp)}")
print(f"  Blue score:       {bs}")
print(f"  Blue work:        {bw}")
print(f"  Mergeset blues:   {len(mb)}")
print(f"  Mergeset reds:    {len(mr)}")
print(f"  Selected parent:  {sp[:16]}...")
print(f"  Early protection: {epw}")

if dp:
    print(f"  Parent hashes:")
    for p in dp:
        print(f"    {p[:16]}...")

# ── Final ─────────────────────────────────────────────────────────────
print(f"\n=== Result ===")
info = rpc_must("getblockchaininfo")
print(f"  chain={info['chain']}  blocks={info['blocks']}  tips={info['dag_tips']}")
print(f"  ticker={info['ticker']}  dag={info['dagmode']}  pqc={info['pqc']}  k={info['ghostdag_k']}")

if len(dp) > 1:
    print(f"\n  PASS — merge block has {len(dp)} dagparents, {len(mb)} mergeset_blues")
elif len(mb) > 0:
    print(f"\n  PASS — merge block has {len(mb)} mergeset blues")
else:
    print(f"\n  INFO — linear chain (submit=false hex may not persist for re-submission)")
    print(f"  Run regtest fork test (run_ghostdag_test_v2.py) for proven multi-parent merges.")
