#!/usr/bin/env python3
"""Create two parallel blocks on the same parent, submit both, verify DAG merge."""
import subprocess, json, sys, struct, hashlib, binascii, os

CLI = "/workspaces/QuantBTC/build-fresh/src/bitcoin-cli"
DATADIR = "/workspaces/QuantBTC/.tmp/qbtc-regtest-fresh"

def cli(*args):
    cmd = [CLI, f"-datadir={DATADIR}"] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR ({' '.join(args[:2])}): {r.stderr.strip()}", file=sys.stderr)
        return None
    s = r.stdout.strip()
    if s.startswith('{') or s.startswith('['):
        return json.loads(s)
    return s

def le32(v): return struct.pack('<I', v)
def le64(v): return struct.pack('<q', v)

def sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def compact_size(n):
    if n < 0xfd: return bytes([n])
    elif n <= 0xffff: return b'\xfd' + struct.pack('<H', n)
    elif n <= 0xffffffff: return b'\xfe' + struct.pack('<I', n)
    else: return b'\xff' + struct.pack('<Q', n)

def build_coinbase(height, addr_script, value_sat, witness_commitment=None):
    """Build a minimal coinbase transaction."""
    # Version
    tx = le32(1)
    # Marker + Flag for segwit
    tx += b'\x00\x01'
    # Input count
    tx += compact_size(1)
    # Prevout (null)
    tx += b'\x00' * 32 + b'\xff\xff\xff\xff'
    # ScriptSig: height push
    height_bytes = height.to_bytes((height.bit_length() + 7) // 8, 'little') if height > 0 else b'\x00'
    scriptsig = bytes([len(height_bytes)]) + height_bytes
    tx += compact_size(len(scriptsig)) + scriptsig
    # Sequence
    tx += b'\xff\xff\xff\xff'
    
    # Output count
    n_outputs = 1
    if witness_commitment:
        n_outputs = 2
    tx += compact_size(n_outputs)
    
    # Output 0: block reward
    tx += struct.pack('<q', value_sat)
    tx += compact_size(len(addr_script)) + addr_script
    
    # Output 1: witness commitment (if any)
    if witness_commitment:
        commitment_script = bytes.fromhex('6a24aa21a9ed') + witness_commitment
        tx += struct.pack('<q', 0)
        tx += compact_size(len(commitment_script)) + commitment_script
    
    # Witness (segwit coinbase witness)
    tx += compact_size(1)  # 1 witness element
    tx += compact_size(32) + b'\x00' * 32  # 32 zero bytes
    
    # Locktime
    tx += le32(0)
    
    return tx

def build_block(tmpl, coinbase_tx, extra_nonce=0):
    """Build a block from template and coinbase."""
    # Compute coinbase txid (non-witness serialization hash)
    # For non-witness: version + vin + vout + locktime (skip marker+flag and witness)
    cb_hex = coinbase_tx.hex()
    
    # Compute merkle root from just coinbase
    cb_txid = sha256d(coinbase_tx)  # simplified - use witness for proper
    
    # Actually, for merkle root we need the txid (not wtxid)
    # Let's compute non-witness serialization
    # The coinbase has marker+flag at bytes 4-5
    version = coinbase_tx[:4]
    # Skip marker (0x00) and flag (0x01)
    rest = coinbase_tx[6:]
    # Find the witness data - it's before the last 4 bytes (locktime)
    # This is complex; let's just use the full tx hash for now (regtest is permissive)
    
    # For a single-tx block, merkle root = txid of the coinbase
    # We need non-witness hash. Let's rebuild without witness.
    nw_tx = version  # version
    # vin count
    nw_tx += compact_size(1)
    nw_tx += b'\x00' * 32 + b'\xff\xff\xff\xff'  # null prevout
    height = tmpl['height']
    height_bytes = height.to_bytes((height.bit_length() + 7) // 8, 'little') if height > 0 else b'\x00'
    scriptsig = bytes([len(height_bytes)]) + height_bytes + extra_nonce.to_bytes(4, 'little')
    nw_tx += compact_size(len(scriptsig)) + scriptsig
    nw_tx += b'\xff\xff\xff\xff'  # sequence
    # Parse outputs from coinbase_tx... this is getting complex.
    # Let me just use a simpler approach.
    return None

# --- Simpler approach: use the RPC to create block proposals ---

info = cli("getblockchaininfo")
print(f"Starting state: blocks={info['blocks']}, dag_tips={info['dag_tips']}")
parent_hash = info['bestblockhash']

# Mine 1 block to addr1, get the hex, then rollback
addr1 = cli("getnewaddress", "", "bech32")
addr2 = cli("getnewaddress", "", "bech32")

# Get template before mining
tmpl1 = cli("getblocktemplate", '{"rules":["segwit"]}')
print(f"Template parent: {tmpl1['previousblockhash'][:16]}...")
print(f"Template height: {tmpl1['height']}")

# Mine block A
result_a = cli("generatetoaddress", "1", addr1)
block_a_hash = result_a[0]
block_a_hex = cli("getblock", block_a_hash, "0")  # get raw hex
print(f"Block A: {block_a_hash[:16]}... (mined to {addr1})")

# Invalidate block A so we can mine B on the same parent
cli("invalidateblock", block_a_hash)
check = cli("getblockchaininfo")
print(f"After invalidate A: blocks={check['blocks']}")

# Mine block B
result_b = cli("generatetoaddress", "1", addr2)
if result_b is None:
    print("Block B mining failed; trying reconsider first")
    cli("reconsiderblock", block_a_hash)
    sys.exit(1)
    
block_b_hash = result_b[0]
block_b_hex = cli("getblock", block_b_hash, "0")
print(f"Block B: {block_b_hash[:16]}... (mined to {addr2})")

# Now reconsider block A - it should be accepted as a DAG sibling
cli("reconsiderblock", block_a_hash)

check = cli("getblockchaininfo")
print(f"\nAfter reconsider A: blocks={check['blocks']}, dag_tips={check['dag_tips']}")

tips = cli("getchaintips")
print(f"Chain tips: {json.dumps(tips, indent=2)}")

# Now mine a merge block
result_m = cli("generatetoaddress", "1", addr1)
merge_hash = result_m[0]
merge_hdr = cli("getblockheader", merge_hash)
print(f"\n=== MERGE BLOCK ===")
print(f"  hash: {merge_hash}")
print(f"  height: {merge_hdr['height']}")
print(f"  dagparents: {merge_hdr.get('dagparents', [])}")
print(f"  selected_parent: {merge_hdr.get('selected_parent', 'N/A')}")
print(f"  blue_score: {merge_hdr.get('blue_score', 'N/A')}")
print(f"  mergeset_blues: {merge_hdr.get('mergeset_blues', [])}")
print(f"  mergeset_reds: {merge_hdr.get('mergeset_reds', [])}")

final = cli("getblockchaininfo")
print(f"\nFinal state: blocks={final['blocks']}, dag_tips={final['dag_tips']}, dagmode={final['dagmode']}, pqc={final['pqc']}")
