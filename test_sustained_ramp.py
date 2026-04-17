#!/usr/bin/env python3
"""
QuantBTC Sustained 30-Minute Ramp Test
========================================
Simulates a gradually growing Falcon-hybrid testnet with a full TPS ramp:

  t=0 min   : Node 1 starts, mines 200 blocks (chain bootstrap)
  t=2 min   : Node 2 joins — 10 wallets total, ~5 tx/s
  t=6 min   : Node 3 joins — 15 wallets,      ~15 tx/s
  t=10 min  : Node 4 joins — 20 wallets,       ~25 tx/s
  t=14 min  : Node 5 joins — 25 wallets,       ~35 tx/s
  t=18 min  : Peak — all 5 miners,             ~50 tx/s
  t=24 min  : Ramp-down begins               ~25 tx/s
  t=27 min  : Cool-down                       ~10 tx/s
  t=29 min  : Floor                            ~5 tx/s
  t=30 min  : Final assertions + report

Usage:
  python3 test_sustained_ramp.py          # 30-minute full run
  python3 test_sustained_ramp.py --fast   # ~4-minute smoke test (scaled)
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import time
import threading

# ── Binary paths ───────────────────────────────────────────────────────────────

BITCOIND = "./build-fresh/src/bitcoind"
CLI      = "./build-fresh/src/bitcoin-cli"
BASE_DIR = os.path.join(os.environ.get("TMPDIR", "/tmp"), "qbtc_sustained_ramp")

NODES = [
    {"id": 1, "rpc": 19811, "p2p": 19911},
    {"id": 2, "rpc": 19812, "p2p": 19912},
    {"id": 3, "rpc": 19813, "p2p": 19913},
    {"id": 4, "rpc": 19814, "p2p": 19914},
    {"id": 5, "rpc": 19815, "p2p": 19915},
]

WALLETS_PER_NODE = 5
RPCUSER  = "qbtctest"
RPCPASS  = "qbtctest"

# ── ANSI colours ───────────────────────────────────────────────────────────────

RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Globals ────────────────────────────────────────────────────────────────────

procs        = {}
addresses    = {}          # (nid, wname) -> address
tx_count     = 0
tx_lock      = threading.Lock()
stop_flag    = threading.Event()
results      = []
tps_log      = []          # [(elapsed_s, tps, height, mempool_size)]
current_interval = threading.Event()  # used to signal interval changes
_tx_interval = [2.0]       # mutable box for tx sleep interval

def log(level, msg):
    ts = time.strftime("%H:%M:%S")
    colours = {"INFO": CYAN, "OK": GREEN, "WARN": YELLOW, "ERR": RED, "HEAD": BOLD}
    c = colours.get(level, "")
    print(f"  {c}[{ts}][{level}]{RESET} {msg}", flush=True)

def record(name, ok, detail=""):
    results.append((name, ok, detail))
    tag = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
    log("OK" if ok else "ERR", f"[{tag}] {name}" + (f" — {detail}" if detail else ""))

# ── Node management ────────────────────────────────────────────────────────────

def node_datadir(nid):
    return os.path.join(BASE_DIR, f"node{nid}")

def cli_raw(nid, *args, wallet=None):
    node = NODES[nid - 1]
    base = [
        CLI, f"-datadir={node_datadir(nid)}", "-regtest",
        f"-rpcport={node['rpc']}", f"-rpcuser={RPCUSER}", f"-rpcpassword={RPCPASS}",
    ]
    if wallet:
        base += [f"-rpcwallet={wallet}"]
    r = subprocess.run(base + list(args), capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def cli(nid, *args, wallet=None):
    rc, out, err = cli_raw(nid, *args, wallet=wallet)
    if rc != 0:
        raise RuntimeError(f"Node {nid} CLI ({args[0]}): {err[:200]}")
    return out

def cli_json(nid, *args, wallet=None):
    return json.loads(cli(nid, *args, wallet=wallet))

def wait_ready(nid, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            cli(nid, "getblockchaininfo")
            return True
        except Exception:
            time.sleep(0.5)
    return False

def start_node(nid):
    node = NODES[nid - 1]
    datadir = node_datadir(nid)
    os.makedirs(f"{datadir}/regtest", exist_ok=True)
    cmd = [
        BITCOIND,
        f"-datadir={datadir}", "-regtest",
        f"-rpcport={node['rpc']}", f"-rpcuser={RPCUSER}", f"-rpcpassword={RPCPASS}",
        f"-port={node['p2p']}", f"-bind=127.0.0.1:{node['p2p']}",
        "-pqc=1", "-pqcsig=falcon",
        "-fallbackfee=0.0001", "-maxtxfee=1.0",
        "-listen=1", "-nodebug", "-server=1",
        "-mempoolfullrbf=1",
    ]
    if nid > 1:
        cmd += [f"-addnode=127.0.0.1:{NODES[0]['p2p']}"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs[nid] = proc
    log("INFO", f"Node {nid} started (pid={proc.pid}, rpc={node['rpc']}, p2p={node['p2p']})")
    return proc

def stop_node(nid):
    try:
        cli(nid, "stop")
        procs[nid].wait(timeout=15)
    except Exception:
        try:
            procs[nid].terminate()
            procs[nid].wait(timeout=5)
        except Exception:
            pass

def stop_all():
    log("INFO", "Stopping all nodes...")
    for nid in sorted(procs.keys(), reverse=True):
        try:
            stop_node(nid)
        except Exception:
            pass
    shutil.rmtree(BASE_DIR, ignore_errors=True)

# ── Wallet helpers ─────────────────────────────────────────────────────────────

def setup_wallet(nid, wname):
    """Create one wallet, return address."""
    try:
        cli_json(nid, "createwallet", wname)
    except Exception:
        pass
    addr = cli(nid, "getnewaddress", wallet=wname)
    addresses[(nid, wname)] = addr
    return addr

def get_balance(nid, wname):
    try:
        info = cli_json(nid, "getbalances", wallet=wname)
        return float(info.get("mine", {}).get("trusted", 0))
    except Exception:
        return 0.0

def mine_block(nid, wname):
    addr = addresses.get((nid, wname))
    if not addr:
        return 0
    try:
        result = cli_json(nid, "generatetoaddress", "1", addr, wallet=wname)
        return len(result)
    except Exception:
        return 0

def get_mempool_size(nid=1):
    try:
        return cli_json(nid, "getmempoolinfo")["size"]
    except Exception:
        return 0

def get_height(nid=1):
    try:
        return cli_json(nid, "getblockcount")
    except Exception:
        return 0

# ── Background workers ─────────────────────────────────────────────────────────

def tx_worker(active_wallets_ref):
    """Continuously sends transactions. Rate controlled by _tx_interval[0]."""
    global tx_count
    log("INFO", "Transaction worker started")
    while not stop_flag.is_set():
        pool = list(active_wallets_ref)
        if len(pool) < 2:
            time.sleep(0.5)
            continue
        try:
            src_nid, src_wname = random.choice(pool)
            dst_nid, dst_wname = random.choice(pool)
            if (src_nid, src_wname) == (dst_nid, dst_wname):
                time.sleep(0.1)
                continue
            bal = get_balance(src_nid, src_wname)
            if bal < 0.005:
                time.sleep(0.2)
                continue
            amount = round(random.uniform(0.001, min(0.05, bal * 0.15)), 6)
            dst_addr = addresses.get((dst_nid, dst_wname))
            if not dst_addr:
                continue
            cli(src_nid, "sendtoaddress", dst_addr, str(amount), wallet=src_wname)
            with tx_lock:
                tx_count += 1
        except Exception:
            pass
        time.sleep(max(0.01, _tx_interval[0]))

def mining_worker(active_miners_ref, interval_ref):
    """Rotate mining among active nodes at variable interval."""
    while not stop_flag.is_set():
        pool = list(active_miners_ref)
        if not pool:
            time.sleep(1)
            continue
        nid, wname = random.choice(pool)
        mine_block(nid, wname)
        time.sleep(max(0.5, interval_ref[0]))

# ── TPS scheduling ─────────────────────────────────────────────────────────────

def tps_to_interval(tps):
    """Convert target tx/s to sleep interval between tx attempts."""
    # We can't guarantee exactly N tx/s due to balance constraints,
    # but we can tune the sending interval to approach the target.
    return max(0.02, 1.0 / max(tps, 0.1))

# Ramp schedule: list of (elapsed_s, target_tps, mine_interval_s, description)
# Full 30-minute schedule (1800s total)
FULL_SCHEDULE = [
    # elapsed,  tps,  mine_s,  label
    (   0,     5,   8.0,  "bootstrap: 1 miner, 5 wallets — 5 tx/s"),
    ( 120,     5,   6.0,  "node 2 joined: 10 wallets — 5 tx/s"),
    ( 360,    15,   4.0,  "node 3 joined: 15 wallets — 15 tx/s"),
    ( 600,    25,   3.0,  "node 4 joined: 20 wallets — 25 tx/s"),
    ( 840,    35,   2.0,  "node 5 joined: 25 wallets — 35 tx/s"),
    (1080,    50,   1.5,  "PEAK: all miners, 25 wallets — 50 tx/s"),
    (1440,    25,   2.0,  "ramp-down: 25 tx/s"),
    (1620,    10,   3.0,  "cool-down: 10 tx/s"),
    (1740,     5,   5.0,  "floor: 5 tx/s"),
]

# Fast (4-minute smoke test, ~4x compressed = 240s)
FAST_SCHEDULE = [
    (  0,    5,   8.0,  "bootstrap: 1 miner, 5 wallets — 5 tx/s"),
    ( 15,    5,   6.0,  "node 2 joined: 10 wallets — 5 tx/s"),
    ( 45,   15,   4.0,  "node 3 joined: 15 wallets — 15 tx/s"),
    ( 75,   25,   3.0,  "node 4 joined: 20 wallets — 25 tx/s"),
    (105,   35,   2.0,  "node 5 joined: 25 wallets — 35 tx/s"),
    (135,   50,   1.5,  "PEAK: all miners, 25 wallets — 50 tx/s"),
    (180,   25,   2.0,  "ramp-down: 25 tx/s"),
    (205,   10,   3.0,  "cool-down: 10 tx/s"),
    (220,    5,   5.0,  "floor: 5 tx/s"),
]

# Node joins at these elapsed-second marks
FULL_NODE_JOINS  = {0: 1, 120: 2, 360: 3, 600: 4, 840: 5}
FAST_NODE_JOINS  = {0: 1,  15: 2,  45: 3,  75: 4, 105: 5}

def phase_banner(desc):
    log("HEAD", f"\n{'='*60}")
    log("HEAD", f"  {desc}")
    log("HEAD", f"{'='*60}")

# ── Main ───────────────────────────────────────────────────────────────────────

def run(fast=False):
    global tx_count

    schedule    = FAST_SCHEDULE if fast else FULL_SCHEDULE
    node_joins  = FAST_NODE_JOINS if fast else FULL_NODE_JOINS
    total_s     = schedule[-1][0] + (15 if fast else 60)  # 15s/60s floor period

    if os.path.exists(BASE_DIR):
        shutil.rmtree(BASE_DIR)
    os.makedirs(BASE_DIR, exist_ok=True)

    start_ts = time.time()

    active_miners  = []   # [(nid, wname), ...]
    active_wallets = []   # [(nid, wname), ...]
    mine_interval  = [8.0]

    # Joined node IDs
    joined = set()

    def elapsed():
        return time.time() - start_ts

    def join_node(nid, height_ref):
        """Bootstrap a new node, fund its wallets, add to active lists."""
        phase_banner(f"Node {nid} joins network (t+{elapsed():.0f}s)")

        start_node(nid)
        ok = wait_ready(nid, 60)
        record(f"Node {nid} starts", ok, "rpc responsive")
        if not ok:
            return

        # Connect to node 1
        if nid > 1:
            try:
                cli(nid, "addnode", f"127.0.0.1:{NODES[0]['p2p']}", "add")
            except Exception:
                pass
            time.sleep(3)
            # Wait for sync
            for _ in range(30):
                try:
                    if cli_json(nid, "getblockcount") >= height_ref[0]:
                        break
                except Exception:
                    pass
                time.sleep(1)
            synced_h = get_height(nid)
            record(f"Node {nid} synced", synced_h >= height_ref[0],
                   f"height={synced_h}")
            peer_count = 0
            try:
                peer_count = cli_json(nid, "getconnectioncount")
            except Exception:
                pass
            record(f"Node {nid} has peers", peer_count > 0, f"peers={peer_count}")

        # Set up wallets
        log("INFO", f"Creating wallets on node {nid}...")
        miner_wname = f"n{nid}w1"
        setup_wallet(nid, miner_wname)
        active_miners.append((nid, miner_wname))
        active_wallets.append((nid, miner_wname))

        for i in range(2, WALLETS_PER_NODE + 1):
            wname = f"n{nid}w{i}"
            addr = setup_wallet(nid, wname)
            active_wallets.append((nid, wname))

        # Fund wallets from node 1's miner
        if nid > 1:
            log("INFO", f"Funding node {nid} wallets from node 1...")
            miner_bal = get_balance(1, "n1w1")
            per_wallet = min(5.0, miner_bal / (WALLETS_PER_NODE * 2 + 1))
            if per_wallet > 0.5:
                for i in range(1, WALLETS_PER_NODE + 1):
                    wname = f"n{nid}w{i}"
                    addr = addresses.get((nid, wname))
                    if addr:
                        try:
                            cli(1, "sendtoaddress", addr, str(round(per_wallet, 4)),
                                wallet="n1w1")
                        except Exception:
                            pass
                # Mine to confirm funding
                mine_block(1, "n1w1")
                mine_block(1, "n1w1")
                height_ref[0] = get_height(1)
                log("INFO", f"Funding confirmed at height {height_ref[0]}")

        joined.add(nid)
        log("INFO", f"Node {nid} fully joined. "
            f"Active miners: {len(active_miners)}, wallets: {len(active_wallets)}")

    try:
        # ── Phase 0: pre-launch ────────────────────────────────────────────────
        phase_banner("Phase 0: Node 1 bootstrap — mining 200 blocks")

        start_node(1)
        record("Node 1 starts", wait_ready(1, 60), "rpc responsive")

        addr1 = setup_wallet(1, "n1w1")
        active_miners.append((1, "n1w1"))
        active_wallets.append((1, "n1w1"))

        log("INFO", "Mining 200 initial blocks...")
        cli_json(1, "generatetoaddress", "200", addr1, wallet="n1w1")
        h = get_height(1)
        record("Initial 200 blocks mined", h >= 200, f"height={h}")

        # Fund node 1's remaining wallets
        for i in range(2, WALLETS_PER_NODE + 1):
            wname = f"n1w{i}"
            addr = setup_wallet(1, wname)
            active_wallets.append((1, wname))
            try:
                cli(1, "sendtoaddress", addr, "10.0", wallet="n1w1")
            except Exception:
                pass
        mine_block(1, "n1w1")
        mine_block(1, "n1w1")
        height_ref = [get_height(1)]
        log("INFO", f"Node 1 bootstrapped at height {height_ref[0]}")

        joined.add(1)

        # ── Start background workers ───────────────────────────────────────────
        _tx_interval[0] = tps_to_interval(5)

        tx_thread = threading.Thread(
            target=tx_worker, args=(active_wallets,), daemon=True)
        mine_thread = threading.Thread(
            target=mining_worker, args=(active_miners, mine_interval), daemon=True)

        tx_thread.start()
        mine_thread.start()

        # ── Main ramp loop ─────────────────────────────────────────────────────
        log("INFO", f"Starting ramp loop. Total duration: {total_s}s")

        schedule_idx = 0
        next_join_times = sorted(node_joins.items())  # [(elapsed_s, nid)]
        join_idx = 1  # start from node 2 (node 1 already joined)

        snap_interval = 10 if fast else 30
        last_snap = start_ts
        last_tx   = 0
        phase_start_elapsed = 0

        while elapsed() < total_s:
            now_e = elapsed()

            # ── Node joins ───────────────────────────────────────────────────
            while join_idx < len(next_join_times):
                join_at, nid = next_join_times[join_idx]
                if now_e >= join_at and nid not in joined:
                    join_node(nid, height_ref)
                    join_idx += 1
                    break
                elif now_e < join_at:
                    break
                else:
                    join_idx += 1

            # ── TPS schedule ─────────────────────────────────────────────────
            while schedule_idx + 1 < len(schedule):
                next_at = schedule[schedule_idx + 1][0]
                if now_e >= next_at:
                    schedule_idx += 1
                    target_tps, m_int, label = (
                        schedule[schedule_idx][1],
                        schedule[schedule_idx][2],
                        schedule[schedule_idx][3],
                    )
                    _tx_interval[0]  = tps_to_interval(target_tps)
                    mine_interval[0] = m_int
                    phase_start_elapsed = now_e
                    log("INFO", f"[t+{now_e:.0f}s] Ramp: {label}")
                else:
                    break

            # ── Progress snapshot ─────────────────────────────────────────────
            if time.time() - last_snap >= snap_interval:
                with tx_lock:
                    delta_tx = tx_count - last_tx
                    last_tx  = tx_count
                h     = get_height(1)
                mpool = get_mempool_size(1)
                tps   = round(delta_tx / snap_interval, 2)
                target_tps = schedule[schedule_idx][1]
                remaining  = max(0, total_s - now_e)
                tps_log.append((round(now_e), tps, h, mpool))
                log("INFO",
                    f"  t+{now_e:.0f}s | tps={tps:.1f} (target≈{target_tps}) | "
                    f"height={h} | mempool={mpool} | total_tx={tx_count} | "
                    f"miners={len(active_miners)} | wallets={len(active_wallets)} | "
                    f"remaining={remaining:.0f}s")
                last_snap = time.time()

            time.sleep(1)

        # ── Stop workers ───────────────────────────────────────────────────────
        stop_flag.set()

        # ── Final assertions ───────────────────────────────────────────────────
        phase_banner("Final Assertions")

        final_h = get_height(1)
        mpool   = get_mempool_size(1)

        # All nodes agree on tip
        hashes = set()
        for nid in joined:
            try:
                hashes.add(cli_json(nid, "getblockchaininfo")["bestblockhash"])
            except Exception:
                pass
        record("All joined nodes agree on chain tip",
               len(hashes) == 1, f"tip={list(hashes)[0][:20]}..." if hashes else "no tip")

        record("Chain grew during test", final_h > 202,
               f"height={final_h}")

        record("Total transactions sent", tx_count > 0,
               f"{tx_count} txs")

        tps_threshold = 5 if fast else 15
        max_tps = max((t[1] for t in tps_log), default=0)
        record(f"TPS reached ≥ {tps_threshold}", max_tps >= tps_threshold,
               f"max measured: {max_tps:.1f} tx/s")

        all_wallets_with_history = 0
        for nid_wname in active_wallets:
            nid, wname = nid_wname
            try:
                txs = cli_json(nid, "listtransactions", "*", "100", wallet=wname)
                if len(txs) > 0:
                    all_wallets_with_history += 1
            except Exception:
                pass
        record("Wallets with tx history",
               all_wallets_with_history >= len(active_wallets) * 0.8,
               f"{all_wallets_with_history}/{len(active_wallets)}")

        for nid in joined:
            try:
                info = cli_json(nid, "getpqcinfo")
                record(f"Node {nid} getpqcinfo",
                       info.get("scheme") == "falcon" and info.get("nist_level") == "1",
                       f"scheme={info.get('scheme')} nist_level={info.get('nist_level')}")
            except Exception as e:
                record(f"Node {nid} getpqcinfo", False, str(e))

        for nid in joined:
            try:
                h = get_height(nid)
                p = cli_json(nid, "getconnectioncount")
                record(f"Node {nid} alive at end", h >= 200,
                       f"height={h}, peers={p}")
            except Exception as e:
                record(f"Node {nid} alive at end", False, str(e))

    finally:
        stop_flag.set()
        stop_all()

    # ── Report ─────────────────────────────────────────────────────────────────
    elapsed_total = time.time() - start_ts
    print()
    print("=" * 70)
    print(f"  SUSTAINED RAMP TEST COMPLETE — {elapsed_total:.0f}s elapsed")
    print("=" * 70)

    print()
    print("  TPS RAMP LOG")
    print("  " + "-" * 60)
    print(f"  {'t+s':>6}  {'measured':>9}  {'height':>7}  {'mempool':>8}")
    for (t, tps, h, mp) in tps_log:
        bar_len = min(40, int(tps * 0.8))
        bar = "█" * bar_len
        print(f"  {t:>6}s  {tps:>8.1f}/s  {h:>7}  {mp:>8}  {bar}")

    print()
    print("  RAMP SCHEDULE")
    print("  " + "-" * 60)
    sched = FAST_SCHEDULE if fast else FULL_SCHEDULE
    for (t, tps, mi, label) in sched:
        print(f"  t+{t:>5}s  target={tps:>3} tx/s  mine_interval={mi:.1f}s  {label}")

    print()
    print("  RESULTS")
    print("  " + "-" * 60)
    passed = 0
    failed = 0
    for name, ok, detail in results:
        tag = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        d   = f" [{detail}]" if detail else ""
        print(f"  {tag} {name}{d}")
        if ok:
            passed += 1
        else:
            failed += 1

    print()
    total = passed + failed
    if failed == 0:
        print(f"  {GREEN}{BOLD}{passed}/{total} checks passed{RESET}")
        print(f"  {GREEN}{BOLD}ALL CHECKS PASSED{RESET}")
    else:
        print(f"  {RED}{BOLD}{failed} FAILED / {passed} passed / {total} total{RESET}")

    print("=" * 70)
    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QuantBTC Sustained Ramp Test")
    parser.add_argument("--fast", action="store_true",
                        help="Run compressed ~4-minute smoke test instead of 30 minutes")
    args = parser.parse_args()

    ok = run(fast=args.fast)
    sys.exit(0 if ok else 1)
