#!/usr/bin/env python3
"""
QuantumBTC Multi-Node Stress Test
==================================
Launches 4 QBTC testnet nodes in a mesh topology, creates 20 wallets
(5 per node), runs 2000 PQC hybrid transactions across the network,
and measures P2P propagation, block relay, and aggregate throughput.
"""

import subprocess
import json
import sys
import time
import random
import os
import signal
import shutil
from collections import defaultdict

# ── Configuration ──────────────────────────────────────────────────────
BITCOIND = os.environ.get("BITCOIND", "build-fresh/src/bitcoind")
CLI      = os.environ.get("CLI", "build-fresh/src/bitcoin-cli")
CHAIN    = "qbtctestnet"

NUM_NODES       = 4
WALLETS_PER_NODE = 5
NUM_TXS         = 2000
BATCH_SIZE      = 80       # txs between mining rounds
FUND_AMOUNT     = 30.0     # QBTC per wallet
SEND_MIN        = 0.001
SEND_MAX        = 0.3

# Port layout: node N → P2P 28333+N*100, RPC 28332+N*100
NODES = []
for i in range(NUM_NODES):
    NODES.append({
        "id": i,
        "p2p_port": 28333 + i * 100,
        "rpc_port": 28332 + i * 100,
        "datadir": f"/tmp/qbtc-multinode-{i}",
    })

# ── Process tracking ──────────────────────────────────────────────────
node_procs = []

def cleanup():
    """Kill all node processes and clean up data dirs."""
    print("\n[CLEANUP] Stopping all nodes...")
    for p in node_procs:
        try:
            p.terminate()
            p.wait(timeout=10)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    # Also kill any leftover bitcoind
    subprocess.run(["pkill", "-f", "qbtc-multinode"], capture_output=True)
    time.sleep(1)

def cleanup_and_exit(signum, frame):
    cleanup()
    sys.exit(1)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ── CLI helpers ────────────────────────────────────────────────────────
def node_cli(node_id, *args, wallet=None):
    n = NODES[node_id]
    cmd = [CLI, f"-{CHAIN}",
           f"-rpcport={n['rpc_port']}",
           f"-datadir={n['datadir']}"]
    if wallet:
        cmd.append(f"-rpcwallet={wallet}")
    cmd.extend(args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"CLI[node{node_id}]: {' '.join(cmd)}\n{r.stderr.strip()}")
    return r.stdout.strip()

def node_cli_json(node_id, *args, wallet=None):
    return json.loads(node_cli(node_id, *args, wallet=wallet))

def mine(node_id, n, addr):
    return node_cli_json(node_id, "generatetoaddress", str(n), addr)

# ── Stats ──────────────────────────────────────────────────────────────
tx_sizes = []
tx_vsizes = []
tx_weights = []
tx_fees = []
tx_times = []
tx_witness_elems = []
tx_input_counts = []
tx_output_counts = []
tx_source_node = []
tx_dest_node = []
wallet_send_count = defaultdict(int)
wallet_recv_count = defaultdict(int)
propagation_times = []  # time for tx to appear in all mempools
block_relay_times = []  # time for block to reach all nodes
blocks_mined = 0
txs_confirmed = 0
txs_failed = 0
errors = []

def percentile(data, p):
    if not data:
        return 0
    s = sorted(data)
    k = (len(s) - 1) * p / 100.0
    f = int(k)
    c = f + 1 if f + 1 < len(s) else f
    return s[f] + (s[c] - s[f]) * (k - f)

def mean(data):
    return sum(data) / len(data) if data else 0

def median(data):
    return percentile(data, 50)

