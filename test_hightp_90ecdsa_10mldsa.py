#!/usr/bin/env python3
"""
QuantumBTC High-Throughput Multi-Miner DAG Stress Test
========================================================
Launches a local regtest network where EVERY node mines concurrently,
creating parallel blocks that stress the GHOSTDAG consensus. Pushes
maximum throughput with a 90% ECDSA / 10% ML-DSA (Dilithium) tx mix.

Architecture:
  - ALL nodes mine simultaneously → parallel blocks → DAG merges
  - 9 nodes: pqcmode=classical  → ECDSA-only signatures
  - 1 node:  pqcmode=hybrid     → ECDSA + ML-DSA-44 (Dilithium) hybrid
  - Each node gets multiple wallets
  - Concurrent mining across all nodes to max block production & DAG width
  - Tracks DAG metrics: tips, blue/red scoring, mergesets, selected parents

Usage:
    python3 test_hightp_90ecdsa_10mldsa.py [--nodes N] [--wallets-per-node W]
        [--txs T] [--batch B] [--duration S]

Defaults:
    --nodes 10  --wallets-per-node 5  --txs 50000  --batch 500
"""

import argparse
import json
import os
import random
import shutil
import signal
import subprocess
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Configuration ──────────────────────────────────────────────────────
BITCOIND = os.environ.get("BITCOIND", "build-fresh/src/bitcoind")
CLI      = os.environ.get("CLI", "build-fresh/src/bitcoin-cli")
CHAIN    = "regtest"

SEND_MIN = 0.00001
SEND_MAX = 0.005
FUND_AMOUNT = 200.0

# Fraction of ECDSA vs ML-DSA (enforced by which node sends)
ECDSA_RATIO = 0.90   # 90% ECDSA
MLDSA_RATIO = 0.10   # 10% ML-DSA

# ── Global state ───────────────────────────────────────────────────────
node_procs = []
NODES = []
_lock = threading.Lock()

def cleanup():
    print("\n[CLEANUP] Stopping all nodes...")
    for p in node_procs:
        try:
            p.terminate()
            p.wait(timeout=8)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
    subprocess.run(["pkill", "-f", "qbtc-htp-"], capture_output=True)
    time.sleep(1)

def cleanup_and_exit(signum, frame):
    cleanup()
    sys.exit(1)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ── CLI helpers ────────────────────────────────────────────────────────
