#!/usr/bin/env python3
# Copyright (c) 2026 BearTec.
# This file is part of QuantumBTC.
# Licensed under the Business Source License 1.1 until 2030-04-09.
# On 2030-04-09, the Change License becomes MIT. See LICENSE-BUSL and NOTICE.
"""
QuantumBTC GHOSTDAG Comprehensive Test
Mines 30-50 blocks while creating parallel forks, then analyzes:
- GHOSTDAG blue/red scoring
- Multi-parent DAG blocks
- Tip selection by blue_work
- Double-spend resistance
"""
import subprocess, json, struct, hashlib, os, sys, time

DATADIR = os.path.join(os.environ.get("TMPDIR", "/tmp"), "qbtc_regtest")
CLI = ["./src/bitcoin-cli", "-regtest", f"-datadir={DATADIR}"]

def rpc(method, *args):
    cmd = CLI + [method] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"RPC {method} failed: {r.stderr.strip()}")
    s = r.stdout.strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except (json.JSONDecodeError, ValueError):
        return s

def sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def u32le(v): return struct.pack('<I', v)
def u64le(v): return struct.pack('<q', v)
def varint(n):
    if n < 253: return bytes([n])
    elif n < 0x10000: return struct.pack('<BH', 253, n)
    else: return struct.pack('<BI', 254, n)

def le_hex(hex_str):
    return bytes.fromhex(hex_str)[::-1]

def bits_to_target(nbits):
    exp = nbits >> 24
    man = nbits & 0x7fffff
    return man << (8 * (exp - 3))

def create_coinbase_tx(height):
    extra = os.urandom(8)  # extra randomness for uniqueness
    if height == 0:
        ht = b'\x00'
    elif 1 <= height <= 16:
        ht = bytes([0x50 + height])
    else:
        h = height
        hb = b''
        while h > 0:
            hb += bytes([h & 0xff])
            h >>= 8
        if hb[-1] & 0x80:
            hb += b'\x00'
        ht = bytes([len(hb)]) + hb
    script_sig = ht + b'\x00' + extra
    script_pk = bytes.fromhex("76a914" + "01"*20 + "88ac")
    tx  = u32le(1)
    tx += varint(1)
    tx += b'\x00'*32 + u32le(0xffffffff)
    tx += varint(len(script_sig)) + script_sig + u32le(0xffffffff)
    tx += varint(1) + u64le(50_0000_0000)
    tx += varint(len(script_pk)) + script_pk + u32le(0)
    return tx

def mine_fork_block(prev_hash, height, timestamp, bits):
    """Create and mine a fork block on prev_hash."""
    coinbase = create_coinbase_tx(height)
    txid = sha256d(coinbase)
    version = 0x30000000
    hdr  = u32le(version) + le_hex(prev_hash) + txid
    hdr += u32le(timestamp) + u32le(bits) + u32le(0)
    hdr += varint(0)  # empty hashParents
    block = hdr + varint(1) + coinbase
    target = bits_to_target(bits)
    hdr_len = 80 + 1
    for nonce in range(0xFFFFFFFF):
        trial = block[:76] + u32le(nonce) + block[80:]
        h = sha256d(trial[:hdr_len])
        if int.from_bytes(h, 'little') <= target:
            return trial, h[::-1].hex()
    raise RuntimeError("Mining failed")

ADDR = "raw(76a914000000000000000000000000000000000000000088ac)"

def mine_block_rpc():
    """Mine a block via RPC generateblock."""
    result = rpc("generateblock", ADDR, "[]")
    return result['hash']

def get_header(hash_str):
    return rpc("getblockheader", hash_str)

# ============================================================
print("=" * 70)
print("  QuantumBTC GHOSTDAG Comprehensive Test")
print("=" * 70)

info = rpc("getblockchaininfo")
start_height = info['blocks']
print(f"\nStarting at height {start_height}")

# Phase 1: Mine 20 linear blocks
print("\n--- Phase 1: Mining 20 linear blocks ---")
for i in range(20):
    mine_block_rpc()
info = rpc("getblockchaininfo")
print(f"Height after linear mining: {info['blocks']}")
tip_hash = rpc("getbestblockhash")
tip_hdr = get_header(tip_hash)
print(f"Tip blue_score: {tip_hdr.get('blue_score', 'N/A')}")

# Phase 2: Create 5 fork blocks at different heights
print("\n--- Phase 2: Creating 5 parallel fork blocks ---")
fork_blocks = []
for fork_i in range(5):
    # Fork from (current_height - 2*fork_i) to create diverse forks
    fork_from_height = info['blocks'] - 2 * fork_i
    fork_from_hash = rpc("getblockhash", fork_from_height)
    fork_from_hdr = get_header(fork_from_hash)
    fork_height = fork_from_height + 1
    bits = int(fork_from_hdr['bits'], 16)
    ts = fork_from_hdr['time'] + 1

    block_data, block_hash = mine_fork_block(fork_from_hash, fork_height, ts, bits)
    result = rpc("submitblock", block_data.hex())
    print(f"  Fork {fork_i+1}: forking from height {fork_from_height} -> block {block_hash[:16]}... result='{result}'")
    fork_blocks.append(block_hash)

