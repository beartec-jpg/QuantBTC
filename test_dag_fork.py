#!/usr/bin/env python3
"""
QuantumBTC DAG Multi-Parent Block Demo
Creates concurrent tips by submitting a fork block, then mines a DAG block
that references multiple parents.
"""
import subprocess, json, struct, hashlib, os

DATADIR = os.path.join(os.environ.get("TMPDIR", "/tmp"), "qbtc_regtest")
CLI = ["./src/bitcoin-cli", "-regtest", f"-datadir={DATADIR}"]

def rpc(method, *args):
    cmd = CLI + [method] + [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"RPC {method} failed: {r.stderr.strip()}")
    s = r.stdout.strip()
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
    """Hex string (big-endian display) -> little-endian bytes for serialization."""
    return bytes.fromhex(hex_str)[::-1]

def create_coinbase_tx(height):
    """BIP34-compliant coinbase producing 50 BTC to a burn address."""
    extra = os.urandom(4)
    # BIP34 height push: CScript() << nHeight encoding
    # For 0: OP_0 (0x00)
    # For 1-16: OP_1..OP_16 (0x51..0x60)
    # For larger: push CScriptNum bytes
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

    # Use a distinctive burn address (all 0x01) to avoid duplicate txid
    script_pk = bytes.fromhex("76a914" + "01"*20 + "88ac")

    tx  = u32le(1)                     # version
    tx += varint(1)                    # 1 input
    tx += b'\x00'*32                   # null prevout hash
    tx += u32le(0xffffffff)            # null prevout index
    tx += varint(len(script_sig)) + script_sig
    tx += u32le(0xffffffff)            # sequence
    tx += varint(1)                    # 1 output
    tx += u64le(50_0000_0000)          # 50 BTC
    tx += varint(len(script_pk)) + script_pk
    tx += u32le(0)                     # locktime
    return tx

def bits_to_target(nbits):
    exp = nbits >> 24
    man = nbits & 0x7fffff
    return man << (8 * (exp - 3))

print("=== QuantumBTC DAG Multi-Parent Block Demo ===\n")

info = rpc("getblockchaininfo")
cur_height = info['blocks']
print(f"Chain: {info['chain']}, Height: {cur_height}")

# Fork from block 3 to create a competing block at height 4
fork_hash = rpc("getblockhash", 3)
fork_hdr = rpc("getblockheader", fork_hash)
print(f"Fork point: height={fork_hdr['height']}, hash={fork_hash}")

tip_hash = rpc("getbestblockhash")
print(f"Current tip: height={cur_height}, hash={tip_hash}")

# Build a fork block at height 4
fork_height = 4
coinbase = create_coinbase_tx(fork_height)
txid = sha256d(coinbase)  # non-witness txid = merkle root (single tx)

version = 0x30000000  # BIP9 + BLOCK_VERSION_DAGMODE
bits = int(fork_hdr['bits'], 16)

# Serialize header: 80 bytes + DAG parents (empty)
hdr  = u32le(version)
hdr += le_hex(fork_hash)       # hashPrevBlock
hdr += txid                    # hashMerkleRoot
hdr += u32le(fork_hdr['time'] + 1)  # nTime
hdr += u32le(bits)             # nBits
hdr += u32le(0)                # nNonce (placeholder)
hdr += varint(0)               # hashParents: empty

# Full block
block = hdr + varint(1) + coinbase

# Mine (regtest difficulty is trivial)
target = bits_to_target(bits)
print(f"\nMining fork block at height {fork_height}...")
hdr_len = 80 + 1  # 80 base + 1 byte varint(0) for empty parents

for nonce in range(0xFFFFFFFF):
    trial = block[:76] + u32le(nonce) + block[80:]
    h = sha256d(trial[:hdr_len])
    if int.from_bytes(h, 'little') <= target:
        block = trial
        block_hash = h[::-1].hex()
        print(f"Mined! nonce={nonce}, hash={block_hash}")
        break
else:
    print("Mining failed!"); exit(1)

# Submit fork block
print(f"\nSubmitting fork block ({len(block)} bytes)...")
result = rpc("submitblock", block.hex())
print(f"submitblock result: '{result}'")

# Verify it was accepted
try:
    fb = rpc("getblockheader", block_hash)
    print(f"Fork block: height={fb['height']}, confirmations={fb['confirmations']}")
except Exception as e:
    print(f"Fork block not in index: {e}")
    exit(1)

# Now mine a new block via generateblock — should reference both tips
print("\nMining a DAG block that should reference multiple parents...")
ADDR = "raw(76a914000000000000000000000000000000000000000088ac)"
nb = rpc("generateblock", ADDR, "[]")
new_hash = nb['hash']
new_hdr = rpc("getblockheader", new_hash)

print(f"\nNew block: height={new_hdr['height']}, hash={new_hash}")
print(f"  version:           {new_hdr['versionHex']}")
print(f"  dagblock:          {new_hdr.get('dagblock', False)}")
print(f"  dagparents:        {new_hdr.get('dagparents', [])}")
print(f"  previousblockhash: {new_hdr.get('previousblockhash', 'N/A')}")

parents = new_hdr.get('dagparents', [])
if parents:
    total = 1 + len(parents)
    print(f"\n*** SUCCESS: Multi-parent DAG block with {total} parents! ***")
    print(f"    selected parent: {new_hdr['previousblockhash']}")
    for i, p in enumerate(parents):
        print(f"    DAG parent {i+1}:    {p}")
else:
    print("\nNote: dagparents is empty — tipset may only have 1 tip.")
    # Debug
    print("  (This means the fork block was rejected or same-chain as active tip)")
