#!/usr/bin/env python3
"""Create two parallel blocks by constructing raw block data with getblocktemplate.
Both blocks reference the same parent, creating a true DAG fork."""

import subprocess, json, sys, struct, hashlib, binascii, time, copy

CLI = "/workspaces/QuantBTC/build-fresh/src/bitcoin-cli"
DATADIR = "/workspaces/QuantBTC/.tmp/qbtc-regtest-fresh"

def cli(*args):
    cmd = [CLI, f"-datadir={DATADIR}"] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR ({args[0]}): {r.stderr.strip()}", file=sys.stderr)
        return None
    s = r.stdout.strip()
    if s.startswith('{') or s.startswith('['):
        return json.loads(s)
    return s

def sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def le32(v): return struct.pack('<I', v)
def le64(v): return struct.pack('<q', v)

def compact_size(n):
    if n < 0xfd: return bytes([n])
    elif n <= 0xffff: return b'\xfd' + struct.pack('<H', n)
    elif n <= 0xffffffff: return b'\xfe' + struct.pack('<I', n)
    else: return b'\xff' + struct.pack('<Q', n)

def hex_to_bytes_le(hex_str):
    """Convert a hex hash string to little-endian bytes."""
    return bytes.fromhex(hex_str)[::-1]

def bytes_to_hex_le(data):
    """Convert little-endian bytes to hex hash string."""
    return data[::-1].hex()

