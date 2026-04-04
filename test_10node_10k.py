#!/usr/bin/env python3
"""
QuantumBTC 10-Node / 10K-Transaction Stress Test
==================================================
Launches 10 QBTC testnet nodes in a mesh topology, creates 30 wallets
(3 per node), runs 10,000 PQC hybrid transactions across the network,
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

NUM_NODES        = 10
WALLETS_PER_NODE = 3
NUM_TXS          = 10000
BATCH_SIZE       = 200      # txs between mining rounds
FUND_AMOUNT      = 25.0     # QBTC per wallet
SEND_MIN         = 0.001
SEND_MAX         = 0.15

# Port layout: node N → P2P 28333+N*100, RPC 28332+N*100
NODES = []
for i in range(NUM_NODES):
    NODES.append({
        "id": i,
        "p2p_port": 28333 + i * 100,
        "rpc_port": 28332 + i * 100,
        "datadir": f"/tmp/qbtc-mn10-{i}",
    })

# ── Process tracking ──────────────────────────────────────────────────
node_procs = []

def cleanup():
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
    subprocess.run(["pkill", "-f", "qbtc-mn10"], capture_output=True)
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
        raise RuntimeError(f"CLI[node{node_id}]: {r.stderr.strip()[:200]}")
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
propagation_times = []
block_relay_times = []
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

def wait_sync(target=None, timeout_s=120):
    """Wait until all nodes are at the same height (or >= target)."""
    for _ in range(timeout_s):
        heights = []
        for nid in range(NUM_NODES):
            try:
                heights.append(node_cli_json(nid, "getblockchaininfo")["blocks"])
            except Exception:
                heights.append(-1)
        if len(set(heights)) == 1 and (target is None or heights[0] >= target):
            return heights[0]
        time.sleep(1)
    return max(heights) if heights else 0

# ── Main ───────────────────────────────────────────────────────────────
def main():
    random.seed(42)
    global blocks_mined, txs_confirmed, txs_failed
    total_wallets = WALLETS_PER_NODE * NUM_NODES
    wall_start = time.time()

    print("=" * 72)
    print("  QuantumBTC 10-Node Stress Test")
    print(f"  {NUM_NODES} nodes | {total_wallets} wallets | {NUM_TXS:,} transactions")
    print("=" * 72)

    # ── 1. Start nodes ─────────────────────────────────────────────────
    print(f"\n[1/8] Starting {NUM_NODES} nodes...")
    subprocess.run(["pkill", "-f", "qbtc-mn10"], capture_output=True)
    time.sleep(2)

    for n in NODES:
        if os.path.exists(n["datadir"]):
            shutil.rmtree(n["datadir"])
        os.makedirs(n["datadir"], exist_ok=True)

        # Connect to 3 nearest lower-numbered nodes (partial mesh to reduce conn overhead)
        addnode_args = []
        for other in NODES[max(0, n["id"]-3):n["id"]]:
            addnode_args.append(f"-addnode=127.0.0.1:{other['p2p_port']}")

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
            "-maxconnections=40",
            "-dbcache=50",
        ] + addnode_args

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        node_procs.append(proc)
        print(f"  Node {n['id']:>2}: pid={proc.pid}, p2p={n['p2p_port']}, rpc={n['rpc_port']}")

    # Wait for all nodes
    print("  Waiting for nodes to start...")
    for node_id in range(NUM_NODES):
        for attempt in range(60):
            try:
                info = node_cli_json(node_id, "getblockchaininfo")
                break
            except Exception:
                time.sleep(1)
        else:
            print(f"  FATAL: Node {node_id} failed to start")
            cleanup()
            sys.exit(1)
    print(f"  All {NUM_NODES} nodes started ✓")

    # ── 2. Build mesh ──────────────────────────────────────────────────
    print(f"\n[2/8] Establishing mesh connectivity...")
    # Connect every node to every other (addnode onetry is idempotent)
    for i in range(NUM_NODES):
        for j in range(NUM_NODES):
            if i != j:
                try:
                    node_cli(i, "addnode", f"127.0.0.1:{NODES[j]['p2p_port']}", "onetry")
                except Exception:
                    pass

    time.sleep(8)
    total_peers = 0
    for nid in range(NUM_NODES):
        peers = node_cli_json(nid, "getpeerinfo")
        total_peers += len(peers)
        if nid < 3 or nid == NUM_NODES - 1:
            print(f"  Node {nid}: {len(peers)} peers")
    avg_peers = total_peers / NUM_NODES
    print(f"  Average peers/node: {avg_peers:.1f}")

    # ── 3. Create wallets ──────────────────────────────────────────────
    print(f"\n[3/8] Creating {total_wallets} wallets ({WALLETS_PER_NODE}/node)...")
    wallet_info = []  # (node_id, wallet_name, address)
    for node_id in range(NUM_NODES):
        for w in range(WALLETS_PER_NODE):
            name = f"n{node_id}w{w}"
            try:
                node_cli(node_id, "createwallet", name)
            except RuntimeError:
                try:
                    node_cli(node_id, "loadwallet", name)
                except RuntimeError:
                    pass
            addr = node_cli(node_id, "getnewaddress", wallet=name)
            wallet_info.append((node_id, name, addr))
    print(f"  Created {len(wallet_info)} wallets across {NUM_NODES} nodes ✓")

    # ── 4. Mine & fund ─────────────────────────────────────────────────
    print(f"\n[4/8] Mining initial blocks & funding wallets...")
    miner_node = 0
    miner_wallet = wallet_info[0][1]
    miner_addr = wallet_info[0][2]

    # Mine 350 blocks for maturity (need lots of coins for 10K txs)
    print(f"  Mining 350 blocks on node 0...")
    for batch in range(7):
        mine(miner_node, 50, miner_addr)
    blocks_mined += 350

    h = wait_sync()
    print(f"  All nodes synced at height {h}")

    # Fund all non-miner wallets in 3 rounds
    for rnd in range(3):
        funded = 0
        for i, (node_id, name, addr) in enumerate(wallet_info[1:], 1):
            try:
                node_cli(miner_node, "sendtoaddress", addr, str(FUND_AMOUNT), wallet=miner_wallet)
                funded += 1
            except RuntimeError:
                pass
            if funded % 15 == 0:
                mine(miner_node, 1, miner_addr)
                blocks_mined += 1
        mine(miner_node, 6, miner_addr)
        blocks_mined += 6
        print(f"  Funding round {rnd+1}: {funded} wallets funded")

    wait_sync()

    # Verify balances
    balances = []
    for node_id, name, addr in wallet_info:
        b = node_cli_json(node_id, "getbalance", wallet=name)
        balances.append(b)
    min_bal = min(balances[1:])  # skip miner
    print(f"  Wallet balances: miner={balances[0]:.2f}, "
          f"min={min_bal:.2f}, avg={mean(balances[1:]):.2f} QBTC")

    # ── 5. Execute 10,000 transactions ─────────────────────────────────
    print(f"\n[5/8] Running {NUM_TXS:,} PQC transactions across {NUM_NODES} nodes...")
    test_start = time.time()
    tx_count = 0
    batch_num = 0
    consecutive_fail = 0

    while tx_count < NUM_TXS:
        batch_num += 1
        batch_target = min(BATCH_SIZE, NUM_TXS - tx_count)
        batch_ok = 0
        batch_fail = 0

        for _ in range(batch_target):
            sender_idx = random.randint(0, total_wallets - 1)
            receiver_idx = random.randint(0, total_wallets - 1)
            while receiver_idx == sender_idx:
                receiver_idx = random.randint(0, total_wallets - 1)

            s_node, s_wallet, _ = wallet_info[sender_idx]
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

                # Sample P2P propagation every 100th successful tx
                if batch_ok % 100 == 0 and batch_ok > 0:
                    prop_start = time.time()
                    for _ in range(40):
                        found = sum(1 for nid in range(NUM_NODES)
                                    if txid in node_cli_json(nid, "getrawmempool"))
                        if found == NUM_NODES:
                            propagation_times.append(time.time() - prop_start)
                            break
                        time.sleep(0.1)

                batch_ok += 1
                consecutive_fail = 0
            except RuntimeError as e:
                batch_fail += 1
                txs_failed += 1
                consecutive_fail += 1
                if len(errors) < 50:
                    errors.append(f"TX#{tx_count}: {str(e)[:120]}")

            tx_count += 1

        # Mine and measure block relay
        mine_start = time.time()
        mine(miner_node, 3, miner_addr)
        blocks_mined += 3

        target_h = node_cli_json(miner_node, "getblockchaininfo")["blocks"]
        relay_start = time.time()
        for _ in range(60):
            synced = sum(1 for nid in range(1, NUM_NODES)
                        if node_cli_json(nid, "getblockchaininfo")["blocks"] >= target_h)
            if synced == NUM_NODES - 1:
                break
            time.sleep(0.1)
        block_relay_times.append(time.time() - relay_start)

        elapsed_total = time.time() - test_start
        pct = tx_count / NUM_TXS * 100
        tps = (tx_count - txs_failed) / elapsed_total if elapsed_total > 0 else 0
        print(f"  Batch {batch_num:>3}: {batch_ok:>3} ok {batch_fail:>2} fail | "
              f"{tx_count:>5}/{NUM_TXS} ({pct:>5.1f}%) | "
              f"relay {block_relay_times[-1]:.2f}s | "
              f"{tps:.1f} tps | {elapsed_total:.0f}s")

        # If too many consecutive failures, refund wallets
        if consecutive_fail > 20:
            print("  ⚠ Re-mining for liquidity...")
            mine(miner_node, 20, miner_addr)
            blocks_mined += 20
            wait_sync(timeout_s=30)
            consecutive_fail = 0

    test_elapsed = time.time() - test_start

    # ── 6. Final mining and sync ───────────────────────────────────────
    print(f"\n[6/8] Final mining and sync...")
    mine(miner_node, 10, miner_addr)
    blocks_mined += 10
    final_height = wait_sync()
    print(f"  All {NUM_NODES} nodes synced at height {final_height}")

    # ── 7. Analyze confirmed transactions ──────────────────────────────
    print(f"\n[7/8] Analyzing on-chain transactions (scanning ~{final_height - 350} blocks)...")
    start_scan = 351
    pqc_tx_count = 0
    classical_tx_count = 0
    blocks_with_pqc = 0

    for h in range(start_scan, final_height + 1):
        try:
            bh = node_cli(0, "getblockhash", str(h))
            blk = node_cli_json(0, "getblock", bh, "2")
        except Exception:
            continue

        block_has_pqc = False
        for tx in blk.get("tx", []):
            if tx.get("vin", [{}])[0].get("coinbase"):
                continue

            txs_confirmed += 1
            tx_sizes.append(tx.get("size", 0))
            tx_vsizes.append(tx.get("vsize", 0))
            tx_weights.append(tx.get("weight", 0))
            tx_input_counts.append(len(tx.get("vin", [])))
            tx_output_counts.append(len(tx.get("vout", [])))

            for vin in tx.get("vin", []):
                wit = vin.get("txinwitness", [])
                if len(wit) >= 4:
                    pqc_tx_count += 1
                    block_has_pqc = True
                elif len(wit) > 0:
                    classical_tx_count += 1
                tx_witness_elems.append(len(wit))
                break

            # Sample fee calculation (every 10th tx to save time)
            if txs_confirmed % 10 == 0:
                total_out = sum(v.get("value", 0) for v in tx.get("vout", []))
                total_in = 0
                for vin in tx.get("vin", []):
                    ptx = vin.get("txid")
                    pvout = vin.get("vout", 0)
                    if ptx:
                        try:
                            prev = node_cli_json(0, "getrawtransaction", ptx, "true")
                            total_in += prev["vout"][pvout]["value"]
                        except Exception:
                            pass
                if total_in > 0:
                    fee = total_in - total_out
                    if fee > 0:
                        tx_fees.append(fee)

        if block_has_pqc:
            blocks_with_pqc += 1

    # ── 8. Report ──────────────────────────────────────────────────────
    wall_elapsed = time.time() - wall_start
    succeeded = NUM_TXS - txs_failed

    print(f"\n{'=' * 72}")
    print(f"  MULTI-NODE 10K STRESS TEST REPORT")
    print(f"{'=' * 72}")

    print(f"\n── Network Topology ─────────────────────────────────────────")
    print(f"  Nodes:              {NUM_NODES}")
    print(f"  Wallets:            {total_wallets} ({WALLETS_PER_NODE}/node)")
    for nid in range(NUM_NODES):
        try:
            peers = node_cli_json(nid, "getpeerinfo")
            h = node_cli_json(nid, "getblockchaininfo")["blocks"]
            mp = node_cli_json(nid, "getrawmempool")
            print(f"  Node {nid:>2}:            height={h}, peers={len(peers)}, mempool={len(mp)}")
        except Exception:
            print(f"  Node {nid:>2}:            (unreachable)")

    print(f"\n── Transaction Summary ──────────────────────────────────────")
    print(f"  Attempted:          {NUM_TXS:,}")
    print(f"  Succeeded:          {succeeded:,} ({succeeded/NUM_TXS*100:.1f}%)")
    print(f"  Failed:             {txs_failed:,}")
    print(f"  Confirmed on-chain: {txs_confirmed:,}")
    print(f"  PQC hybrid txs:    {pqc_tx_count:,}")
    print(f"  Classical txs:      {classical_tx_count:,}")
    print(f"  Blocks with PQC:    {blocks_with_pqc}")

    print(f"\n── Timing ──────────────────────────────────────────────────")
    print(f"  Total wall time:    {wall_elapsed:.0f}s ({wall_elapsed/60:.1f}m)")
    print(f"  TX phase time:      {test_elapsed:.0f}s ({test_elapsed/60:.1f}m)")
    if tx_times:
        print(f"  Effective TPS:      {succeeded/test_elapsed:.1f} tx/s")
        print(f"  Submit latency:")
        print(f"    Mean:             {mean(tx_times)*1000:.1f} ms")
        print(f"    Median:           {median(tx_times)*1000:.1f} ms")
        print(f"    P95:              {percentile(tx_times, 95)*1000:.1f} ms")
        print(f"    P99:              {percentile(tx_times, 99)*1000:.1f} ms")
        print(f"    Min:              {min(tx_times)*1000:.1f} ms")
        print(f"    Max:              {max(tx_times)*1000:.1f} ms")

    print(f"\n── P2P Propagation (to all {NUM_NODES} nodes) ──────────────────────")
    if propagation_times:
        print(f"  Samples:            {len(propagation_times)}")
        print(f"  Mean:               {mean(propagation_times)*1000:.0f} ms")
        print(f"  Median:             {median(propagation_times)*1000:.0f} ms")
        print(f"  P95:                {percentile(propagation_times, 95)*1000:.0f} ms")
        print(f"  Max:                {max(propagation_times)*1000:.0f} ms")
    else:
        print(f"  No samples collected")

    print(f"\n── Block Relay (miner → {NUM_NODES-1} peers) ──────────────────────────")
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
        print(f"  Analyzed:           {len(tx_vsizes):,}")
        print(f"  vsize (vB):")
        print(f"    Mean:             {mean(tx_vsizes):,.0f}")
        print(f"    Median:           {median(tx_vsizes):,.0f}")
        print(f"    P5:               {percentile(tx_vsizes, 5):,.0f}")
        print(f"    P95:              {percentile(tx_vsizes, 95):,.0f}")
        print(f"    Max:              {max(tx_vsizes):,}")
        total_bytes = sum(tx_sizes)
        print(f"  Total tx data:      {total_bytes:,} bytes ({total_bytes/1e6:.1f} MB)")

    print(f"\n── Witness Analysis ────────────────────────────────────────")
    if tx_witness_elems:
        four_e = sum(1 for e in tx_witness_elems if e >= 4)
        two_e  = sum(1 for e in tx_witness_elems if e == 2)
        total_w = len(tx_witness_elems)
        print(f"  4-element (PQC):    {four_e:,} ({four_e/total_w*100:.1f}%)")
        print(f"  2-element (std):    {two_e:,} ({two_e/total_w*100:.1f}%)")
        print(f"  PQC overhead:       {(2420+1312)/107:.1f}x vs classical P2WPKH")

    print(f"\n── Fees ────────────────────────────────────────────────────")
    if tx_fees:
        total_sat = sum(int(f * 1e8) for f in tx_fees)
        print(f"  Samples:            {len(tx_fees):,} (every 10th tx)")
        print(f"  Avg fee:            {mean(tx_fees)*1e8:,.0f} sats")
        fee_rates = [f*1e8/vs for f, vs in zip(tx_fees, tx_vsizes[::10]) if vs > 0]
        if fee_rates:
            print(f"  Fee rate (sat/vB):  mean={mean(fee_rates):.1f}, median={median(fee_rates):.1f}")
        print(f"  Est. total fees:    {total_sat/1e8 * 10:,.4f} QBTC (extrapolated)")

    print(f"\n── Cross-Node Activity ─────────────────────────────────────")
    if tx_source_node:
        cross = sum(1 for s, d in zip(tx_source_node, tx_dest_node) if s != d)
        same  = len(tx_source_node) - cross
        print(f"  Cross-node txs:     {cross:,} ({cross/len(tx_source_node)*100:.1f}%)")
        print(f"  Same-node txs:      {same:,} ({same/len(tx_source_node)*100:.1f}%)")

        node_sends = defaultdict(int)
        node_recvs = defaultdict(int)
        for s in tx_source_node:
            node_sends[s] += 1
        for d in tx_dest_node:
            node_recvs[d] += 1
        print(f"\n  {'Node':<8} {'Sent':>8} {'Recv':>8}")
        for nid in range(NUM_NODES):
            print(f"  Node {nid:<3} {node_sends[nid]:>8,} {node_recvs[nid]:>8,}")

    print(f"\n── Input/Output Analysis ───────────────────────────────────")
    if tx_input_counts:
        print(f"  Inputs/tx:  mean={mean(tx_input_counts):.1f}, max={max(tx_input_counts)}")
        print(f"  Outputs/tx: mean={mean(tx_output_counts):.1f}, max={max(tx_output_counts)}")

    # Data dir sizes
    print(f"\n── Storage ─────────────────────────────────────────────────")
    total_storage = 0
    for nid in range(NUM_NODES):
        try:
            r = subprocess.run(["du", "-sm", NODES[nid]["datadir"]],
                              capture_output=True, text=True, timeout=10)
            mb = int(r.stdout.split()[0])
            total_storage += mb
            if nid < 3 or nid == NUM_NODES - 1:
                print(f"  Node {nid}: {mb} MB")
        except Exception:
            pass
    print(f"  Total storage:      {total_storage} MB ({total_storage/1024:.1f} GB)")

    if errors:
        print(f"\n── Errors ({len(errors):,}) ────────────────────────────────────────")
        for e in errors[:15]:
            print(f"  {e}")
        if len(errors) > 15:
            print(f"  ... ({len(errors)-15} more)")

    status = "PASSED" if txs_failed == 0 else f"COMPLETED ({txs_failed:,} failures)"
    print(f"\n{'=' * 72}")
    print(f"  TEST {status}")
    print(f"  {succeeded:,}/{NUM_TXS:,} txs | {NUM_NODES} nodes | {final_height} blocks | {wall_elapsed/60:.1f}m")
    print(f"{'=' * 72}")

    cleanup()
    return 0 if txs_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
