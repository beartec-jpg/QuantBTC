#!/usr/bin/env python3
"""
QuantumBTC Ramp Stress Test — 15-minute high-throughput with overload
=====================================================================
Traffic pattern:
  Phase 1 (0-5 min):   Ramp from 10% → 110% of max TPS
  Phase 2 (5-7 min):   Hold at 110% (overload) for 2 minutes
  Phase 3 (7-12 min):  Ramp down from 110% → 10%
  Phase 4 (12-15 min): Cool-down at 10%, verify chain convergence

All nodes mine concurrently → GHOSTDAG DAG stress.
90% ECDSA / 10% ML-DSA signature mix.
Parallel TX submission via ThreadPoolExecutor for realistic throughput.
"""

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
TMPBASE  = os.environ.get("TMPDIR", "/tmp")

NUM_NODES = 8
WALLETS_PER_NODE = 8      # 64 total wallets (was 5 → 40)
TOTAL_WALLETS = NUM_NODES * WALLETS_PER_NODE
ADDRS_PER_WALLET = 10     # more UTXOs per wallet
FUND_AMOUNT = 10.0
MLDSA_RATIO = 0.10

# Ramp parameters (seconds)
PHASE1_RAMP_UP   = 300   # 5 min
PHASE2_OVERLOAD  = 120   # 2 min at 110%
PHASE3_RAMP_DOWN = 300   # 5 min
PHASE4_COOLDOWN  = 180   # 3 min
TOTAL_DURATION   = PHASE1_RAMP_UP + PHASE2_OVERLOAD + PHASE3_RAMP_DOWN + PHASE4_COOLDOWN

ESTIMATED_MAX_TPS = 40.0   # will be calibrated
OVERLOAD_FACTOR = 1.10

# TX sender parallelism
TX_WORKERS = 48      # 3× more parallel senders (was 16)

# ── Global state ───────────────────────────────────────────────────────
node_procs = []
NODES = []
_lock = threading.Lock()

total_ok = 0
total_fail = 0
total_insuff = 0
total_ecdsa = 0
total_mldsa = 0
blocks_mined = 0
max_dag_tips = 0
per_node_sent = defaultdict(int)
per_node_mined = defaultdict(int)
phase_metrics = []

def cleanup():
    print("\n[CLEANUP] Stopping all nodes...")
    for p in node_procs:
        try: p.terminate()
        except: pass
    time.sleep(2)
    for p in node_procs:
        try: p.kill()
        except: pass

def cleanup_and_exit(signum, frame):
    cleanup()
    sys.exit(1)

signal.signal(signal.SIGINT, cleanup_and_exit)
signal.signal(signal.SIGTERM, cleanup_and_exit)

# ── CLI helpers ────────────────────────────────────────────────────────
def node_cli(nid, *args, wallet=None, timeout=60):
    n = NODES[nid]
    cmd = [CLI, f"-{CHAIN}", "-rpcuser=test", "-rpcpassword=test",
           f"-rpcport={n['rpc_port']}", f"-datadir={n['datadir']}"]
    if wallet:
        cmd.append(f"-rpcwallet={wallet}")
    cmd.extend(str(a) for a in args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip()[:300])
    return r.stdout.strip()

def node_cli_json(nid, *args, **kw):
    return json.loads(node_cli(nid, *args, **kw))

def mine(nid, n_blocks, addr):
    return node_cli_json(nid, "generatetoaddress", str(n_blocks), addr)

# ── Node management ───────────────────────────────────────────────────
def build_nodes():
    global NODES
    NODES = []
    for i in range(NUM_NODES):
        NODES.append({
            "id": i,
            "p2p_port": 30333 + i * 100,
            "rpc_port": 30332 + i * 100,
            "datadir": os.path.join(TMPBASE, f"qbtc-ramp-{i}"),
            "pqcmode": "hybrid" if i == 0 else "classical",
        })