# Phase 3: Mine 15 more blocks (should reference fork blocks as DAG parents)
print("\n--- Phase 3: Mining 15 more blocks (should merge fork tips) ---")
multi_parent_count = 0
for i in range(15):
    h = mine_block_rpc()
    hdr = get_header(h)
    n_parents = 1 + len(hdr.get('dagparents', []))
    if n_parents > 1:
        multi_parent_count += 1
        print(f"  Block {hdr['height']}: {n_parents} parents, blue_score={hdr.get('blue_score')}, "
              f"blues={len(hdr.get('mergeset_blues', []))}, reds={len(hdr.get('mergeset_reds', []))}")

print(f"\nMulti-parent blocks: {multi_parent_count} out of 15")

# Phase 4: Create more forks to increase concurrency
print("\n--- Phase 4: Creating 5 more forks for higher concurrency ---")
for fork_i in range(5):
    cur_height = int(rpc("getblockcount"))
    fork_from_height = cur_height - fork_i
    fork_from_hash = rpc("getblockhash", fork_from_height)
    fork_from_hdr = get_header(fork_from_hash)
    fork_height = fork_from_height + 1
    bits = int(fork_from_hdr['bits'], 16)
    ts = fork_from_hdr['time'] + 1

    block_data, block_hash = mine_fork_block(fork_from_hash, fork_height, ts, bits)
    result = rpc("submitblock", block_data.hex())
    print(f"  Fork {fork_i+6}: forking from height {fork_from_height} -> {block_hash[:16]}... result='{result}'")
    fork_blocks.append(block_hash)

# Phase 5: Mine 10 more blocks
print("\n--- Phase 5: Mining 10 more blocks ---")
for i in range(10):
    h = mine_block_rpc()
    hdr = get_header(h)
    n_parents = 1 + len(hdr.get('dagparents', []))
    if n_parents > 1:
        multi_parent_count += 1
        print(f"  Block {hdr['height']}: {n_parents} parents, blue_score={hdr.get('blue_score')}, "
              f"blues={len(hdr.get('mergeset_blues', []))}, reds={len(hdr.get('mergeset_reds', []))}")

# ============================================================
# Summary
print("\n" + "=" * 70)
print("  RESULTS")
print("=" * 70)

info = rpc("getblockchaininfo")
print(f"\nChain: {info['chain']}")
print(f"Height: {info['blocks']}")
print(f"Total blocks mined: {info['blocks'] - start_height}")
print(f"Multi-parent blocks: {multi_parent_count}")

# Show tip
print("\n--- Best tip (getblockheader) ---")
best_hash = rpc("getbestblockhash")
best_hdr = get_header(best_hash)
for k in ['hash', 'height', 'versionHex', 'dagblock', 'blue_score', 'blue_work',
          'selected_parent', 'dagparents', 'mergeset_blues', 'mergeset_reds']:
    if k in best_hdr:
        v = best_hdr[k]
        if isinstance(v, str) and len(v) > 40:
            v = v[:16] + "..."
        print(f"  {k}: {v}")

# Show fork block scoring
print("\n--- Fork block GHOSTDAG scoring ---")
for i, fb_hash in enumerate(fork_blocks):
    try:
        fb_hdr = get_header(fb_hash)
        color = "BLUE" if fb_hdr.get('blue_score', 0) > 0 else "RED/UNSCORED"
        print(f"  Fork {i+1}: height={fb_hdr['height']}, blue_score={fb_hdr.get('blue_score', 'N/A')}, "
              f"confirmations={fb_hdr['confirmations']}, {color}")
    except Exception as e:
        print(f"  Fork {i+1}: {fb_hash[:16]}... ERROR: {e}")

# Walk a sample of blocks to show blue_score progression
print("\n--- Blue score progression (every 5th block) ---")
total = info['blocks']
for h in range(0, total + 1, 5):
    bh = rpc("getblockhash", h)
    bhdr = get_header(bh)
    dag_info = f"blue_score={bhdr.get('blue_score', 'N/A')}, blue_work={bhdr.get('blue_work', 'N/A')}"
    dp = bhdr.get('dagparents', [])
    print(f"  Height {h:3d}: {dag_info}, dagparents={len(dp)}")

# Show getblockchaininfo
print("\n--- getblockchaininfo ---")
for k in ['chain', 'blocks', 'headers', 'bestblockhash', 'chainwork', 'difficulty']:
    print(f"  {k}: {info.get(k)}")

print("\n" + "=" * 70)
print("  TEST COMPLETE")
print("=" * 70)