def build_coinbase_tx(height, coinbase_value_sat, coinbase_script_hex, default_witness_commitment_hex, extra_nonce_bytes=b'\x00\x00\x00\x00'):
    """Build a coinbase transaction for the given height."""
    # Height encoding for scriptSig
    if height == 0:
        height_push = b'\x01\x00'
    elif height <= 16:
        height_push = bytes([0x50 + height])
    else:
        height_bytes = height.to_bytes((height.bit_length() + 7) // 8, 'little')
        height_push = bytes([len(height_bytes)]) + height_bytes
    
    scriptsig = height_push + extra_nonce_bytes
    
    # Parse output script
    coinbase_script = bytes.fromhex(coinbase_script_hex)
    
    # Non-witness transaction for txid computation
    nw = b''
    nw += le32(1)  # version
    nw += compact_size(1)  # 1 input
    nw += b'\x00' * 32 + b'\xff\xff\xff\xff'  # null prevout
    nw += compact_size(len(scriptsig)) + scriptsig
    nw += b'\xff\xff\xff\xff'  # sequence
    
    # Outputs
    has_commitment = default_witness_commitment_hex and len(default_witness_commitment_hex) > 0
    n_outputs = 2 if has_commitment else 1
    nw += compact_size(n_outputs)
    
    # Output 0: coinbase value
    nw += le64(coinbase_value_sat)
    nw += compact_size(len(coinbase_script)) + coinbase_script
    
    # Output 1: witness commitment
    if has_commitment:
        commit_script = bytes.fromhex(default_witness_commitment_hex)
        nw += le64(0)
        nw += compact_size(len(commit_script)) + commit_script
    
    nw += le32(0)  # locktime
    
    txid = sha256d(nw)
    
    # Witness transaction (full, for block serialization)
    wt = b''
    wt += le32(1)  # version
    wt += b'\x00\x01'  # marker + flag
    wt += compact_size(1)  # 1 input
    wt += b'\x00' * 32 + b'\xff\xff\xff\xff'  # null prevout
    wt += compact_size(len(scriptsig)) + scriptsig
    wt += b'\xff\xff\xff\xff'  # sequence
    wt += compact_size(n_outputs)
    wt += le64(coinbase_value_sat)
    wt += compact_size(len(coinbase_script)) + coinbase_script
    if has_commitment:
        commit_script = bytes.fromhex(default_witness_commitment_hex)
        wt += le64(0)
        wt += compact_size(len(commit_script)) + commit_script
    # Witness
    wt += compact_size(1)  # 1 witness element for coinbase
    wt += compact_size(32) + b'\x00' * 32  # 32 zero bytes
    wt += le32(0)  # locktime
    
    return wt, txid

def build_block(tmpl, extra_nonce_bytes):
    """Build a complete block from a getblocktemplate result."""
    version = tmpl['version']
    prev_hash = hex_to_bytes_le(tmpl['previousblockhash'])
    bits = int(tmpl['bits'], 16)
    curtime = tmpl['curtime']
    height = tmpl['height']
    coinbase_value = tmpl['coinbasevalue']
    
    # Get the coinbase output script from template
    # Use a simple OP_TRUE script for regtest
    coinbase_script_hex = '51'  # OP_TRUE (anyone can spend)
    
    dwc = tmpl.get('default_witness_commitment', '')
    
    cb_tx, cb_txid = build_coinbase_tx(height, coinbase_value, coinbase_script_hex, dwc, extra_nonce_bytes)
    
    # Merkle root (single tx = txid)
    merkle_root = cb_txid
    
    # Build header (80 bytes for non-DAG, extended for DAG)
    header = b''
    # Set DAG version bit
    dag_version = version | (1 << 28)  # BLOCK_VERSION_DAGMODE
    header += le32(dag_version)
    header += prev_hash
    header += merkle_root
    header += le32(curtime)
    header += le32(bits)
    
    # Try nonces until we find valid PoW (regtest difficulty is minimal)
    for nonce in range(0, 0xFFFFFFFF):
        candidate = header + le32(nonce)
        # DAG block: no extra parents (empty vector), so add compact_size(0)
        full_header = candidate + compact_size(0)
        block_hash = sha256d(full_header)
        # Check against target
        target = bits_to_target(bits)
        hash_int = int.from_bytes(block_hash, 'little')
        if hash_int <= target:
            # Found valid block
            block = full_header + compact_size(1) + cb_tx
            return block, bytes_to_hex_le(sha256d(full_header))
    
    return None, None

def bits_to_target(bits):
    """Convert compact bits to full target."""
    exp = bits >> 24
    mant = bits & 0x7fffff
    if bits & 0x800000:
        mant = -mant
    if exp <= 3:
        target = mant >> (8 * (3 - exp))
    else:
        target = mant << (8 * (exp - 3))
    return target

# Main
info = cli("getblockchaininfo")
print(f"Starting: blocks={info['blocks']}, dag_tips={info['dag_tips']}")

# Get template (both blocks will use the same template = same parent)
tmpl = cli("getblocktemplate", '{"rules":["segwit"]}')
print(f"Template: height={tmpl['height']}, parent={tmpl['previousblockhash'][:16]}...")

# Build block A with extra_nonce = 0x01
print("Building block A...")
block_a, hash_a = build_block(tmpl, b'\x01\x00\x00\x00')
print(f"Block A hash: {hash_a[:16]}...")

# Build block B with extra_nonce = 0x02 (different coinbase = different block)
print("Building block B...")
block_b, hash_b = build_block(tmpl, b'\x02\x00\x00\x00')
print(f"Block B hash: {hash_b[:16]}...")

# Submit both blocks
print("\nSubmitting block A...")
res_a = cli("submitblock", block_a.hex())
print(f"  Result: {res_a}")

print("Submitting block B...")
res_b = cli("submitblock", block_b.hex())
print(f"  Result: {res_b}")

# Check state
info = cli("getblockchaininfo")
print(f"\nAfter both: blocks={info['blocks']}, dag_tips={info['dag_tips']}")

tips = cli("getchaintips")
print(f"Chain tips:")
for t in tips:
    print(f"  height={t['height']} status={t['status']} hash={t['hash'][:16]}...")

# Mine a merge block that should reference both
print("\nMining merge block...")
addr = cli("getnewaddress", "", "bech32")
result = cli("generatetoaddress", "1", addr)
if result:
    merge_hash = result[0]
    merge_hdr = cli("getblockheader", merge_hash)
    print(f"Merge block hash: {merge_hash[:16]}...")
    print(f"  height: {merge_hdr['height']}")
    print(f"  dagparents: {merge_hdr.get('dagparents', [])}")
    dp_count = len(merge_hdr.get('dagparents', []))
    print(f"  dagparents count: {dp_count}")
    print(f"  selected_parent: {merge_hdr.get('selected_parent', 'N/A')[:16]}...")
    print(f"  blue_score: {merge_hdr.get('blue_score', 'N/A')}")
    print(f"  mergeset_blues: {merge_hdr.get('mergeset_blues', [])}")
    
    final = cli("getblockchaininfo")
    print(f"\nFinal: blocks={final['blocks']}, dag_tips={final['dag_tips']}, dagmode={final['dagmode']}, pqc={final['pqc']}")