def start_nodes():
    global node_procs
    for n in NODES:
        if os.path.exists(n["datadir"]):
            shutil.rmtree(n["datadir"])
        os.makedirs(n["datadir"], exist_ok=True)

        conf = os.path.join(n["datadir"], "bitcoin.conf")
        with open(conf, "w") as f:
            f.write(f"regtest=1\nserver=1\nrpcuser=test\nrpcpassword=test\n"
                    f"rpcallowip=127.0.0.0/8\npqc=1\npqcmode={n['pqcmode']}\n"
                    f"dag=1\nfallbackfee=0.0001\nlisten=1\nlistenonion=0\n"
                    f"i2pacceptincoming=0\ndiscover=0\ndnsseed=0\nfixedseeds=0\n"
                    f"maxconnections=50\ndbcache=300\nmaxmempool=500\n"
                    f"blockmaxweight=4000000\nblockmintxfee=0.00001\n"
                    f"limitancestorcount=500\nlimitancestorsize=5000\n"
                    f"limitdescendantcount=500\nlimitdescendantsize=5000\n"
                    f"[regtest]\nrpcport={n['rpc_port']}\nport={n['p2p_port']}\n"
                    f"bind=127.0.0.1:{n['p2p_port']}\nrpcbind=127.0.0.1:{n['rpc_port']}\n")

        proc = subprocess.Popen(
            [BITCOIND, f"-datadir={n['datadir']}", "-daemon=0", "-printtoconsole=0"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        node_procs.append(proc)
        mode = "ML-DSA" if n["pqcmode"] == "hybrid" else "ECDSA"
        print(f"  Node {n['id']:>2}: pid={proc.pid} rpc={n['rpc_port']} [{mode}]")

    print("  Waiting for nodes...")
    for nid in range(NUM_NODES):
        for _ in range(60):
            try:
                node_cli_json(nid, "getblockchaininfo")
                break
            except:
                time.sleep(1)
        else:
            print(f"  FATAL: Node {nid} failed to start")
            cleanup(); sys.exit(1)
    print(f"  All {NUM_NODES} nodes started ✓")

def connect_mesh():
    print(f"  Connecting {NUM_NODES}-node mesh...")
    for i in range(NUM_NODES):
        for j in range(NUM_NODES):
            if i != j:
                try: node_cli(i, "addnode", f"127.0.0.1:{NODES[j]['p2p_port']}", "onetry")
                except: pass
    time.sleep(5)
    peers = sum(len(node_cli_json(i, "getpeerinfo")) for i in range(NUM_NODES))
    print(f"  Mesh: avg {peers/NUM_NODES:.1f} peers/node ✓")
    time.sleep(3)  # let mesh stabilize

def wait_sync(timeout_s=120):
    for _ in range(timeout_s):
        hs = []
        for nid in range(NUM_NODES):
            try: hs.append(node_cli_json(nid, "getblockchaininfo")["blocks"])
            except: hs.append(-1)
        if len(set(hs)) == 1 and hs[0] >= 0:
            return hs[0]
        time.sleep(1)
    return max(hs) if hs else 0

# ── Concurrent mining ─────────────────────────────────────────────────
def mine_one(nid, addr, n_blocks=1):
    try:
        mine(nid, n_blocks, addr)
        with _lock:
            per_node_mined[nid] += n_blocks
        return n_blocks
    except:
        return 0

def parallel_mine(wallet_info, blocks_each=1):
    global blocks_mined, max_dag_tips
    mined = 0
    with ThreadPoolExecutor(max_workers=NUM_NODES) as pool:
        futs = []
        for nid in range(NUM_NODES):
            addr = wallet_info[nid * WALLETS_PER_NODE]["addrs"][0]
            futs.append(pool.submit(mine_one, nid, addr, blocks_each))
        for f in as_completed(futs):
            mined += f.result()
    with _lock:
        blocks_mined += mined
    try:
        tips = node_cli_json(0, "getblockchaininfo").get("dag_tips", 1)
        with _lock:
            if tips > max_dag_tips:
                max_dag_tips = tips
    except: pass
    return mined

# ── Traffic shaping ───────────────────────────────────────────────────
def get_target_tps(elapsed, max_tps):
    overload_tps = max_tps * OVERLOAD_FACTOR
    base_tps = max_tps * 0.10

    if elapsed < PHASE1_RAMP_UP:
        progress = elapsed / PHASE1_RAMP_UP
        return base_tps + (overload_tps - base_tps) * progress
    elif elapsed < PHASE1_RAMP_UP + PHASE2_OVERLOAD:
        return overload_tps
    elif elapsed < PHASE1_RAMP_UP + PHASE2_OVERLOAD + PHASE3_RAMP_DOWN:
        ramp_elapsed = elapsed - PHASE1_RAMP_UP - PHASE2_OVERLOAD
        progress = ramp_elapsed / PHASE3_RAMP_DOWN
        return overload_tps - (overload_tps - base_tps) * progress
    else:
        return base_tps

def get_phase_name(elapsed):
    if elapsed < PHASE1_RAMP_UP:
        return "RAMP-UP"
    elif elapsed < PHASE1_RAMP_UP + PHASE2_OVERLOAD:
        return "OVERLOAD"
    elif elapsed < PHASE1_RAMP_UP + PHASE2_OVERLOAD + PHASE3_RAMP_DOWN:
        return "RAMP-DOWN"
    else:
        return "COOL-DOWN"

# ── Parallel TX sender ────────────────────────────────────────────────
def send_one_tx(sender, dst, amt):
    """Send a single transaction. Returns (ok, is_mldsa, is_insuff)."""
    try:
        node_cli(sender["nid"], "sendtoaddress", dst, f"{amt:.8f}",
                 wallet=sender["name"], timeout=15)
        return (True, sender["mldsa"], False)
    except RuntimeError as e:
        err = str(e)
        if "Insufficient" in err or "too many" in err or "Amount exceeds" in err:
            return (False, sender["mldsa"], True)
        return (False, sender["mldsa"], False)

# ── Main ───────────────────────────────────────────────────────────────
def main():
    global total_ok, total_fail, total_insuff, total_ecdsa, total_mldsa
    global blocks_mined, ESTIMATED_MAX_TPS, max_dag_tips

    random.seed(int(time.time()))
    wall_start = time.time()

    print("=" * 76)
    print("  QuantumBTC RAMP STRESS TEST — 15-minute high-throughput")
    print(f"  {NUM_NODES} nodes (all mining) | 90% ECDSA / 10% ML-DSA")
    print(f"  Profile: Ramp 5m → Overload 2m (110%) → Ramp down 5m → Cool 3m")
    print(f"  TX workers: {TX_WORKERS} parallel senders")
    print("=" * 76)

    # ── 1. Start nodes ─────────────────────────────────────────────────
    print(f"\n[1/8] Starting {NUM_NODES} nodes...")
    build_nodes()
    start_nodes()

    info = node_cli_json(0, "getblockchaininfo")
    print(f"  Chain: {info.get('chain')} | DAG: {info.get('dagmode')} | PQC: {info.get('pqc')}")

    # ── 2. Mesh ────────────────────────────────────────────────────────
    print(f"\n[2/8] Mesh connectivity...")
    connect_mesh()

    # ── 3. Wallets ─────────────────────────────────────────────────────
    print(f"\n[3/8] Creating {TOTAL_WALLETS} wallets ({ADDRS_PER_WALLET} addrs each)...")
    wallet_info = []
    ecdsa_wallets = []
    mldsa_wallets = []

    for nid in range(NUM_NODES):
        is_mldsa = NODES[nid]["pqcmode"] == "hybrid"
        for w in range(WALLETS_PER_NODE):
            name = f"r{nid}w{w}"
            try: node_cli(nid, "createwallet", name)
            except:
                try: node_cli(nid, "loadwallet", name)
                except: pass
            addrs = []
            for _ in range(ADDRS_PER_WALLET):
                addrs.append(node_cli(nid, "getnewaddress", "", "bech32", wallet=name))
            entry = {"nid": nid, "name": name, "addrs": addrs, "mldsa": is_mldsa}
            wallet_info.append(entry)
            if is_mldsa:
                mldsa_wallets.append(entry)
            else:
                ecdsa_wallets.append(entry)

    print(f"  ECDSA wallets: {len(ecdsa_wallets)} | ML-DSA wallets: {len(mldsa_wallets)}")
    print(f"  Total addresses: {len(wallet_info) * ADDRS_PER_WALLET}")

    all_addrs = [addr for w in wallet_info for addr in w["addrs"]]

    # ── 4. Mine bootstrap + fund wallets ──────────────────────────────
    print(f"\n[4/8] Mining bootstrap + funding wallets...")
    bootstrap_addr = wallet_info[0]["addrs"][0]

    # Mine 600 blocks in batches of 100 on Node 0 with retry
    bootstrap_blocks = 600
    for batch_start in range(0, bootstrap_blocks, 100):
        batch_count = min(100, bootstrap_blocks - batch_start)
        for attempt in range(5):
            try:
                mine(0, batch_count, bootstrap_addr)
                blocks_mined += batch_count
                per_node_mined[0] += batch_count
                break
            except Exception as e:
                print(f"    Mine batch retry {attempt+1}: {str(e)[:80]}")
                time.sleep(3)
        else:
            print(f"    WARNING: Failed to mine batch at {batch_start}")

    # Wait for all nodes to sync after bootstrap
    for _ in range(180):
        try:
            hs = [node_cli_json(i, "getblockchaininfo")["blocks"] for i in range(NUM_NODES)]
            if min(hs) >= bootstrap_blocks - 10:
                break
        except: pass
        time.sleep(1)

    height = node_cli_json(0, "getblockchaininfo")["blocks"]
    print(f"  Bootstrap: {blocks_mined} blocks, height={height}")

    # Fund via sendtoaddress from node 0's funder wallet
    funder = wallet_info[0]["name"]
    funder_bal = float(node_cli(0, "getbalance", wallet=funder))
    print(f"  Funder balance: {funder_bal:.2f} BTC")

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
                             f"{send_per_addr:.8f}", wallet=funder)
                    funded += 1
                except: pass
            # Mine every 20 sends to keep UTXO set fresh
            if funded > 0 and funded % 20 == 0:
                try:
                    mine(0, 2, bootstrap_addr)
                    blocks_mined += 2; per_node_mined[0] += 2
                except: pass
        # Confirm this round
        try:
            mine(0, 10, bootstrap_addr)
            blocks_mined += 10; per_node_mined[0] += 10
        except: pass
        wait_sync(timeout_s=60)
        print(f"  Round {rnd+1}/{fund_rounds}: {funded} sends")

    # Extra maturity mining
    try:
        mine(0, 10, bootstrap_addr)
        blocks_mined += 10; per_node_mined[0] += 10
    except: pass
    wait_sync(timeout_s=60)

    # Verify
    total_bal = 0
    wallets_with_bal = 0
    for w in wallet_info:
        try:
            bal = float(node_cli(w["nid"], "getbalance", wallet=w["name"], timeout=10))
            if bal > 1.0:
                wallets_with_bal += 1
                total_bal += bal
        except: pass

    height = node_cli_json(0, "getblockchaininfo")["blocks"]
    print(f"  {wallets_with_bal}/{TOTAL_WALLETS} wallets funded | "
          f"Total: {total_bal:.0f} BTC | Height: {height}")

    if wallets_with_bal < 10:
        print("  FATAL: Not enough funded wallets. Aborting.")
        cleanup(); sys.exit(1)

    # ── 5. Calibrate max TPS ───────────────────────────────────────────
    print(f"\n[5/8] Calibrating max TPS (parallel burst of 500 tx)...")
    cal_tasks = []
    for _ in range(500):
        use_mldsa = random.random() < MLDSA_RATIO
        pool = mldsa_wallets if (use_mldsa and mldsa_wallets) else ecdsa_wallets
        sender = random.choice(pool)
        dst = random.choice(all_addrs)
        amt = round(random.uniform(0.00001, 0.005), 8)
        cal_tasks.append((sender, dst, amt))

    cal_start = time.time()
    cal_ok = 0
    with ThreadPoolExecutor(max_workers=TX_WORKERS) as pool:
        futs = [pool.submit(send_one_tx, s, d, a) for s, d, a in cal_tasks]
        for f in as_completed(futs):
            ok, _, _ = f.result()
            if ok:
                cal_ok += 1
    cal_elapsed = time.time() - cal_start

    if cal_elapsed > 0 and cal_ok > 20:
        ESTIMATED_MAX_TPS = cal_ok / cal_elapsed
    ESTIMATED_MAX_TPS = max(20.0, min(200.0, ESTIMATED_MAX_TPS))

    parallel_mine(wallet_info, blocks_each=3)
    wait_sync(timeout_s=30)
    print(f"  Calibrated: {ESTIMATED_MAX_TPS:.1f} TPS ({cal_ok}/500 in {cal_elapsed:.1f}s)")
    print(f"  Overload target: {ESTIMATED_MAX_TPS * OVERLOAD_FACTOR:.1f} TPS (110%)")

    # ── 6. RAMP STRESS TEST ────────────────────────────────────────────
    print(f"\n[6/8] Starting 15-minute ramp stress test...")
    print(f"  Max: {ESTIMATED_MAX_TPS:.1f} | Overload: {ESTIMATED_MAX_TPS*OVERLOAD_FACTOR:.1f} TPS")
    print(f"  Phases: Ramp 5m → Overload 2m → Ramp-down 5m → Cool 3m")
    print()

    test_start = time.time()
    report_interval = 10.0
    last_report = test_start
    mine_thread_stop = threading.Event()

    def bg_miner():
        while not mine_thread_stop.is_set():
            try:
                parallel_mine(wallet_info, blocks_each=1)
            except: pass
            mine_thread_stop.wait(1.5)  # slower mining → more tx per block

    miner_t = threading.Thread(target=bg_miner, daemon=True)
    miner_t.start()

    # Wallet balance cache
    wallet_bal = {}
    for w in wallet_info:
        try: wallet_bal[w["name"]] = float(node_cli(w["nid"], "getbalance", wallet=w["name"], timeout=10))
        except: wallet_bal[w["name"]] = 0

    tx_pool = ThreadPoolExecutor(max_workers=TX_WORKERS)

    interval_ok = 0
    interval_fail = 0
    interval_insuff = 0
    interval_start = time.time()

    while True:
        elapsed = time.time() - test_start
        if elapsed >= TOTAL_DURATION:
            break

        target_tps = get_target_tps(elapsed, ESTIMATED_MAX_TPS)
        phase = get_phase_name(elapsed)

        # Submit batch for ~1 second worth of TX
        tx_this_second = max(1, int(target_tps))

        batch_futs = []
        for _ in range(tx_this_second):
            use_mldsa = random.random() < MLDSA_RATIO
            src_pool = mldsa_wallets if (use_mldsa and mldsa_wallets) else ecdsa_wallets
            candidates = [w for w in src_pool if wallet_bal.get(w["name"], 0) > 0.01]
            if not candidates:
                candidates = src_pool
            sender = random.choice(candidates)
            dst = random.choice(all_addrs)
            amt = round(random.uniform(0.00001, 0.003), 8)
            f = tx_pool.submit(send_one_tx, sender, dst, amt)
            batch_futs.append(f)

        for f in as_completed(batch_futs):
            ok, is_mldsa, is_insuff = f.result()
            with _lock:
                if ok:
                    total_ok += 1
                    interval_ok += 1
                    if is_mldsa:
                        total_mldsa += 1
                    else:
                        total_ecdsa += 1
                elif is_insuff:
                    total_insuff += 1
                    interval_insuff += 1
                else:
                    total_fail += 1
                    interval_fail += 1

        # Pace: sleep remainder of 1-second window
        batch_end = time.time()
        batch_duration = batch_end - (test_start + elapsed)
        sleep_time = max(0, 1.0 - batch_duration)
        if sleep_time > 0:
            time.sleep(sleep_time)

        # Periodic report
        now = time.time()
        if now - last_report >= report_interval:
            dt = now - interval_start
            actual_tps = interval_ok / dt if dt > 0 else 0

            tips = "?"
            height = "?"
            mempool = "?"
            try:
                info = node_cli_json(0, "getblockchaininfo")
                tips = info.get("dag_tips", 1)
                height = info["blocks"]
                with _lock:
                    if isinstance(tips, int) and tips > max_dag_tips:
                        max_dag_tips = tips
            except: pass
            try:
                mpi = node_cli_json(0, "getmempoolinfo")
                mempool = mpi.get("size", "?")
            except: pass

            pct = elapsed / TOTAL_DURATION * 100
            bar_len = 25
            bar_fill = int(bar_len * elapsed / TOTAL_DURATION)
            bar = "█" * bar_fill + "░" * (bar_len - bar_fill)

            phase_metrics.append({
                "time": elapsed, "phase": phase,
                "target_tps": target_tps, "actual_tps": actual_tps,
                "ok": interval_ok, "fail": interval_fail, "insuff": interval_insuff,
                "dag_tips": tips, "height": height, "mempool": mempool,
            })

            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            print(f"  {mins:02d}:{secs:02d} [{bar}] {pct:>5.1f}% "
                  f"{phase:<9} "
                  f"tgt={target_tps:>5.1f} act={actual_tps:>5.1f} "
                  f"ok={interval_ok:>4} fail={interval_fail} insf={interval_insuff} "
                  f"mp={mempool} tips={tips} h={height}")

            interval_ok = 0
            interval_fail = 0
            interval_insuff = 0
            interval_start = now
            last_report = now

            # Refresh balances periodically
            if int(elapsed) % 30 < report_interval + 1:
                for w in wallet_info:
                    try: wallet_bal[w["name"]] = float(
                        node_cli(w["nid"], "getbalance", wallet=w["name"], timeout=5))
                    except: pass

    mine_thread_stop.set()
    miner_t.join(timeout=30)
    tx_pool.shutdown(wait=False)
    test_elapsed = time.time() - test_start

    # ── 7. Final sync & analysis ───────────────────────────────────────
    print(f"\n[7/8] Final sync and analysis...")
    parallel_mine(wallet_info, blocks_each=3)
    time.sleep(5)
    final_height = wait_sync(timeout_s=120)

    hashes = []
    for nid in range(NUM_NODES):
        try: hashes.append(node_cli(nid, "getbestblockhash"))
        except: hashes.append("err")
    consensus = len(set(hashes)) == 1 and hashes[0] != "err"

    scan_start = max(1, final_height - 300)
    pqc_onchain = 0
    ecdsa_onchain = 0
    txs_confirmed = 0
    multi_parent = 0
    blocks_scanned = 0

    for h in range(scan_start, final_height + 1):
        try:
            bh = node_cli(0, "getblockhash", str(h))
            hdr = node_cli_json(0, "getblockheader", bh)
            blk = node_cli_json(0, "getblock", bh, "2")
            blocks_scanned += 1
            if len(hdr.get("dagparents", [])) > 0:
                multi_parent += 1
            for tx in blk.get("tx", []):
                if tx.get("vin", [{}])[0].get("coinbase"):
                    continue
                txs_confirmed += 1
                for vin in tx.get("vin", []):
                    wit = vin.get("txinwitness", [])
                    if len(wit) >= 4:
                        pqc_onchain += 1
                    elif len(wit) > 0:
                        ecdsa_onchain += 1
                    break
        except: pass

    # ── 8. REPORT ──────────────────────────────────────────────────────
    wall_elapsed = time.time() - wall_start
    succeeded = total_ok

    print(f"\n{'=' * 76}")
    print(f"  RAMP STRESS TEST REPORT")
    print(f"  {NUM_NODES} nodes | {TX_WORKERS} tx-workers | 90/10 ECDSA/ML-DSA")
    print(f"{'=' * 76}")

    print(f"\n── Calibration ─────────────────────────────────────────────")
    print(f"  Max TPS (measured):   {ESTIMATED_MAX_TPS:.1f}")
    print(f"  Overload target:      {ESTIMATED_MAX_TPS * OVERLOAD_FACTOR:.1f} (110%)")

    print(f"\n── Test Duration ───────────────────────────────────────────")
    print(f"  Stress test:          {test_elapsed:.0f}s ({test_elapsed/60:.1f}m)")
    print(f"  Total wall time:      {wall_elapsed:.0f}s ({wall_elapsed/60:.1f}m)")

    print(f"\n── Traffic Profile ─────────────────────────────────────────")
    print(f"  {'Time':>5} {'Phase':<9} {'Target':>6} {'Actual':>6} {'OK':>5} "
          f"{'Fail':>4} {'Insf':>4} {'Mempl':>5} {'Tips':>4} {'Height':>6}")
    print(f"  {'─'*5} {'─'*9} {'─'*6} {'─'*6} {'─'*5} {'─'*4} {'─'*4} {'─'*5} {'─'*4} {'─'*6}")
    for m in phase_metrics:
        mins = int(m["time"] // 60)
        secs = int(m["time"] % 60)
        print(f"  {mins:02d}:{secs:02d} {m['phase']:<9} {m['target_tps']:>6.1f} "
              f"{m['actual_tps']:>6.1f} {m['ok']:>5} "
              f"{m['fail']:>4} {m['insuff']:>4} {str(m['mempool']):>5} "
              f"{str(m['dag_tips']):>4} {str(m['height']):>6}")

    peak_actual = max((m["actual_tps"] for m in phase_metrics), default=0)
    peak_target = max((m["target_tps"] for m in phase_metrics), default=0)

    print(f"\n── Network ─────────────────────────────────────────────────")
    print(f"  Nodes:              {NUM_NODES} (all mining)")
    print(f"  Final height:       {final_height}")
    print(f"  Consensus:          {'YES ✓' if consensus else 'NO ✗ CHAIN SPLIT!'}")
    if not consensus:
        for nid, h in enumerate(hashes):
            print(f"    Node {nid}: {h[:20]}...")
    print(f"  Max DAG tips:       {max_dag_tips}")
    print(f"  Multi-parent blks:  {multi_parent}/{blocks_scanned} "
          f"({multi_parent/max(1,blocks_scanned)*100:.1f}%)")

    for nid in range(NUM_NODES):
        mode = "MLd" if nid == 0 else "ECD"
        try:
            inf = node_cli_json(nid, "getblockchaininfo")
            print(f"    N{nid} [{mode}] h={inf['blocks']} tips={inf.get('dag_tips','?')} "
                  f"tx-sent={per_node_sent.get(nid,0):,} mined={per_node_mined.get(nid,0)}")
        except:
            print(f"    N{nid} [{mode}] (unreachable)")

    print(f"\n── Signature Mix ───────────────────────────────────────────")
    print(f"  TARGET:             90% ECDSA / 10% ML-DSA")
    if succeeded > 0:
        print(f"  ACTUAL:             {total_ecdsa/succeeded*100:.1f}% ECDSA / "
              f"{total_mldsa/succeeded*100:.1f}% ML-DSA")
    print(f"  ECDSA sent:         {total_ecdsa:,}")
    print(f"  ML-DSA sent:        {total_mldsa:,}")
    if pqc_onchain + ecdsa_onchain > 0:
        print(f"  On-chain ECDSA:     {ecdsa_onchain:,}")
        print(f"  On-chain ML-DSA:    {pqc_onchain:,} "
              f"({pqc_onchain/(pqc_onchain+ecdsa_onchain)*100:.1f}%)")

    print(f"\n── Transaction Summary ──────────────────────────────────────")
    print(f"  Succeeded:          {succeeded:,}")
    print(f"  Failed (real):      {total_fail:,}")
    print(f"  Skipped (no UTXO):  {total_insuff:,}")
    print(f"  Confirmed on-chain: {txs_confirmed:,}")
    if test_elapsed > 0:
        print(f"  Overall avg TPS:    {succeeded/test_elapsed:.1f}")
    print(f"  Peak actual TPS:    {peak_actual:.1f}")
    print(f"  Peak target TPS:    {peak_target:.1f}")

    print(f"\n── Mining ──────────────────────────────────────────────────")
    print(f"  Total blocks:       {blocks_mined}")

    print(f"\n── Storage ─────────────────────────────────────────────────")
    total_mb = 0
    for nid in range(NUM_NODES):
        try:
            r = subprocess.run(["du", "-sm", NODES[nid]["datadir"]],
                              capture_output=True, text=True, timeout=10)
            mb = int(r.stdout.split()[0])
            total_mb += mb
        except: pass
    print(f"  Total: {total_mb} MB ({total_mb/1024:.2f} GB)")

    # ── Verdict ────────────────────────────────────────────────────────
    issues = []
    if not consensus:
        issues.append("CHAIN SPLIT")
    real = succeeded + total_fail
    if real > 0 and total_fail >= real * 0.05:
        issues.append(f"high fail rate ({total_fail}/{real})")
    if succeeded > 100:
        mldsa_pct = total_mldsa / succeeded * 100
        if mldsa_pct < 5 or mldsa_pct > 20:
            issues.append(f"sig mix off ({mldsa_pct:.1f}% ML-DSA)")

    status = "PASSED ✓" if not issues else "ISSUES: " + "; ".join(issues)

    print(f"\n{'=' * 76}")
    print(f"  VERDICT: {status}")
    print(f"  {succeeded:,} tx | ECDSA={total_ecdsa:,} ML-DSA={total_mldsa:,}")
    print(f"  {blocks_mined} blocks | h={final_height} | max-tips={max_dag_tips} | "
          f"consensus={'YES' if consensus else 'NO'}")
    print(f"  Peak: {peak_actual:.1f}/{peak_target:.1f} TPS | Duration: {wall_elapsed/60:.1f}m")
    print(f"{'=' * 76}")

    cleanup()
    return 0 if not issues else 1

if __name__ == "__main__":
    sys.exit(main())