# ── Main ───────────────────────────────────────────────────────────────
def main():
    random.seed(42)
    global blocks_mined, txs_confirmed, txs_failed

    print("=" * 72)
    print("  QuantumBTC Multi-Node Stress Test")
    print(f"  {NUM_NODES} nodes | {WALLETS_PER_NODE * NUM_NODES} wallets | {NUM_TXS} transactions")
    print("=" * 72)

    # ── 1. Start nodes ─────────────────────────────────────────────────
    print(f"\n[1/8] Starting {NUM_NODES} nodes...")

    # Kill any leftover nodes from prior runs
    subprocess.run(["pkill", "-f", "qbtc-multinode"], capture_output=True)
    time.sleep(1)

    for n in NODES:
        # Clean slate
        if os.path.exists(n["datadir"]):
            shutil.rmtree(n["datadir"])
        os.makedirs(n["datadir"], exist_ok=True)

        # Build addnode list (connect to all lower-numbered nodes)
        addnode_args = []
        for other in NODES[:n["id"]]:
            addnode_args.extend([f"-addnode=127.0.0.1:{other['p2p_port']}"])

        cmd = [
            BITCOIND, f"-{CHAIN}", "-daemon=0",
            f"-datadir={n['datadir']}",
            f"-port={n['p2p_port']}",
            f"-bind=127.0.0.1:{n['p2p_port']}",
            f"-rpcport={n['rpc_port']}",
            f"-rpcbind=127.0.0.1:{n['rpc_port']}",
            "-rpcallowip=127.0.0.0/8",
            "-fallbackfee=0.0001",
            "-txindex=1",
            "-server=1",
            "-listen=1",
            "-listenonion=0",
            "-i2pacceptincoming=0",
            "-discover=0",
            "-dnsseed=0",
            "-fixedseeds=0",
            "-printtoconsole=0",
            "-pqc=1",
        ] + addnode_args

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        node_procs.append(proc)
        print(f"  Node {n['id']}: pid={proc.pid}, p2p={n['p2p_port']}, rpc={n['rpc_port']}")

    # Wait for all nodes to be ready
    print("  Waiting for nodes to start...")
    for node_id in range(NUM_NODES):
        for attempt in range(45):
            try:
                info = node_cli_json(node_id, "getblockchaininfo")
                break
            except Exception:
                time.sleep(1)
        else:
            print(f"  FATAL: Node {node_id} failed to start")
            cleanup()
            sys.exit(1)
        print(f"  Node {node_id} ready: chain={info['chain']}, pqc={info['pqc']}")

    # ── 2. Verify mesh connectivity ────────────────────────────────────
    print(f"\n[2/8] Establishing mesh connectivity...")
    # Explicitly connect all node pairs
    for i in range(NUM_NODES):
        for j in range(NUM_NODES):
            if i != j:
                try:
                    node_cli(i, "addnode", f"127.0.0.1:{NODES[j]['p2p_port']}", "onetry")
                except Exception:
                    pass

    # Wait for connections
    time.sleep(5)
    for node_id in range(NUM_NODES):
        peers = node_cli_json(node_id, "getpeerinfo")
        print(f"  Node {node_id}: {len(peers)} peers connected")

    # ── 3. Create wallets ──────────────────────────────────────────────
    total_wallets = WALLETS_PER_NODE * NUM_NODES
    print(f"\n[3/8] Creating {total_wallets} wallets ({WALLETS_PER_NODE}/node)...")

    # wallet_info: list of (node_id, wallet_name, address)
    wallet_info = []
    for node_id in range(NUM_NODES):
        for w in range(WALLETS_PER_NODE):
            name = f"mn{node_id}w{w}"
            try:
                node_cli(node_id, "createwallet", name)
            except RuntimeError:
                try:
                    node_cli(node_id, "loadwallet", name)
                except RuntimeError:
                    pass
            addr = node_cli(node_id, "getnewaddress", wallet=name)
            wallet_info.append((node_id, name, addr))
            print(f"  Node {node_id} / {name}: {addr[:24]}...")

    # ── 4. Mine initial blocks and fund wallets ────────────────────────
    print(f"\n[4/8] Mining initial blocks & funding wallets...")

    # Use first wallet on node 0 as miner
    miner_node = 0
    miner_wallet = wallet_info[0][1]
    miner_addr = wallet_info[0][2]

    # Mine 250 blocks for maturity
    print(f"  Mining 250 blocks on node 0...")
    for batch in range(5):
        mine(miner_node, 50, miner_addr)
    blocks_mined += 250

    # Wait for sync across all nodes
    print("  Waiting for block sync...")
    sync_start = time.time()
    for attempt in range(60):
        heights = []
        for node_id in range(NUM_NODES):
            info = node_cli_json(node_id, "getblockchaininfo")
            heights.append(info["blocks"])
        if len(set(heights)) == 1 and heights[0] >= 250:
            break
        time.sleep(1)
    else:
        print(f"  WARNING: Sync incomplete after 60s. Heights: {heights}")
    sync_time = time.time() - sync_start
    print(f"  All nodes synced to height {heights[0]} in {sync_time:.1f}s")

    # Fund each wallet (skip miner wallet[0])
    print(f"  Funding {total_wallets - 1} wallets with {FUND_AMOUNT} QBTC each...")
    funded = 0
    for i, (node_id, name, addr) in enumerate(wallet_info[1:], 1):
        try:
            node_cli(miner_node, "sendtoaddress", addr, str(FUND_AMOUNT), wallet=miner_wallet)
            funded += 1
        except RuntimeError as e:
            errors.append(f"Fund {name}: {e}")
        # Mine every 10 funding txs to confirm and free up coins
        if funded % 10 == 0:
            mine(miner_node, 1, miner_addr)
            blocks_mined += 1

    # Mine remaining funding txs
    mine(miner_node, 10, miner_addr)
    blocks_mined += 10
    print(f"  Funded {funded}/{total_wallets - 1} wallets")

    # Wait for funding sync
    time.sleep(5)
    for attempt in range(30):
        heights = [node_cli_json(nid, "getblockchaininfo")["blocks"] for nid in range(NUM_NODES)]
        if len(set(heights)) == 1:
            break
        time.sleep(1)
    print(f"  Post-funding sync: all nodes at height {heights[0]}")

    # Second funding round for cross-node wallets (send larger amounts to ensure liquidity)
    print("  Second funding round for extra liquidity...")
    funded2 = 0
    for i, (node_id, name, addr) in enumerate(wallet_info[1:], 1):
        try:
            node_cli(miner_node, "sendtoaddress", addr, str(FUND_AMOUNT), wallet=miner_wallet)
            funded2 += 1
        except RuntimeError:
            pass
        if funded2 % 10 == 0:
            mine(miner_node, 1, miner_addr)
            blocks_mined += 1
    mine(miner_node, 10, miner_addr)
    blocks_mined += 10
    print(f"  Second round funded: {funded2}")

    # Sync again
    time.sleep(5)
    for attempt in range(30):
        heights = [node_cli_json(nid, "getblockchaininfo")["blocks"] for nid in range(NUM_NODES)]
        if len(set(heights)) == 1:
            break
        time.sleep(1)

    # Check balances
    print("  Wallet balances:")
    for node_id, name, addr in wallet_info[:6]:
        bal = node_cli_json(node_id, "getbalance", wallet=name)
        print(f"    {name}@node{node_id}: {bal} QBTC")
    print(f"    ... ({total_wallets - 6} more wallets)")

    # ── 5. Execute 2000 transactions ───────────────────────────────────
    print(f"\n[5/8] Running {NUM_TXS} PQC transactions across {NUM_NODES} nodes...")
    test_start = time.time()
    tx_count = 0
    batch_num = 0

    while tx_count < NUM_TXS:
        batch_num += 1
        batch_target = min(BATCH_SIZE, NUM_TXS - tx_count)
        batch_ok = 0
        batch_fail = 0

        for _ in range(batch_target):
            # Pick random sender and receiver on potentially different nodes
            sender_idx = random.randint(0, total_wallets - 1)
            receiver_idx = random.randint(0, total_wallets - 1)
            while receiver_idx == sender_idx:
                receiver_idx = random.randint(0, total_wallets - 1)

            s_node, s_wallet, s_addr = wallet_info[sender_idx]
            r_node, r_wallet, r_addr = wallet_info[receiver_idx]
            amount = round(random.uniform(SEND_MIN, SEND_MAX), 8)

            t0 = time.time()
            try:
                txid = node_cli(s_node, "sendtoaddress", r_addr, str(amount), wallet=s_wallet)
                elapsed = time.time() - t0
                tx_times.append(elapsed)
                tx_source_node.append(s_node)
                tx_dest_node.append(r_node)
                wallet_send_count[s_wallet] += 1
                wallet_recv_count[r_wallet] += 1

                # Sample propagation: check if tx appears in all mempools
                if batch_ok % 20 == 0:  # Sample every 20th tx
                    prop_start = time.time()
                    all_have = False
                    for check in range(30):
                        try:
                            found = 0
                            for nid in range(NUM_NODES):
                                mp = node_cli_json(nid, "getrawmempool")
                                if txid in mp:
                                    found += 1
                            if found == NUM_NODES:
                                all_have = True
                                break
                        except Exception:
                            pass
                        time.sleep(0.1)
                    prop_time = time.time() - prop_start
                    if all_have:
                        propagation_times.append(prop_time)

                batch_ok += 1
                tx_count += 1
            except RuntimeError as e:
                batch_fail += 1
                txs_failed += 1
                errors.append(f"TX {tx_count}: {str(e)[:100]}")
                tx_count += 1  # Count failures too so we don't loop forever

        # Mine batch and measure block relay
        mine_start = time.time()
        new_blocks = mine(miner_node, 2, miner_addr)
        blocks_mined += 2

        # Measure block relay to all nodes
        target_height = node_cli_json(miner_node, "getblockchaininfo")["blocks"]
        relay_start = time.time()
        for attempt in range(30):
            synced = 0
            for nid in range(1, NUM_NODES):
                try:
                    h = node_cli_json(nid, "getblockchaininfo")["blocks"]
                    if h >= target_height:
                        synced += 1
                except Exception:
                    pass
            if synced == NUM_NODES - 1:
                break
            time.sleep(0.1)
        relay_time = time.time() - relay_start
        block_relay_times.append(relay_time)

        elapsed_total = time.time() - test_start
        pct = tx_count / NUM_TXS * 100
        print(f"  Batch {batch_num}: {batch_ok} ok, {batch_fail} fail | "
              f"Progress: {tx_count}/{NUM_TXS} ({pct:.0f}%) | "
              f"Block relay: {relay_time:.2f}s | "
              f"Elapsed: {elapsed_total:.0f}s")

    test_elapsed = time.time() - test_start

    # ── 6. Final mining and sync ───────────────────────────────────────
    print(f"\n[6/8] Final mining and sync...")
    mine(miner_node, 10, miner_addr)
    blocks_mined += 10

    # Wait for full sync
    for attempt in range(60):
        heights = [node_cli_json(nid, "getblockchaininfo")["blocks"] for nid in range(NUM_NODES)]
        if len(set(heights)) == 1:
            break
        time.sleep(1)
    final_height = heights[0]
    print(f"  All nodes synced at height {final_height}")

    # ── 7. Collect transaction stats ───────────────────────────────────
    print(f"\n[7/8] Analyzing confirmed transactions...")

    # Get all blocks from start of test mining
    start_scan = 251  # after initial maturity blocks
    pqc_tx_count = 0
    classical_tx_count = 0

    for h in range(start_scan, final_height + 1):
        try:
            bh = node_cli(0, "getblockhash", str(h))
            blk = node_cli_json(0, "getblock", bh, "2")
        except Exception:
            continue

        for tx in blk.get("tx", []):
            if tx.get("vin", [{}])[0].get("coinbase"):
                continue  # skip coinbase

            txs_confirmed += 1
            size_b = tx.get("size", 0)
            vsize = tx.get("vsize", 0)
            weight = tx.get("weight", 0)
            tx_sizes.append(size_b)
            tx_vsizes.append(vsize)
            tx_weights.append(weight)

            # Count inputs/outputs
            n_in = len(tx.get("vin", []))
            n_out = len(tx.get("vout", []))
            tx_input_counts.append(n_in)
            tx_output_counts.append(n_out)

            # Check witness
            for vin in tx.get("vin", []):
                wit = vin.get("txinwitness", [])
                if len(wit) >= 4:
                    pqc_tx_count += 1
                    tx_witness_elems.append(len(wit))
                elif len(wit) > 0:
                    classical_tx_count += 1
                    tx_witness_elems.append(len(wit))
                break  # just check first input

            # Compute fee
            total_out = sum(v.get("value", 0) for v in tx.get("vout", []))
            total_in = 0
            for vin in tx.get("vin", []):
                prev_txid = vin.get("txid")
                prev_vout = vin.get("vout", 0)
                if prev_txid:
                    try:
                        prev_tx = node_cli_json(0, "getrawtransaction", prev_txid, "true")
                        total_in += prev_tx["vout"][prev_vout]["value"]
                    except Exception:
                        pass
            if total_in > 0:
                fee = total_in - total_out
                if fee > 0:
                    tx_fees.append(fee)

    # ── 8. Print comprehensive report ──────────────────────────────────
    print(f"\n{'=' * 72}")
    print(f"  MULTI-NODE STRESS TEST REPORT")
    print(f"{'=' * 72}")

    print(f"\n── Network Topology ─────────────────────────────────────────")
    print(f"  Nodes:              {NUM_NODES}")
    print(f"  Wallets:            {total_wallets} ({WALLETS_PER_NODE}/node)")
    print(f"  Mesh:               full mesh ({NUM_NODES * (NUM_NODES-1)} connections)")

    for nid in range(NUM_NODES):
        peers = node_cli_json(nid, "getpeerinfo")
        h = node_cli_json(nid, "getblockchaininfo")["blocks"]
        mp = node_cli_json(nid, "getrawmempool")
        print(f"  Node {nid}:             height={h}, peers={len(peers)}, mempool={len(mp)}")

    print(f"\n── Transaction Summary ──────────────────────────────────────")
    print(f"  Attempted:          {NUM_TXS}")
    succeeded = NUM_TXS - txs_failed
    print(f"  Succeeded:          {succeeded} ({succeeded/NUM_TXS*100:.1f}%)")
    print(f"  Failed:             {txs_failed}")
    print(f"  Confirmed on-chain: {txs_confirmed}")
    print(f"  PQC hybrid txs:    {pqc_tx_count}")
    print(f"  Classical txs:      {classical_tx_count}")

    print(f"\n── Timing ──────────────────────────────────────────────────")
    print(f"  Total test time:    {test_elapsed:.1f}s")
    if tx_times:
        effective_tps = succeeded / test_elapsed
        print(f"  Effective TPS:      {effective_tps:.1f} tx/s")
        print(f"  Submit latency:")
        print(f"    Mean:             {mean(tx_times)*1000:.1f} ms")
        print(f"    Median:           {median(tx_times)*1000:.1f} ms")
        print(f"    P95:              {percentile(tx_times, 95)*1000:.1f} ms")
        print(f"    P99:              {percentile(tx_times, 99)*1000:.1f} ms")
        print(f"    Min:              {min(tx_times)*1000:.1f} ms")
        print(f"    Max:              {max(tx_times)*1000:.1f} ms")

    print(f"\n── P2P Propagation ─────────────────────────────────────────")
    if propagation_times:
        print(f"  Samples:            {len(propagation_times)}")
        print(f"  Mean:               {mean(propagation_times)*1000:.0f} ms")
        print(f"  Median:             {median(propagation_times)*1000:.0f} ms")
        print(f"  P95:                {percentile(propagation_times, 95)*1000:.0f} ms")
        print(f"  Max:                {max(propagation_times)*1000:.0f} ms")
    else:
        print(f"  No propagation samples collected")

    print(f"\n── Block Relay ─────────────────────────────────────────────")
    if block_relay_times:
        print(f"  Samples:            {len(block_relay_times)}")
        print(f"  Mean:               {mean(block_relay_times)*1000:.0f} ms")
        print(f"  Median:             {median(block_relay_times)*1000:.0f} ms")
        print(f"  P95:                {percentile(block_relay_times, 95)*1000:.0f} ms")
        print(f"  Max:                {max(block_relay_times)*1000:.0f} ms")

    print(f"\n── Blocks ──────────────────────────────────────────────────")
    print(f"  Total mined:        {blocks_mined}")
    print(f"  Final height:       {final_height}")

    print(f"\n── Transaction Sizes ───────────────────────────────────────")
    if tx_vsizes:
        print(f"  Confirmed txs:      {len(tx_vsizes)}")
        print(f"  vsize (vB):")
        print(f"    Mean:             {mean(tx_vsizes):.0f}")
        print(f"    Median:           {median(tx_vsizes):.0f}")
        print(f"    P5:               {percentile(tx_vsizes, 5):.0f}")
        print(f"    P95:              {percentile(tx_vsizes, 95):.0f}")
        print(f"    Min:              {min(tx_vsizes)}")
        print(f"    Max:              {max(tx_vsizes)}")
        print(f"  Raw size (bytes):")
        print(f"    Mean:             {mean(tx_sizes):.0f}")
        print(f"    Median:           {median(tx_sizes):.0f}")
        print(f"  Weight (WU):")
        print(f"    Mean:             {mean(tx_weights):.0f}")
        print(f"    Median:           {median(tx_weights):.0f}")
        total_bytes = sum(tx_sizes)
        print(f"  Total tx data:      {total_bytes:,} bytes ({total_bytes/1e6:.2f} MB)")

    print(f"\n── Witness Analysis ────────────────────────────────────────")
    if tx_witness_elems:
        four_elem = sum(1 for e in tx_witness_elems if e >= 4)
        two_elem = sum(1 for e in tx_witness_elems if e == 2)
        print(f"  4-element (PQC):    {four_elem} ({four_elem/len(tx_witness_elems)*100:.1f}%)")
        print(f"  2-element (std):    {two_elem} ({two_elem/len(tx_witness_elems)*100:.1f}%)")
        if pqc_tx_count > 0:
            pqc_overhead = (2420 + 1312) / 107  # vs standard P2WPKH witness
            print(f"  PQC overhead:       {pqc_overhead:.1f}x vs classical P2WPKH")

    print(f"\n── Fees ────────────────────────────────────────────────────")
    if tx_fees:
        total_fees_sat = sum(int(f * 1e8) for f in tx_fees)
        print(f"  Total fees:         {sum(tx_fees):.8f} QBTC ({total_fees_sat:,} sats)")
        fee_rates = [f * 1e8 / vs for f, vs in zip(tx_fees, tx_vsizes) if vs > 0]
        if fee_rates:
            print(f"  Fee rate (sat/vB):")
            print(f"    Mean:             {mean(fee_rates):.1f}")
            print(f"    Median:           {median(fee_rates):.1f}")

    print(f"\n── Cross-Node Activity ─────────────────────────────────────")
    if tx_source_node and tx_dest_node:
        cross_node = sum(1 for s, d in zip(tx_source_node, tx_dest_node) if s != d)
        same_node = sum(1 for s, d in zip(tx_source_node, tx_dest_node) if s == d)
        print(f"  Cross-node txs:     {cross_node} ({cross_node/len(tx_source_node)*100:.1f}%)")
        print(f"  Same-node txs:      {same_node} ({same_node/len(tx_source_node)*100:.1f}%)")

        # Per-node send/recv table
        node_sends = defaultdict(int)
        node_recvs = defaultdict(int)
        for s in tx_source_node:
            node_sends[s] += 1
        for d in tx_dest_node:
            node_recvs[d] += 1
        print(f"\n  Per-node traffic:")
        print(f"  {'Node':<8} {'Sent':>8} {'Received':>10}")
        for nid in range(NUM_NODES):
            print(f"  Node {nid:<3} {node_sends[nid]:>8} {node_recvs[nid]:>10}")

    print(f"\n── Wallet Activity ─────────────────────────────────────────")
    print(f"  {'Wallet':<12} {'Sent':>6} {'Received':>10}")
    sorted_wallets = sorted(wallet_send_count.keys())
    for w in sorted_wallets[:10]:
        print(f"  {w:<12} {wallet_send_count[w]:>6} {wallet_recv_count[w]:>10}")
    if len(sorted_wallets) > 10:
        print(f"  ... ({len(sorted_wallets) - 10} more wallets)")

    print(f"\n── Input/Output Analysis ───────────────────────────────────")
    if tx_input_counts:
        print(f"  Inputs/tx:")
        print(f"    Mean:             {mean(tx_input_counts):.1f}")
        print(f"    Max:              {max(tx_input_counts)}")
        print(f"  Outputs/tx:")
        print(f"    Mean:             {mean(tx_output_counts):.1f}")
        print(f"    Max:              {max(tx_output_counts)}")

    if errors:
        print(f"\n── Errors ({len(errors)}) ────────────────────────────────────────")
        for e in errors[:20]:
            print(f"  {e}")
        if len(errors) > 20:
            print(f"  ... ({len(errors) - 20} more errors)")

    print(f"\n{'=' * 72}")
    print(f"  TEST {'PASSED' if txs_failed == 0 else 'COMPLETED WITH FAILURES'}")
    print(f"  {succeeded}/{NUM_TXS} transactions | {NUM_NODES} nodes | {final_height} blocks")
    print(f"{'=' * 72}")

    # Clean up
    cleanup()
    return 0 if txs_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
