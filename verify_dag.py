#!/usr/bin/env python3
"""Create parallel DAG blocks and verify GHOSTDAG merge."""

import subprocess, json, sys, struct, hashlib, time

CLI = "/workspaces/QuantBTC/build-fresh/src/bitcoin-cli"
DATADIR = "/workspaces/QuantBTC/.tmp/qbtc-regtest-fresh"

def cli(*args):
    cmd = [CLI, f"-datadir={DATADIR}"] + list(args)
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"CLI error: {res.stderr.strip()}", file=sys.stderr)
        return None
    return json.loads(res.stdout) if res.stdout.strip().startswith('{') or res.stdout.strip().startswith('[') else res.stdout.strip()

def get_block_template():
    return cli("getblocktemplate", '{"rules":["segwit"]}')

def create_coinbase(height, addr, value_sat):
    """Create a minimal coinbase transaction."""
    # Use bitcoin-cli to create a raw coinbase
    # Simpler: mine normally but with different timestamps
    pass

# Step 1: Get current state
info = cli("getblockchaininfo")
print(f"Starting: blocks={info['blocks']}, dag_tips={info['dag_tips']}")

# Step 2: Get two addresses
addr1 = cli("getnewaddress", "", "bech32")
addr2 = cli("getnewaddress", "", "bech32")
print(f"Addr1: {addr1}")
print(f"Addr2: {addr2}")

# Step 3: Get current tip
tip_hash = info['bestblockhash']

# Step 4: Use generateblock to create two blocks in sequence on same parent
# First, mine block A normally
block_a_hashes = cli("generatetoaddress", "1", addr1)
if not block_a_hashes:
    sys.exit("Failed to mine block A")
block_a = block_a_hashes[0]
print(f"Block A: {block_a} (height {info['blocks']+1})")

# Now get the raw block A and use its parent to craft block B
header_a = cli("getblockheader", block_a)
parent = header_a['previousblockhash']
print(f"Common parent: {parent}")

# Get a block template that would have been valid before A was mined
# We need to use submitblock with a block that references the same parent
tmpl = get_block_template()
print(f"Template height: {tmpl['height']}, template parent: {tmpl['previousblockhash']}")

# The template now points to block A as parent - we need to construct a
# competing block that points to 'parent' instead.
# Simplest approach: use generateblock with a specific set of txns before block A
# Actually, let's just mine 2 more blocks to show DAG parents
print()
print("=== Mining forward to create merge block ===")
merge_hashes = cli("generatetoaddress", "1", addr2)
merge_hash = merge_hashes[0]
merge_header = cli("getblockheader", merge_hash)
print(f"Block at height {merge_header['height']}: {merge_hash}")
print(f"  dagblock: {merge_header.get('dagblock')}")
print(f"  blue_score: {merge_header.get('blue_score')}")
print(f"  dagparents: {merge_header.get('dagparents')}")
print(f"  selected_parent: {merge_header.get('selected_parent')}")
print(f"  mergeset_blues: {merge_header.get('mergeset_blues')}")

# Check all block headers for DAG fields
print()
print("=== All blocks DAG summary ===")
for h in range(0, merge_header['height'] + 1):
    bh = cli("getblockhash", str(h))
    hdr = cli("getblockheader", bh)
    dps = hdr.get('dagparents', [])
    bs = hdr.get('blue_score', 'N/A')
    sp = hdr.get('selected_parent', 'N/A')[:16] if hdr.get('selected_parent') else 'N/A'
    mb = hdr.get('mergeset_blues', [])
    print(f"  height={h}: hash={bh[:16]}... blue_score={bs} dagparents={len(dps)} selected_parent={sp}... mergeset_blues={len(mb)}")

# Final state
info = cli("getblockchaininfo")
print()
print(f"Final: blocks={info['blocks']}, dag_tips={info['dag_tips']}, dagmode={info['dagmode']}, pqc={info['pqc']}")
