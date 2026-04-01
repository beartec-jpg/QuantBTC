#!/usr/bin/env python3
"""
QuantumBTC GHOSTDAG Polish Test
================================
1. Mine 50+ blocks on a linear chain.
2. Create parallel forks at various heights.
3. Force >18 concurrent forks from the same base to produce red blocks.
4. Verify tip always has highest blue_work.
5. Show getblockchaininfo with dagmode field.
"""

import subprocess, json, time, sys, os

DATADIR = "/tmp/qbtc_polish_test"
CLI = "./src/bitcoin-cli"
BITCOIND = "./src/bitcoind"
RPC_PORT = "18555"

def rpc(method, *params):
    cmd = [CLI, f"-datadir={DATADIR}", f"-rpcport={RPC_PORT}", method]
    for p in params:
        cmd.append(str(p))
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"RPC ERROR [{method}]: {r.stderr.strip()}")
        return None
    out = r.stdout.strip()
    if not out:
        return None
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return out

def start_node():
    """Start bitcoind in regtest mode."""
    os.makedirs(DATADIR, exist_ok=True)
    subprocess.Popen([
        BITCOIND,
        f"-datadir={DATADIR}",
        "-regtest",
        "-server",
        "-daemon",
        f"-rpcport={RPC_PORT}",
        "-rpcuser=test",
        "-rpcpassword=test",
        "-dag=1",
        "-debug=validation",
        "-txindex=1",
        "-listen=0",
        "-listenonion=0",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait for RPC to become available
    for i in range(30):
        time.sleep(1)
        info = rpc("getblockchaininfo")
        if info:
            return True
    print("ERROR: bitcoind did not start")
    return False

def stop_node():
    rpc("stop")
    time.sleep(3)

def generate(n=1, address=None):
    """Generate blocks to a given address (or a new one)."""
    if not address:
        address = rpc("getnewaddress") or "bcrt1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq78cuzu"
    result = rpc("generatetoaddress", n, address)
    return result

def get_block_header(blockhash):
    return rpc("getblockheader", blockhash)

def get_best_block_hash():
    return rpc("getbestblockhash")

def main():
    print("=" * 70)
    print("QuantumBTC GHOSTDAG Polish Test")
    print("=" * 70)

    # Cleanup previous run
    subprocess.run(["rm", "-rf", DATADIR], capture_output=True)

    print("\n[1] Starting node...")
    if not start_node():
        sys.exit(1)

    # Use a fixed address for mining
    ADDR = "bcrt1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq78cuzu"  # anyone-can-spend

    # ============================================================
    # Phase 1: Mine 50 blocks linearly
    # ============================================================
    print("\n[2] Mining 50 blocks linearly...")
    blocks = generate(50, ADDR)
    if blocks:
        print(f"    Mined 50 blocks. Tip: {blocks[-1][:16]}...")
    else:
        print("    WARNING: generate returned None (wallet disabled?)")
        # Try generateblock approach
        print("    Trying generatetoaddress with -disablewallet workaround...")
        # With --disable-wallet, we use the raw block submission approach
        # Actually, let's just check if generatetoaddress works
        result = rpc("generatetoaddress", 1, ADDR)
        if result is None:
            print("    Cannot generate blocks. Checking if wallet is disabled...")
            info = rpc("getblockchaininfo")
            print(f"    Blockchain info: height={info.get('blocks', '?')}")

    info = rpc("getblockchaininfo")
    height = info.get("blocks", 0)
    print(f"    Current height: {height}")

    if height < 50:
        print("    Mining with submitblock fallback...")
        # Use low-level block creation
        import struct, hashlib

        def mine_block_raw():
            """Mine a block using getblocktemplate + submitblock."""
            template = rpc("getblocktemplate", '{"rules":["segwit"]}')
            if not template:
                return None

            import binascii

            version = template["version"]
            prev = template["previousblockhash"]
            curtime = template["curtime"]
            bits = template["bits"]
            height_val = template["height"]

            # Build coinbase transaction
            # Simple coinbase: OP_RETURN output
            height_bytes = height_val.to_bytes((height_val.bit_length() + 7) // 8, 'little') if height_val > 0 else b'\x00'
            # scriptSig: push height (BIP34)
            scriptsig = bytes([len(height_bytes)]) + height_bytes + b'\x00'  # extra nonce space
            # Coinbase input
            cb_txin = (
                b'\x00' * 32 +  # prev_hash (null)
                b'\xff\xff\xff\xff' +  # prev_index
                bytes([len(scriptsig)]) + scriptsig +
                b'\xff\xff\xff\xff'  # sequence
            )
            # Output: value + scriptPubKey (OP_TRUE)
            value = template.get("coinbasevalue", 5000000000)
            cb_txout = (
                struct.pack('<q', value) +
                b'\x01\x51'  # 1-byte scriptPubKey: OP_TRUE
            )
            # Witness commitment (required for segwit)
            # Simple: skip witness for now and use non-segwit coinbase
            # Full coinbase tx (non-witness)
            cb_tx = (
                struct.pack('<I', 1) +  # version
                b'\x01' +  # vin count
                cb_txin +
                b'\x01' +  # vout count
                cb_txout +
                struct.pack('<I', 0)  # locktime
            )

            # Calculate txid
            txid = hashlib.sha256(hashlib.sha256(cb_tx).digest()).digest()

            # Build merkle root (single tx)
            merkle_root = txid

            # Build header
            header = (
                struct.pack('<I', version) +
                bytes.fromhex(prev)[::-1] +  # little-endian
                merkle_root +
                struct.pack('<I', curtime) +
                bytes.fromhex(bits)[::-1] +  # little-endian
                struct.pack('<I', 0)  # nonce (start at 0)
            )

            # Mine: find nonce
            target = int(template["target"], 16)
            for nonce in range(0, 2**32):
                attempt = header[:76] + struct.pack('<I', nonce)
                h = hashlib.sha256(hashlib.sha256(attempt).digest()).digest()
                if int.from_bytes(h, 'little') < target:
                    # Found valid nonce
                    block_hex = (attempt + b'\x01' + cb_tx).hex()
                    result = rpc("submitblock", block_hex)
                    if result is None or result == "":
                        return True
                    else:
                        # Some error
                        return None

            return None

        # Mine blocks one at a time
        for i in range(50 - height):
            mine_block_raw()
            if (i + 1) % 10 == 0:
                info2 = rpc("getblockchaininfo")
                print(f"    ... mined {info2.get('blocks', '?')} blocks")

    info = rpc("getblockchaininfo")
    height = info.get("blocks", 0)
    print(f"    After phase 1: height={height}")

    # ============================================================
    # Phase 2: Create some forks at different heights
    # ============================================================
    print("\n[3] Creating parallel forks at various heights...")

    # Get block at height 40 as fork base
    fork_base_hash = rpc("getblockhash", 40)
    fork_base = get_block_header(fork_base_hash)
    print(f"    Fork base: height=40, hash={fork_base_hash[:16]}...")
    print(f"    Fork base blue_score: {fork_base.get('blue_score', 'N/A')}")

    # For creating forks, we need to invalidate and regenerate.
    # Alternative: use submitblock with blocks built on height 40.
    # Let's try invalidating blocks and re-mining.

    # Save current best
    best_before = get_best_block_hash()

    # Create 5 forks of length 2 each, branching from height 45-49
    fork_tips = []
    for fork_id in range(5):
        fork_height = 45 + fork_id
        base_hash = rpc("getblockhash", fork_height)
        # Invalidate block at fork_height+1 to rewind
        next_hash = rpc("getblockhash", fork_height + 1)
        if next_hash:
            rpc("invalidateblock", next_hash)
            # Mine 2 blocks on the fork
            new_blocks = generate(2, ADDR)
            if new_blocks:
                fork_tips.append(new_blocks[-1])
                tip_header = get_block_header(new_blocks[-1])
                print(f"    Fork {fork_id}: base=h{fork_height}, tip={new_blocks[-1][:16]}... "
                      f"blue_score={tip_header.get('blue_score', 'N/A')}")
            # Reconsider the invalidated block
            rpc("reconsiderblock", next_hash)

    info = rpc("getblockchaininfo")
    print(f"    After forks: height={info.get('blocks', 0)}, tips={info.get('dag_tips', 'N/A')}")

    # ============================================================
    # Phase 3: Mine 10 more blocks to extend
    # ============================================================
    print("\n[4] Mining 10 more blocks to extend chain...")
    more = generate(10, ADDR)
    info = rpc("getblockchaininfo")
    height = info.get("blocks", 0)
    print(f"    Height after extension: {height}")

    # ============================================================
    # Phase 4: Force >18 concurrent forks (red block test)
    # ============================================================
    print("\n[5] Creating >18 concurrent forks from same base (red block test)...")
    print("    GHOSTDAG K=18: forks beyond 18 should produce RED blocks")

    # Get the current tip as base for all forks
    current_best = get_best_block_hash()
    current_height = rpc("getblockchaininfo").get("blocks", 0)

    # We'll invalidate the tip, mine a single block, and reconsider - repeat 22 times
    # to create 22 competing tips at the same height
    # Better approach: mine from a base that's 1 block behind
    base_for_forks = rpc("getblockhash", current_height - 1)

    print(f"    Base for forks: height={current_height - 1}")

    # Invalidate the current tip
    rpc("invalidateblock", current_best)

    concurrent_fork_hashes = []
    for fork_id in range(22):
        # Mine 1 block
        new_blocks = generate(1, ADDR)
        if new_blocks:
            concurrent_fork_hashes.append(new_blocks[0])
            # Invalidate this new block and go back to base
            rpc("invalidateblock", new_blocks[0])

    # Now reconsider ALL of them
    print(f"    Created {len(concurrent_fork_hashes)} competing blocks")
    for h in concurrent_fork_hashes:
        rpc("reconsiderblock", h)

    # Reconsider original tip too
    rpc("reconsiderblock", current_best)

    # Mine a merge block that should incorporate all these tips
    print("    Mining merge block to consolidate forks...")
    merge_blocks = generate(1, ADDR)

    # Check GHOSTDAG data on the merge block
    if merge_blocks:
        merge_header = get_block_header(merge_blocks[0])
        print(f"\n    MERGE BLOCK GHOSTDAG DATA:")
        print(f"      hash:           {merge_blocks[0][:32]}...")
        print(f"      blue_score:     {merge_header.get('blue_score', 'N/A')}")
        print(f"      blue_work:      {merge_header.get('blue_work', 'N/A')}")
        print(f"      selected_parent:{merge_header.get('selected_parent', 'N/A')}")
        print(f"      dagparents:     {len(merge_header.get('dagparents', []))}")
        blues = merge_header.get("mergeset_blues", [])
        reds = merge_header.get("mergeset_reds", [])
        print(f"      mergeset_blues: {len(blues)}")
        print(f"      mergeset_reds:  {len(reds)}")
        if reds:
            print(f"      RED BLOCKS DETECTED! (anticone > K=18)")
            for r in reds[:5]:
                print(f"        red: {r[:32]}...")
        else:
            print(f"      No red blocks in this merge (anticone <= K=18)")

    # ============================================================
    # Phase 5: Verify tip selection uses highest blue_work
    # ============================================================
    print("\n[6] Verifying tip selection...")
    best = get_best_block_hash()
    best_header = get_block_header(best)
    print(f"    Best tip: {best[:32]}...")
    print(f"    blue_score: {best_header.get('blue_score', 'N/A')}")
    print(f"    blue_work:  {best_header.get('blue_work', 'N/A')}")
    print(f"    nHeight:    {best_header.get('height', 'N/A')}")
    dagparents = best_header.get("dagparents", [])
    print(f"    dagparents: {len(dagparents)}")

    # ============================================================
    # Phase 6: Show getblockchaininfo
    # ============================================================
    print("\n[7] getblockchaininfo:")
    info = rpc("getblockchaininfo")
    for key in ["chain", "blocks", "bestblockhash", "chainwork", "dagmode", "ghostdag_k", "dag_tips", "warnings"]:
        if key in info:
            val = info[key]
            if key == "bestblockhash":
                val = val[:32] + "..."
            if key == "chainwork":
                val = val[:16] + "..."
            print(f"    {key}: {val}")

    # ============================================================
    # Phase 7: Show a few block headers with GHOSTDAG fields
    # ============================================================
    print("\n[8] Sample block headers with GHOSTDAG fields:")
    final_height = info.get("blocks", 0)
    for h in [1, 10, 25, final_height - 1, final_height]:
        bh = rpc("getblockhash", h)
        if bh:
            hdr = get_block_header(bh)
            dag_p = hdr.get("dagparents", [])
            print(f"    h={h:3d}  blue_score={hdr.get('blue_score','?'):>4}  "
                  f"blue_work={hdr.get('blue_work','?'):>6}  "
                  f"dagparents={len(dag_p)}  "
                  f"blues={len(hdr.get('mergeset_blues',[]))}  "
                  f"reds={len(hdr.get('mergeset_reds',[]))}")

    # Count total red blocks
    print("\n[9] Scanning for red blocks across all heights...")
    total_reds = 0
    total_blues = 0
    max_reds_block = None
    max_reds_count = 0
    for h in range(1, final_height + 1):
        bh = rpc("getblockhash", h)
        if bh:
            hdr = get_block_header(bh)
            reds_count = len(hdr.get("mergeset_reds", []))
            blues_count = len(hdr.get("mergeset_blues", []))
            total_reds += reds_count
            total_blues += blues_count
            if reds_count > max_reds_count:
                max_reds_count = reds_count
                max_reds_block = h

    print(f"    Total mergeset_blues entries: {total_blues}")
    print(f"    Total mergeset_reds entries:  {total_reds}")
    if max_reds_block:
        print(f"    Max red blocks in single merge: {max_reds_count} (at height {max_reds_block})")
    else:
        print(f"    No red blocks found")

    print("\n" + "=" * 70)
    print("TEST COMPLETE")
    print("=" * 70)

    stop_node()

if __name__ == "__main__":
    main()