def node_cli(node_id, *args, wallet=None, timeout=120):
    n = NODES[node_id]
    cmd = [CLI, f"-{CHAIN}",
           f"-rpcuser=test", f"-rpcpassword=test",
           f"-rpcport={n['rpc_port']}",
           f"-datadir={n['datadir']}"]
    if wallet:
        cmd.append(f"-rpcwallet={wallet}")
    cmd.extend(str(a) for a in args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(f"CLI[node{node_id}]: {r.stderr.strip()[:200]}")
    return r.stdout.strip()

def node_cli_json(node_id, *args, wallet=None, timeout=120):
    return json.loads(node_cli(node_id, *args, wallet=wallet, timeout=timeout))

def mine(node_id, n_blocks, addr):
    return node_cli_json(node_id, "generatetoaddress", str(n_blocks), addr)

# ── Stats ──────────────────────────────────────────────────────────────
tx_times = []
tx_sizes = []
tx_vsizes = []
tx_weights = []
tx_fees = []
tx_witness_elems = []
ecdsa_count = 0
mldsa_count = 0
txs_confirmed = 0
txs_failed = 0
txs_insuff = 0
blocks_mined = 0
errors = []
per_node_sent = defaultdict(int)
per_node_mined = defaultdict(int)

# DAG-specific metrics
dag_snapshots = []          # periodic {dag_tips, heights[], max_blue_score}
multi_parent_blocks = 0
total_mergeset_blues = 0
total_mergeset_reds = 0
max_dag_tips_seen = 0
parallel_mine_rounds = 0

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

# ── Node management ───────────────────────────────────────────────────
def build_node_list(num_nodes):
    """Build node config list. Node 0 is the ML-DSA hybrid node."""
    global NODES
    NODES = []
    for i in range(num_nodes):
        NODES.append({
            "id": i,
            "p2p_port": 29333 + i * 100,
            "rpc_port": 29332 + i * 100,
            "datadir": os.path.join(os.environ.get("TMPDIR", "/tmp"), f"qbtc-htp-{i}"),
            # Node 0 = ML-DSA hybrid; rest = classical ECDSA
            "pqcmode": "hybrid" if i == 0 else "classical",
        })

def start_nodes(num_nodes):
    """Start all nodes, connect mesh, wait for readiness."""
    global node_procs

    subprocess.run(["pkill", "-f", "qbtc-htp-"], capture_output=True)
    time.sleep(2)

    for n in NODES:
        if os.path.exists(n["datadir"]):
            shutil.rmtree(n["datadir"])
        os.makedirs(n["datadir"], exist_ok=True)

        # Write bitcoin.conf for each node
        conf_path = os.path.join(n["datadir"], "bitcoin.conf")
        with open(conf_path, "w") as f:
            f.write(f"regtest=1\n")
            f.write(f"server=1\n")
            f.write(f"rpcuser=test\n")
            f.write(f"rpcpassword=test\n")
            f.write(f"rpcallowip=127.0.0.0/8\n")
            f.write(f"pqc=1\n")
            f.write(f"pqcmode={n['pqcmode']}\n")
            f.write(f"dag=1\n")
            f.write(f"txindex=1\n")
            f.write(f"fallbackfee=0.0001\n")
            f.write(f"listen=1\n")
            f.write(f"listenonion=0\n")
            f.write(f"i2pacceptincoming=0\n")
            f.write(f"discover=0\n")
            f.write(f"dnsseed=0\n")
            f.write(f"fixedseeds=0\n")
            f.write(f"maxconnections=50\n")
            f.write(f"dbcache=100\n")
            f.write(f"maxmempool=300\n")
            f.write(f"blockmaxweight=4000000\n")
            f.write(f"blockmintxfee=0.00001\n")
            f.write(f"limitancestorcount=200\n")
            f.write(f"limitancestorsize=2000\n")
            f.write(f"limitdescendantcount=200\n")
            f.write(f"limitdescendantsize=2000\n")
            f.write(f"[regtest]\n")
            f.write(f"rpcport={n['rpc_port']}\n")
            f.write(f"port={n['p2p_port']}\n")
            f.write(f"bind=127.0.0.1:{n['p2p_port']}\n")
            f.write(f"rpcbind=127.0.0.1:{n['rpc_port']}\n")

        cmd = [
            BITCOIND,
            f"-datadir={n['datadir']}",
            "-daemon=0",
            "-printtoconsole=0",
        ]

        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        node_procs.append(proc)
        mode_label = "ML-DSA hybrid" if n["pqcmode"] == "hybrid" else "ECDSA classical"
        print(f"  Node {n['id']:>2}: pid={proc.pid} p2p={n['p2p_port']} rpc={n['rpc_port']} [{mode_label}]")

    # Wait for all nodes to respond
    print("  Waiting for nodes to start...")
    for nid in range(num_nodes):
        for attempt in range(60):
            try:
                node_cli_json(nid, "getblockchaininfo")
                break
            except Exception:
                time.sleep(1)
        else:
            print(f"  FATAL: Node {nid} failed to start after 60s")
            cleanup()
            sys.exit(1)
    print(f"  All {num_nodes} nodes started ✓")

def connect_mesh(num_nodes):
    """Full mesh connectivity."""
    print(f"  Connecting {num_nodes}-node mesh...")
    for i in range(num_nodes):
        for j in range(num_nodes):
            if i != j:
                try:
                    node_cli(i, "addnode", f"127.0.0.1:{NODES[j]['p2p_port']}", "onetry")
                except Exception:
                    pass
    time.sleep(6)

    total_peers = 0
    for nid in range(num_nodes):
        try:
            peers = node_cli_json(nid, "getpeerinfo")
            total_peers += len(peers)
        except Exception:
            pass
    avg = total_peers / num_nodes if num_nodes else 0
    print(f"  Mesh connected: avg {avg:.1f} peers/node ✓")

def wait_sync(num_nodes, target=None, timeout_s=120):
    """Wait until all nodes reach the same height."""
    for _ in range(timeout_s):
        heights = []
        for nid in range(num_nodes):
            try:
                heights.append(node_cli_json(nid, "getblockchaininfo")["blocks"])
            except Exception:
                heights.append(-1)
        if len(set(heights)) == 1 and (target is None or heights[0] >= target):
            return heights[0]
        time.sleep(1)
    return max(heights) if heights else 0

# ── Concurrent mining ─────────────────────────────────────────────────
def mine_one_block(nid, addr):
    """Mine a single block on a given node. Thread-safe. Tolerates rejection."""
    try:
        result = mine(nid, 1, addr)
        with _lock:
            per_node_mined[nid] += 1
        return (nid, result, None)
    except Exception as e:
        # Block rejection is expected during concurrent mining — it creates DAG forks
        return (nid, None, str(e)[:100])

def parallel_mine_all(num_nodes, wallet_info, wallets_per_node, blocks_each=1):
    """Mine blocks on ALL nodes simultaneously → creates parallel DAG blocks."""
    global blocks_mined, parallel_mine_rounds, max_dag_tips_seen
    parallel_mine_rounds += 1
    mined_this_round = 0

    with ThreadPoolExecutor(max_workers=num_nodes) as pool:
        futures = []
        for nid in range(num_nodes):
            addr = wallet_info[nid * wallets_per_node]["addrs"][0]
            for _ in range(blocks_each):
                futures.append(pool.submit(mine_one_block, nid, addr))

        for fut in as_completed(futures):
            nid, result, err = fut.result()
            if result:
                mined_this_round += 1

    with _lock:
        blocks_mined += mined_this_round

    # Snapshot DAG state after parallel mining
    try:
        info = node_cli_json(0, "getblockchaininfo")
        tips = info.get("dag_tips", 1)
        if tips > max_dag_tips_seen:
            max_dag_tips_seen = tips
    except Exception:
        pass

    return mined_this_round

def snapshot_dag(num_nodes):
    """Capture DAG state across all nodes."""
    global max_dag_tips_seen
    snap = {"time": time.time(), "heights": [], "dag_tips": [], "blue_scores": []}
    for nid in range(num_nodes):
        try:
            info = node_cli_json(nid, "getblockchaininfo")
            snap["heights"].append(info["blocks"])
            tips = info.get("dag_tips", 1)
            snap["dag_tips"].append(tips)
            if tips > max_dag_tips_seen:
                max_dag_tips_seen = tips

            best = node_cli(nid, "getbestblockhash")
            hdr = node_cli_json(nid, "getblockheader", best)
            snap["blue_scores"].append(hdr.get("blue_score", 0))
        except Exception:
            snap["heights"].append(-1)
            snap["dag_tips"].append(0)
            snap["blue_scores"].append(0)
    dag_snapshots.append(snap)
    return snap

# ── Main ───────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="High-throughput 90%% ECDSA / 10%% ML-DSA multi-miner DAG stress test")
    parser.add_argument("--nodes", type=int, default=10, help="Total nodes — ALL mine (default: 10)")
    parser.add_argument("--wallets-per-node", type=int, default=5, help="Wallets per node (default: 5)")
    parser.add_argument("--txs", type=int, default=50000, help="Total transactions to send (default: 50000)")
    parser.add_argument("--batch", type=int, default=200, help="Transactions per mining round (default: 200)")
    parser.add_argument("--duration", type=int, default=0, help="Max duration in seconds (0=unlimited)")
    args = parser.parse_args()

    NUM_NODES = args.nodes
    WALLETS_PER_NODE = args.wallets_per_node
    NUM_TXS = args.txs
    BATCH_SIZE = args.batch
    MAX_DURATION = args.duration
    total_wallets = NUM_NODES * WALLETS_PER_NODE

    global blocks_mined, txs_confirmed, txs_failed, txs_insuff, ecdsa_count, mldsa_count
    global multi_parent_blocks, total_mergeset_blues, total_mergeset_reds

    random.seed(int(time.time()))

    print("=" * 76)
    print("  QuantumBTC High-Throughput Multi-Miner DAG Stress Test")
    print(f"  90% ECDSA / 10% ML-DSA (Dilithium) | ALL {NUM_NODES} nodes mining")
    print(f"  {NUM_NODES} nodes | {total_wallets} wallets | {NUM_TXS:,} target txs")
    print(f"  Node 0: ML-DSA hybrid | Nodes 1-{NUM_NODES-1}: ECDSA classical")
    print("=" * 76)

    wall_start = time.time()

    # ── 1. Start nodes ─────────────────────────────────────────────────
    print(f"\n[1/10] Starting {NUM_NODES} nodes (all are miners)...")
    build_node_list(NUM_NODES)
    start_nodes(NUM_NODES)

    # Verify DAG + PQC enabled
    info = node_cli_json(0, "getblockchaininfo")
    print(f"  Chain: {info.get('chain','?')} | DAG: {info.get('dagmode','?')} "
          f"| PQC: {info.get('pqc','?')} | GHOSTDAG K: {info.get('ghostdag_k','?')}")

    # ── 2. Mesh connectivity ───────────────────────────────────────────
    print(f"\n[2/10] Establishing mesh connectivity...")
    connect_mesh(NUM_NODES)

    # ── 3. Create wallets ──────────────────────────────────────────────
    print(f"\n[3/10] Creating {total_wallets} wallets ({WALLETS_PER_NODE}/node)...")
    wallet_info = []
    ecdsa_wallets = []
    mldsa_wallets = []

    for nid in range(NUM_NODES):
        is_mldsa = NODES[nid]["pqcmode"] == "hybrid"
        for w in range(WALLETS_PER_NODE):
            name = f"n{nid}w{w}"
            try:
                node_cli(nid, "createwallet", name)
            except RuntimeError:
                try:
                    node_cli(nid, "loadwallet", name)
                except RuntimeError:
                    pass
            # Create multiple addresses per wallet for UTXO spread
            addrs = []
            for _ in range(5):
                addr = node_cli(nid, "getnewaddress", "", "bech32", wallet=name)
                addrs.append(addr)

            entry = {"nid": nid, "name": name, "addrs": addrs, "mldsa": is_mldsa}
            wallet_info.append(entry)
            if is_mldsa:
                mldsa_wallets.append(entry)
            else:
                ecdsa_wallets.append(entry)

    print(f"  ECDSA wallets:  {len(ecdsa_wallets)} (on {NUM_NODES - 1} nodes)")
    print(f"  ML-DSA wallets: {len(mldsa_wallets)} (on node 0)")

    # ── 4. Mine initial blocks (single-node bootstrap, then distribute) ─
    print(f"\n[4/10] Mining initial blocks for coinbase maturity...")
    # Mine all bootstrap blocks on node 0 only (mesh is connected, so other
    # nodes will try to mine on a moving tip and get rejected).
    # We fund other nodes via transactions in step 6.
    bootstrap_blocks = 600
    bootstrap_addr = wallet_info[0]["addrs"][0]
    print(f"  Mining {bootstrap_blocks} blocks on node 0...")
    for batch_start in range(0, bootstrap_blocks, 100):
        batch_count = min(100, bootstrap_blocks - batch_start)
        mine(0, batch_count, bootstrap_addr)
        blocks_mined += batch_count
        per_node_mined[0] += batch_count
    wait_sync(NUM_NODES, timeout_s=180)

    height = node_cli_json(0, "getblockchaininfo")["blocks"]
    print(f"  Mined {blocks_mined} blocks, height={height}")

    # ── 5. Parallel mine burst — stress DAG with concurrent blocks ─────
    print(f"\n[5/10] DAG stress: parallel mining burst ({NUM_NODES} miners × 3 blocks)...")
    parallel_blocks = parallel_mine_all(NUM_NODES, wallet_info, WALLETS_PER_NODE, blocks_each=3)
    time.sleep(3)  # Let blocks propagate
    snap = snapshot_dag(NUM_NODES)
    print(f"  Parallel blocks mined: {parallel_blocks}")
    print(f"  DAG tips across nodes: {snap['dag_tips']}")
    print(f"  Heights: {snap['heights']}")
    print(f"  Blue scores: {snap['blue_scores']}")

    # ── 6. Fund all wallets ────────────────────────────────────────────
    print(f"\n[6/10] Funding {total_wallets} wallets ({FUND_AMOUNT} QBTC each)...")
    # Node 0 has all the coinbase (600 blocks × 50 QBTC = ~25000 mature).
    # Send from node 0's first wallet to everyone in smaller chunks.
    funder_wallet = wallet_info[0]["name"]

    # First check funder balance
    funder_bal = float(node_cli(0, "getbalance", wallet=funder_wallet))
    print(f"  Funder balance: {funder_bal:.2f} QBTC")

    # Send 5 QBTC per address, 2 addresses per wallet = 10 QBTC per wallet
    # 50 wallets × 10 = 500 QBTC per round; do multiple rounds to build up
    send_per_addr = 5.0
    fund_rounds = 4
    for rnd in range(fund_rounds):
        funded = 0
        for i, w in enumerate(wallet_info):
            if i == 0 and rnd == 0:
                continue
            for addr in w["addrs"][:2]:
                try:
                    node_cli(0, "sendtoaddress", addr,
                             f"{send_per_addr:.8f}",
                             wallet=funder_wallet)
                    funded += 1
                except RuntimeError:
                    pass
            # Mine every 20 sends to keep UTXO set fresh (creates change outputs)
            if funded > 0 and funded % 20 == 0:
                mine(0, 2, wallet_info[0]["addrs"][0])
                blocks_mined += 2
                per_node_mined[0] += 2

        # Mine to confirm this round's txs
        mine(0, 10, wallet_info[0]["addrs"][0])
        blocks_mined += 10
        per_node_mined[0] += 10
        wait_sync(NUM_NODES, timeout_s=60)
        print(f"  Funding round {rnd+1}/{fund_rounds}: {funded} sends")

    # Extra mining for UTXO maturity
    print(f"  Extra mining for UTXO maturity...")
    mine(0, 10, wallet_info[0]["addrs"][0])
    blocks_mined += 10
    per_node_mined[0] += 10
    wait_sync(NUM_NODES, timeout_s=60)

    # Verify balances
    total_bal = 0
    low_balance = 0
    for w in wallet_info:
        try:
            bal = float(node_cli(w["nid"], "getbalance", wallet=w["name"]))
            total_bal += bal
            if bal < 1.0:
                low_balance += 1
        except Exception:
            low_balance += 1
    print(f"  Total funded: {total_bal:.2f} QBTC, low-balance wallets: {low_balance}")

    # ── 7. High-throughput TX blast + concurrent multi-miner ───────────
    print(f"\n[7/10] Blasting {NUM_TXS:,} txs (90% ECDSA / 10% ML-DSA) "
          f"with ALL {NUM_NODES} nodes mining...")
    print(f"  Batch: {BATCH_SIZE} txs → then ALL nodes mine 1 block simultaneously")

    test_start = time.time()
    tx_count = 0
    batch_num = 0
    consecutive_fail = 0

    all_addrs = []
    for w in wallet_info:
        for addr in w["addrs"]:
            all_addrs.append(addr)

    while tx_count < NUM_TXS:
        if MAX_DURATION > 0 and (time.time() - test_start) > MAX_DURATION:
            print(f"\n  Duration limit ({MAX_DURATION}s) reached at tx #{tx_count}")
            break

        batch_num += 1
        batch_target = min(BATCH_SIZE, NUM_TXS - tx_count)
        batch_ok = 0
        batch_fail = 0
        batch_insuff = 0   # insufficient funds (not counted as real failures)
        batch_ecdsa = 0
        batch_mldsa = 0

        # Track nodes that hit map::at so we can avoid them temporarily
        maperr_cooldown = {}   # nid → tx_count when it can be used again

        # Refresh per-wallet spendable balance cache at batch start
        wallet_bal = {}
        for w in wallet_info:
            try:
                bal = float(node_cli(w["nid"], "getbalance", wallet=w["name"], timeout=10))
                wallet_bal[w["name"]] = bal
            except Exception:
                wallet_bal[w["name"]] = 0.0

        for _ in range(batch_target):
            # Decide ECDSA vs ML-DSA
            use_mldsa = random.random() < MLDSA_RATIO

            # Pick sender with funds, avoiding nodes on map::at cooldown
            pool = mldsa_wallets if (use_mldsa and mldsa_wallets) else (ecdsa_wallets if ecdsa_wallets else wallet_info)
            # Sort candidates by balance (prefer wallets with more funds)
            candidates = [w for w in pool
                          if wallet_bal.get(w["name"], 0) > SEND_MAX
                          and (w["nid"] not in maperr_cooldown or tx_count >= maperr_cooldown.get(w["nid"], 0))]
            if not candidates:
                # Fallback: any wallet from the pool
                candidates = pool

            sender = random.choice(candidates)

            recv_addr = random.choice(all_addrs)
            amount = round(random.uniform(SEND_MIN, SEND_MAX), 8)

            t0 = time.time()
            succeeded = False
            for attempt in range(2):  # up to 1 retry on map::at
                try:
                    txid = node_cli(sender["nid"], "sendtoaddress", recv_addr,
                                    f"{amount:.8f}", wallet=sender["name"], timeout=30)
                    dt = time.time() - t0
                    tx_times.append(dt)
                    per_node_sent[sender["nid"]] += 1

                    if sender["mldsa"]:
                        mldsa_count += 1
                        batch_mldsa += 1
                    else:
                        ecdsa_count += 1
                        batch_ecdsa += 1

                    batch_ok += 1
                    consecutive_fail = 0
                    succeeded = True

                    # Deduct from cached balance
                    wallet_bal[sender["name"]] = max(0, wallet_bal.get(sender["name"], 0) - amount)

                    # Sample tx details every 50th tx
                    if batch_ok % 50 == 1:
                        try:
                            txinfo = node_cli_json(sender["nid"], "getrawtransaction", txid, "true")
                            tx_sizes.append(txinfo.get("size", 0))
                            tx_vsizes.append(txinfo.get("vsize", 0))
                            tx_weights.append(txinfo.get("weight", 0))
                            wit = txinfo.get("vin", [{}])[0].get("txinwitness", [])
                            tx_witness_elems.append(len(wit))
                        except Exception:
                            pass
                    break  # success — no retry needed

                except RuntimeError as e:
                    err_str = str(e)
                    if "map::at" in err_str and attempt == 0:
                        # Cooldown this node for 100 txs & retry with different wallet
                        maperr_cooldown[sender["nid"]] = tx_count + 100
                        pool2 = mldsa_wallets if use_mldsa else ecdsa_wallets
                        alt = [w for w in pool2 if w["nid"] not in maperr_cooldown]
                        if alt:
                            sender = random.choice(alt)
                        elif pool2:
                            sender = random.choice(pool2)
                        continue  # retry once

                    # Insufficient funds — don't count as real failure, just skip
                    if "Insufficient funds" in err_str or "too many unconfirmed" in err_str:
                        batch_insuff += 1
                        txs_insuff += 1
                        wallet_bal[sender["name"]] = 0  # mark wallet empty
                        break

                    batch_fail += 1
                    txs_failed += 1
                    consecutive_fail += 1
                    if len(errors) < 100:
                        errors.append(f"tx#{tx_count}: {err_str[:120]}")

            tx_count += 1

            # Mid-batch recovery: if 20+ consecutive fails, mine immediately
            if consecutive_fail >= 20 and consecutive_fail % 20 == 0:
                try:
                    mine(0, 3, wallet_info[0]["addrs"][0])
                    blocks_mined += 3
                    per_node_mined[0] += 3
                except Exception:
                    pass

        # ALL nodes mine simultaneously → creates parallel blocks / DAG forks
        # Base: 3 blocks each; increase to 4 when failure rate is high
        mine_each = 4 if (batch_fail + batch_insuff) > batch_target * 0.2 else 3
        parallel_blocks = parallel_mine_all(NUM_NODES, wallet_info, WALLETS_PER_NODE, blocks_each=mine_each)

        # Snapshot DAG state every 5 batches
        if batch_num % 5 == 0:
            snapshot_dag(NUM_NODES)

        # Every 25 batches: refresh wallet UTXO state on nodes that hit map::at
        if batch_num % 25 == 0 and maperr_cooldown:
            rescan_nids = set(maperr_cooldown.keys())
            maperr_cooldown.clear()
            for w in wallet_info:
                if w["nid"] in rescan_nids:
                    try:
                        node_cli(w["nid"], "rescanblockchain", wallet=w["name"], timeout=60)
                    except Exception:
                        pass

        elapsed = time.time() - test_start
        ok_total = ecdsa_count + mldsa_count
        tps = ok_total / elapsed if elapsed > 0 else 0
        pct = tx_count / NUM_TXS * 100

        # Get DAG tips from node 0
        try:
            dag_tips = node_cli_json(0, "getblockchaininfo").get("dag_tips", "?")
        except Exception:
            dag_tips = "?"

        print(f"  Batch {batch_num:>4}: {batch_ok:>4} ok {batch_fail:>3} fail {batch_insuff:>3} noUTXO | "
              f"{tx_count:>6}/{NUM_TXS} ({pct:>5.1f}%) | "
              f"ECDSA={batch_ecdsa} MLDSA={batch_mldsa} | "
              f"dag_tips={dag_tips} mined={parallel_blocks} | "
              f"{tps:.1f} tps | {elapsed:.0f}s")

        # Liquidity recovery if needed
        if consecutive_fail > 30:
            print(f"  ⚠ Re-mining for liquidity...")
            mine(0, 20, wallet_info[0]["addrs"][0])
            blocks_mined += 20
            per_node_mined[0] += 20
            wait_sync(NUM_NODES, timeout_s=60)
            consecutive_fail = 0

    test_elapsed = time.time() - test_start

    # ── 8. Final mining and sync ───────────────────────────────────────
    print(f"\n[8/10] Final parallel mining and sync...")
    parallel_mine_all(NUM_NODES, wallet_info, WALLETS_PER_NODE, blocks_each=3)
    time.sleep(5)
    final_height = wait_sync(NUM_NODES, timeout_s=120)
    print(f"  All {NUM_NODES} nodes synced at height {final_height}")

    # ── 9. DAG + on-chain analysis ─────────────────────────────────────
    print(f"\n[9/10] Analyzing DAG structure and on-chain transactions...")
    scan_start = max(1, final_height - 300)
    pqc_onchain = 0
    ecdsa_onchain = 0
    blocks_with_pqc = 0
    blocks_scanned = 0

    for h in range(scan_start, final_height + 1):
        try:
            bh = node_cli(0, "getblockhash", str(h))
            hdr = node_cli_json(0, "getblockheader", bh)
            blk = node_cli_json(0, "getblock", bh, "2")
        except Exception:
            continue

        blocks_scanned += 1

        # DAG analysis per block
        dagparents = hdr.get("dagparents", [])
        if len(dagparents) > 0:
            multi_parent_blocks += 1
        mergeset_b = hdr.get("mergeset_blues", [])
        mergeset_r = hdr.get("mergeset_reds", [])
        total_mergeset_blues += len(mergeset_b)
        total_mergeset_reds += len(mergeset_r)

        # TX signature analysis
        block_has_pqc = False
        for tx in blk.get("tx", []):
            if tx.get("vin", [{}])[0].get("coinbase"):
                continue
            txs_confirmed += 1

            for vin in tx.get("vin", []):
                wit = vin.get("txinwitness", [])
                if len(wit) >= 4:
                    pqc_onchain += 1
                    block_has_pqc = True
                elif len(wit) > 0:
                    ecdsa_onchain += 1
                break

        if block_has_pqc:
            blocks_with_pqc += 1

    # Final DAG snapshot
    final_snap = snapshot_dag(NUM_NODES)

    # ── 10. PQC sig cache stats ────────────────────────────────────────
    print(f"\n[10/10] Collecting PQC signature cache stats...")
    sigcache = {}
    try:
        sigcache = node_cli_json(0, "getpqcsigcachestats")
    except Exception:
        pass

    # ── REPORT ─────────────────────────────────────────────────────────
    wall_elapsed = time.time() - wall_start
    succeeded = ecdsa_count + mldsa_count
    total_sent = succeeded + txs_failed + txs_insuff

    print(f"\n{'=' * 76}")
    print(f"  HIGH-THROUGHPUT MULTI-MINER DAG STRESS TEST REPORT")
    print(f"  90% ECDSA / 10% ML-DSA | {NUM_NODES} concurrent miners")
    print(f"{'=' * 76}")

    # ── Network ────────────────────────────────────────────────────────
    print(f"\n── Network ─────────────────────────────────────────────────")
    print(f"  Nodes:              {NUM_NODES} (all mining)")
    print(f"    Classical (ECDSA): {NUM_NODES - 1} nodes")
    print(f"    Hybrid (ML-DSA):   1 node (node 0)")
    print(f"  Wallets:            {total_wallets} ({WALLETS_PER_NODE}/node)")

    for nid in range(NUM_NODES):
        mode = NODES[nid]["pqcmode"]
        try:
            peers = len(node_cli_json(nid, "getpeerinfo"))
            inf = node_cli_json(nid, "getblockchaininfo")
            h = inf["blocks"]
            dt = inf.get("dag_tips", "?")
            mp = len(node_cli_json(nid, "getrawmempool"))
            print(f"  Node {nid:>2} [{mode:>9}]: height={h} dag_tips={dt} peers={peers} "
                  f"mempool={mp} sent={per_node_sent.get(nid,0):,} "
                  f"mined={per_node_mined.get(nid,0)}")
        except Exception:
            print(f"  Node {nid:>2} [{mode:>9}]: (unreachable)")

    # ── DAG / GHOSTDAG ─────────────────────────────────────────────────
    print(f"\n── DAG / GHOSTDAG Analysis ─────────────────────────────────")
    print(f"  Concurrent mining rounds: {parallel_mine_rounds}")
    print(f"  Max DAG tips observed:    {max_dag_tips_seen}")
    print(f"  Multi-parent blocks:      {multi_parent_blocks}/{blocks_scanned} "
          f"({multi_parent_blocks/blocks_scanned*100:.1f}%)" if blocks_scanned > 0 else "")
    print(f"  Total mergeset blues:     {total_mergeset_blues}")
    print(f"  Total mergeset reds:      {total_mergeset_reds}")

    # Best tip DAG info
    try:
        best_hash = node_cli(0, "getbestblockhash")
        best_hdr = node_cli_json(0, "getblockheader", best_hash)
        print(f"  Best tip blue_score:      {best_hdr.get('blue_score', 'N/A')}")
        print(f"  Best tip blue_work:       {best_hdr.get('blue_work', 'N/A')}")
        print(f"  Best tip dagparents:      {len(best_hdr.get('dagparents', []))}")
        print(f"  Best tip selected_parent: {str(best_hdr.get('selected_parent', 'N/A'))[:20]}...")
    except Exception:
        pass

    # DAG snapshots summary
    if dag_snapshots:
        all_tips = [max(s["dag_tips"]) for s in dag_snapshots if s["dag_tips"]]
        if all_tips:
            print(f"  DAG tips over time:       min={min(all_tips)} avg={mean(all_tips):.1f} "
                  f"max={max(all_tips)} ({len(dag_snapshots)} snapshots)")
        all_bs = [max(s["blue_scores"]) for s in dag_snapshots if s["blue_scores"]]
        if all_bs:
            print(f"  Blue score progression:   {min(all_bs)} → {max(all_bs)}")

    # ── Mining distribution ────────────────────────────────────────────
    print(f"\n── Mining Distribution ─────────────────────────────────────")
    print(f"  Total blocks mined:     {blocks_mined}")
    print(f"  Final height:           {final_height}")
    print(f"  {'Node':<8} {'Blocks':>8} {'Pct':>8} {'Txs Sent':>10}")
    for nid in range(NUM_NODES):
        nm = per_node_mined.get(nid, 0)
        pct = nm / blocks_mined * 100 if blocks_mined > 0 else 0
        ns = per_node_sent.get(nid, 0)
        mode = "MLd" if nid == 0 else "ECD"
        print(f"  Node {nid:<2} [{mode}] {nm:>6} {pct:>7.1f}% {ns:>10,}")

    # ── Signature Mix ──────────────────────────────────────────────────
    print(f"\n── Signature Mix ───────────────────────────────────────────")
    print(f"  TARGET:             90% ECDSA / 10% ML-DSA")
    if succeeded > 0:
        actual_ecdsa_pct = ecdsa_count / succeeded * 100
        actual_mldsa_pct = mldsa_count / succeeded * 100
        print(f"  ACTUAL:             {actual_ecdsa_pct:.1f}% ECDSA / {actual_mldsa_pct:.1f}% ML-DSA")
    print(f"  ECDSA txs sent:     {ecdsa_count:,}")
    print(f"  ML-DSA txs sent:    {mldsa_count:,}")
    if pqc_onchain + ecdsa_onchain > 0:
        pqc_pct = pqc_onchain / (pqc_onchain + ecdsa_onchain) * 100
        print(f"  On-chain ECDSA:     {ecdsa_onchain:,}")
        print(f"  On-chain ML-DSA:    {pqc_onchain:,} ({pqc_pct:.1f}%)")
        print(f"  Blocks with PQC:    {blocks_with_pqc}/{blocks_scanned}")

    # ── Transaction Summary ────────────────────────────────────────────
    print(f"\n── Transaction Summary ──────────────────────────────────────")
    print(f"  Attempted:          {total_sent:,}")
    real_attempts = succeeded + txs_failed  # excluding insuff-funds skips
    if real_attempts > 0:
        print(f"  Succeeded:          {succeeded:,} ({succeeded/real_attempts*100:.1f}% of viable)")
    print(f"  Failed (real):      {txs_failed:,}")
    print(f"  Skipped (no UTXO):  {txs_insuff:,}")
    print(f"  Confirmed on-chain: {txs_confirmed:,}")

    # ── Throughput ─────────────────────────────────────────────────────
    print(f"\n── Throughput ──────────────────────────────────────────────")
    print(f"  Total wall time:    {wall_elapsed:.0f}s ({wall_elapsed/60:.1f}m)")
    print(f"  TX phase duration:  {test_elapsed:.0f}s ({test_elapsed/60:.1f}m)")
    if test_elapsed > 0 and succeeded > 0:
        print(f"  Effective TPS:      {succeeded/test_elapsed:.1f} tx/s")
    if tx_times:
        print(f"  Submit latency:")
        print(f"    Mean:             {mean(tx_times)*1000:.1f} ms")
        print(f"    Median:           {median(tx_times)*1000:.1f} ms")
        print(f"    P95:              {percentile(tx_times, 95)*1000:.1f} ms")
        print(f"    P99:              {percentile(tx_times, 99)*1000:.1f} ms")
        print(f"    Min:              {min(tx_times)*1000:.1f} ms")
        print(f"    Max:              {max(tx_times)*1000:.1f} ms")

    # ── Transaction Sizes ──────────────────────────────────────────────
    print(f"\n── Transaction Sizes ───────────────────────────────────────")
    if tx_vsizes:
        print(f"  Sampled:            {len(tx_vsizes)}")
        print(f"  vsize (vB):         mean={mean(tx_vsizes):.0f} med={median(tx_vsizes):.0f} "
              f"p95={percentile(tx_vsizes,95):.0f} max={max(tx_vsizes)}")
        print(f"  weight (WU):        mean={mean(tx_weights):.0f} med={median(tx_weights):.0f}")
        if tx_sizes:
            print(f"  raw size (bytes):   mean={mean(tx_sizes):.0f} max={max(tx_sizes)}")

    # ── Witness Analysis ───────────────────────────────────────────────
    print(f"\n── Witness Analysis ────────────────────────────────────────")
    if tx_witness_elems:
        four_e = sum(1 for e in tx_witness_elems if e >= 4)
        two_e = sum(1 for e in tx_witness_elems if e == 2)
        total_w = len(tx_witness_elems)
        if total_w > 0:
            print(f"  4-element (PQC):    {four_e} ({four_e/total_w*100:.1f}%)")
            print(f"  2-element (ECDSA):  {two_e} ({two_e/total_w*100:.1f}%)")
            print(f"  ML-DSA overhead:    ~{(2420+1312):.0f} bytes/input (sig=2420B + pubkey=1312B)")

    # ── PQC Signature Cache ────────────────────────────────────────────
    if sigcache:
        print(f"\n── PQC Signature Cache ─────────────────────────────────────")
        print(f"  ECDSA hits/misses:   {sigcache.get('ecdsa_hits',0)}/{sigcache.get('ecdsa_misses',0)}"
              f"  (hit rate: {sigcache.get('ecdsa_hit_rate',0):.1f}%)")
        print(f"  Dilithium hits/miss: {sigcache.get('dilithium_hits',0)}/{sigcache.get('dilithium_misses',0)}"
              f"  (hit rate: {sigcache.get('dilithium_hit_rate',0):.1f}%)")

    # ── Storage ────────────────────────────────────────────────────────
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

    # ── Errors ─────────────────────────────────────────────────────────
    if errors:
        print(f"\n── Errors ({len(errors)}) ──────────────────────────────────────────")
        for e in errors[:20]:
            print(f"  {e}")
        if len(errors) > 20:
            print(f"  ... ({len(errors)-20} more)")

    # ── Verdict ────────────────────────────────────────────────────────
    mix_ok = True
    if succeeded > 100:
        actual_mldsa_pct = mldsa_count / succeeded * 100
        if actual_mldsa_pct < 5 or actual_mldsa_pct > 20:
            mix_ok = False

    dag_ok = multi_parent_blocks > 0 or max_dag_tips_seen > 1

    status = "PASSED"
    issues = []
    # Real failures exclude UTXO exhaustion which is expected in high-throughput stress
    real_attempts = succeeded + txs_failed
    if real_attempts > 0 and txs_failed >= real_attempts * 0.05:
        issues.append(f"high failure rate ({txs_failed}/{real_attempts} real errors)")
    if txs_insuff > total_sent * 0.3:
        issues.append(f"UTXO starvation ({txs_insuff:,} skipped)")
    if not mix_ok:
        issues.append(f"sig mix off target ({actual_mldsa_pct:.1f}% ML-DSA)")
    if not dag_ok:
        issues.append("no DAG parallelism observed")
    if issues:
        status = "COMPLETED WITH ISSUES: " + "; ".join(issues)

    print(f"\n{'=' * 76}")
    print(f"  TEST {status}")
    print(f"  {succeeded:,}/{total_sent:,} txs | ECDSA={ecdsa_count:,} ML-DSA={mldsa_count:,}")
    print(f"  {NUM_NODES} miners | {blocks_mined} blocks | height {final_height} | "
          f"max DAG tips {max_dag_tips_seen}")
    print(f"  {parallel_mine_rounds} parallel mine rounds | "
          f"{multi_parent_blocks} multi-parent blocks | {wall_elapsed/60:.1f}m")
    print(f"{'=' * 76}")

    cleanup()
    return 0 if status == "PASSED" else 1

if __name__ == "__main__":
    sys.exit(main())
