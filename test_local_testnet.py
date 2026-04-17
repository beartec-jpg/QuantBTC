#!/usr/bin/env python3
"""
QuantumBTC Local Testnet Simulation
=====================================
Simulates a gradually growing Falcon-hybrid testnet:

  t=0     : Node 1 starts, mines initial chain, opens 5 wallets
  t+phase : Node 2 starts, connects, adds 5 wallets
  t+2x    : Node 3 starts, connects, adds 5 wallets, joins mining
  t+3x    : Node 4 starts, connects, adds 5 wallets, joins mining
  t+4x    : Node 5 starts, connects, adds 5 wallets, joins mining
  final   : All 5 miners, 25 wallets transacting for remaining time

Total runtime: ~30 minutes by default (--fast for ~3-minute smoke test).

Usage:
  python3 test_local_testnet.py          # 30-minute full run
  python3 test_local_testnet.py --fast   # 3-minute smoke test
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

# ── Configuration ──────────────────────────────────────────────────────────────

BITCOIND = "./build-fresh/src/bitcoind"
CLI      = "./build-fresh/src/bitcoin-cli"
BASE_DIR = os.path.join(os.environ.get("TMPDIR", "/tmp"), "qbtc_testnet")

# 5 nodes: each gets unique RPC and P2P ports
NODES = [
    {"id": 1, "rpc": 19801, "p2p": 19901},
    {"id": 2, "rpc": 19802, "p2p": 19902},
    {"id": 3, "rpc": 19803, "p2p": 19903},
    {"id": 4, "rpc": 19804, "p2p": 19904},
    {"id": 5, "rpc": 19805, "p2p": 19905},
]

WALLETS_PER_NODE = 5
RPCUSER  = "qbtctest"
RPCPASS  = "qbtctest"

# Colours
RED    = "\033[91m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

# ── Globals ────────────────────────────────────────────────────────────────────

procs     = {}          # node_id -> Popen
addresses = {}          # (node_id, wallet_name) -> address
balances  = {}          # (node_id, wallet_name) -> last known balance
tx_count  = 0
tx_lock   = threading.Lock()
stop_flag = threading.Event()
results   = []

def log(level, msg):
    ts = time.strftime("%H:%M:%S")
    colours = {"INFO": CYAN, "OK": GREEN, "WARN": YELLOW, "ERR": RED, "HEAD": BOLD}
    c = colours.get(level, "")
    print(f"  {c}[{ts}][{level}]{RESET} {msg}")

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
        raise RuntimeError(f"Node {nid} CLI error ({args[0]}): {err[:120]}")
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
        f"-datadir={datadir}",
        "-regtest",
        f"-rpcport={node['rpc']}",
        f"-rpcuser={RPCUSER}",
        f"-rpcpassword={RPCPASS}",
        f"-port={node['p2p']}",
        f"-bind=127.0.0.1:{node['p2p']}",
        "-pqc=1",
        "-pqcsig=falcon",
        "-fallbackfee=0.0001",
        "-maxtxfee=1.0",
        "-txindex=0",
        "-listen=1",
        "-nodebug",
        "-server=1",
    ]
    # Connect to node 1 as the hub (except node 1 itself)
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
    for nid in sorted(procs.keys(), reverse=True):
        try:
            stop_node(nid)
        except Exception:
            pass
    shutil.rmtree(BASE_DIR, ignore_errors=True)

# ── Wallet helpers ─────────────────────────────────────────────────────────────

def setup_wallets(nid):
    """Create WALLETS_PER_NODE wallets on node nid, each with a Falcon address."""
    node_addrs = []
    for i in range(1, WALLETS_PER_NODE + 1):
        wname = f"n{nid}w{i}"
        try:
            cli_json(nid, "createwallet", wname)
        except Exception:
            pass  # already exists on reconnect

        # getnewaddress with bech32 — Falcon hybrid address
        try:
            addr = cli(nid, "getnewaddress", wallet=wname)
            addresses[(nid, wname)] = addr
            node_addrs.append((wname, addr))
            log("INFO", f"  Node {nid} wallet {wname}: {addr[:30]}...")
        except Exception as e:
            log("WARN", f"  Node {nid} wallet {wname} address failed: {e}")

    return node_addrs

def get_balance(nid, wname):
    try:
        info = cli_json(nid, "getbalances", wallet=wname)
        return float(info.get("mine", {}).get("trusted", 0))
    except Exception:
        return 0.0

def fund_wallets(nid, miner_wallet, all_wallet_addrs, amount=1.0):
    """Send small amounts from miner_wallet to all other wallets."""
    sent = 0
    for (wnode, wname), addr in all_wallet_addrs:
        if wnode == nid and wname == miner_wallet:
            continue
        try:
            cli(nid, "sendtoaddress", addr, str(amount), wallet=miner_wallet)
            sent += 1
        except Exception:
            pass
    return sent

# ── Mining ─────────────────────────────────────────────────────────────────────

def mine_blocks(nid, wname, count=1):
    addr = addresses.get((nid, wname))
    if not addr:
        return 0
    try:
        result = cli_json(nid, "generatetoaddress", str(count), addr, wallet=wname)
        return len(result)
    except Exception as e:
        log("WARN", f"mine_blocks({nid},{wname}): {e}")
        # Also try raw to get full error
        rc, out, err = cli_raw(nid, "generatetoaddress", str(count), addr, wallet=wname)
        if rc != 0:
            log("WARN", f"  raw error: {err[:500].replace(chr(10), ' | ')}")
        return 0

# ── Transaction storm ──────────────────────────────────────────────────────────

def tx_worker(active_wallets, interval):
    """Background thread: send random transactions between wallets."""
    global tx_count
    log("INFO", "Transaction worker started")
    while not stop_flag.is_set():
        if len(active_wallets) < 2:
            time.sleep(1)
            continue
        try:
            (src_nid, src_wname) = random.choice(active_wallets)
            (dst_nid, dst_wname) = random.choice(active_wallets)
            if (src_nid, src_wname) == (dst_nid, dst_wname):
                time.sleep(0.2)
                continue

            bal = get_balance(src_nid, src_wname)
            if bal < 0.01:
                time.sleep(0.5)
                continue

            amount = round(random.uniform(0.001, min(0.1, bal * 0.3)), 6)
            dst_addr = addresses.get((dst_nid, dst_wname))
            if not dst_addr:
                continue

            cli(src_nid, "sendtoaddress", dst_addr, str(amount), wallet=src_wname)
            with tx_lock:
                tx_count += 1
        except Exception:
            pass
        time.sleep(interval)

def mining_worker(active_miners, interval):
    """Background thread: rotate mining among active nodes."""
    while not stop_flag.is_set():
        if not active_miners:
            time.sleep(1)
            continue
        nid, wname = random.choice(active_miners)
        mine_blocks(nid, wname, 1)
        time.sleep(interval)

# ── Phase helpers ──────────────────────────────────────────────────────────────

def phase_banner(phase, description):
    log("HEAD", f"\n{'='*60}")
    log("HEAD", f"  PHASE {phase}: {description}")
    log("HEAD", f"{'='*60}")

def check_sync(nid_list):
    """Check all nodes have the same best block hash."""
    hashes = set()
    for nid in nid_list:
        try:
            info = cli_json(nid, "getblockchaininfo")
            hashes.add(info["bestblockhash"])
        except Exception:
            pass
    return len(hashes) <= 1, hashes

# ── Main test ─────────────────────────────────────────────────────────────────

def run(phase_duration, final_duration):
    global tx_count

    if os.path.exists(BASE_DIR):
        shutil.rmtree(BASE_DIR)
    os.makedirs(BASE_DIR, exist_ok=True)

    start_time = time.time()
    active_miners = []   # list of (nid, wname)
    active_wallets = []  # all (nid, wname) pairs with funded balances
    all_wallet_addrs = {}  # (nid, wname) -> addr  (for funding)

    try:
        # ──────────────────────────────────────────────────────────────────────
        phase_banner(1, "Node 1 starts — mines initial chain, opens 5 wallets")
        # ──────────────────────────────────────────────────────────────────────
        start_node(1)
        record("Node 1 starts", wait_ready(1, 60), "rpc responsive")

        # Mine enough blocks so coinbase is spendable (101)
        log("INFO", "Mining 200 blocks for initial chain + spendable coinbase...")
        cli_json(1, "createwallet", "n1w1")
        addr1 = cli(1, "getnewaddress", wallet="n1w1")
        addresses[(1, "n1w1")] = addr1
        cli_json(1, "generatetoaddress", "200", addr1, wallet="n1w1")
        height = cli_json(1, "getblockcount")
        record("Initial 200 blocks mined", height >= 200, f"height={height}")

        # Rest of node 1's wallets
        for i in range(2, WALLETS_PER_NODE + 1):
            wname = f"n1w{i}"
            cli_json(1, "createwallet", wname)
            addr = cli(1, "getnewaddress", wallet=wname)
            addresses[(1, wname)] = addr
            all_wallet_addrs[(1, wname)] = addr
        all_wallet_addrs[(1, "n1w1")] = addr1

        active_miners.append((1, "n1w1"))
        active_wallets = [(1, f"n1w{i}") for i in range(1, WALLETS_PER_NODE + 1)]

        # Fund wallets from coinbase
        log("INFO", "Funding node 1 wallets from coinbase...")
        for i in range(2, WALLETS_PER_NODE + 1):
            wname = f"n1w{i}"
            cli(1, "sendtoaddress", addresses[(1, wname)], "5.0", wallet="n1w1")
        mine_blocks(1, "n1w1", 2)

        log("INFO", f"Phase 1 complete. Waiting {phase_duration}s before next node...")
        time.sleep(phase_duration)

        # ──────────────────────────────────────────────────────────────────────
        # Phases 2–5: gradually bring up nodes 2-5
        # ──────────────────────────────────────────────────────────────────────
        for nid in range(2, 6):
            phase_banner(nid, f"Node {nid} joins — connects, opens 5 wallets, begins mining")

            start_node(nid)
            record(f"Node {nid} starts", wait_ready(nid, 30), "rpc responsive")

            # Connect to node 1
            try:
                cli(nid, "addnode", f"127.0.0.1:{NODES[0]['p2p']}", "add")
            except Exception:
                pass
            time.sleep(3)

            # Wait for sync
            log("INFO", f"Waiting for node {nid} to sync...")
            for _ in range(20):
                try:
                    info = cli_json(nid, "getblockchaininfo")
                    if info["blocks"] >= height:
                        break
                except Exception:
                    pass
                time.sleep(1)

            synced_height = cli_json(nid, "getblockcount")
            record(f"Node {nid} synced", synced_height >= height,
                   f"height={synced_height}")

            # Set up wallets
            log("INFO", f"Setting up wallets on node {nid}...")
            wallets_here = setup_wallets(nid)
            for wname, addr in wallets_here:
                all_wallet_addrs[(nid, wname)] = addr

            # Fund from node 1
            log("INFO", f"Funding node {nid} wallets from node 1...")
            miner1_bal = get_balance(1, "n1w1")
            if miner1_bal > WALLETS_PER_NODE * 2:
                for wname, addr in wallets_here:
                    try:
                        cli(1, "sendtoaddress", addr, "3.0", wallet="n1w1")
                    except Exception:
                        pass
                mine_blocks(1, "n1w1", 2)
            else:
                log("WARN", f"Node 1 balance low ({miner1_bal:.2f}), skipping funding")

            active_miners.append((nid, f"n{nid}w1"))
            active_wallets += [(nid, f"n{nid}w{i}") for i in range(1, WALLETS_PER_NODE + 1)]

            peer_count = cli_json(nid, "getconnectioncount")
            record(f"Node {nid} has peers", peer_count > 0, f"peers={peer_count}")

            # Update height tracker
            height = cli_json(1, "getblockcount")

            if nid < 5:
                log("INFO", f"Phase {nid} complete. Waiting {phase_duration}s...")
                time.sleep(phase_duration)

        # ──────────────────────────────────────────────────────────────────────
        phase_banner(6, f"Full network — 5 miners, 25 wallets transacting for {final_duration}s")
        # ──────────────────────────────────────────────────────────────────────

        # Verify network topology
        log("INFO", "Checking network sync across all 5 nodes...")
        synced, hashes = check_sync([1, 2, 3, 4, 5])
        record("All 5 nodes in sync", synced, f"{len(hashes)} unique tip hashes")

        log("INFO", f"Active miners: {len(active_miners)}, Active wallets: {len(active_wallets)}")

        # Check balances
        funded_wallets = []
        for nid_wname in active_wallets:
            nid, wname = nid_wname
            bal = get_balance(nid, wname)
            if bal > 0.005:
                funded_wallets.append(nid_wname)
        record("Wallets funded (>0.005 BTC)", len(funded_wallets) >= 10,
               f"{len(funded_wallets)}/25 have balance")

        # Start background transaction + mining workers
        tx_interval   = 2.0   # seconds between tx attempts
        mine_interval = 5.0   # seconds between mining attempts

        tx_thread = threading.Thread(
            target=tx_worker,
            args=(list(active_wallets), tx_interval),
            daemon=True
        )
        mine_thread = threading.Thread(
            target=mining_worker,
            args=(list(active_miners), mine_interval),
            daemon=True
        )
        tx_thread.start()
        mine_thread.start()

        # Progress loop for final_duration
        log("INFO", f"Running transaction storm for {final_duration}s...")
        t0 = time.time()
        snap_interval = 30  # status snapshot every 30s
        last_snap = t0
        last_tx = 0
        final_height_start = cli_json(1, "getblockcount")

        while time.time() - t0 < final_duration:
            if stop_flag.is_set():
                break
            now = time.time()
            elapsed = int(now - t0)
            remaining = int(final_duration - elapsed)

            if now - last_snap >= snap_interval:
                with tx_lock:
                    current_tx = tx_count
                interval_tx = current_tx - last_tx
                last_tx = current_tx

                try:
                    h = cli_json(1, "getblockcount")
                    mempool = cli_json(1, "getmempoolinfo")
                    mp_size = mempool.get("size", 0)
                    synced, _ = check_sync([1, 2, 3, 4, 5])
                    log("INFO",
                        f"  t+{elapsed:3d}s | height={h} | mempool={mp_size} | "
                        f"total_tx={current_tx} (+{interval_tx}) | "
                        f"synced={'✓' if synced else '✗'} | remaining={remaining}s")
                except Exception as e:
                    log("WARN", f"  Snapshot failed: {e}")
                last_snap = now

            time.sleep(2)

        stop_flag.set()

        # ── Final assertions ─────────────────────────────────────────────────
        phase_banner(7, "Final assertions")

        final_height = cli_json(1, "getblockcount")
        blocks_produced = final_height - final_height_start
        record("Blocks produced during storm", blocks_produced > 0,
               f"{blocks_produced} blocks")

        with tx_lock:
            total_tx = tx_count
        record("Transactions sent during storm", total_tx > 0, f"{total_tx} txs")

        synced, hashes = check_sync([1, 2, 3, 4, 5])
        record("All 5 nodes agree on chain tip", synced,
               f"tip={list(hashes)[0][:16]}..." if hashes else "no tips")

        # Check all 5 nodes are still alive
        for nid in range(1, 6):
            try:
                info = cli_json(nid, "getblockchaininfo")
                record(f"Node {nid} alive at end", True,
                       f"height={info['blocks']}, peers={cli_json(nid,'getconnectioncount')}")
            except Exception as e:
                record(f"Node {nid} alive at end", False, str(e))

        # Verify some wallets have confirmed transactions
        wallets_with_activity = 0
        for nid, wname in active_wallets:
            try:
                txlist = cli_json(nid, "listtransactions", "*", "10", wallet=wname)
                if len(txlist) > 0:
                    wallets_with_activity += 1
            except Exception:
                pass
        record("Wallets with transaction history", wallets_with_activity >= 5,
               f"{wallets_with_activity}/25")

        # getpqcinfo on all nodes
        for nid in range(1, 6):
            try:
                pqcinfo = cli_json(nid, "getpqcinfo")
                record(f"Node {nid} getpqcinfo", pqcinfo.get("scheme") == "falcon",
                       f"scheme={pqcinfo['scheme']} nist_level={pqcinfo['nist_level']}")
            except Exception as e:
                record(f"Node {nid} getpqcinfo", False, str(e))

    except KeyboardInterrupt:
        log("WARN", "Interrupted by user")
    except Exception as e:
        import traceback
        log("ERR", f"Test error: {e}")
        traceback.print_exc()
        record("Test completed without exception", False, str(e))
    finally:
        stop_flag.set()
        log("INFO", "Stopping all nodes...")
        stop_all()

    # ── Summary ──────────────────────────────────────────────────────────────
    elapsed_total = int(time.time() - start_time)
    print(f"\n{'='*60}")
    print(f"  TESTNET SIMULATION COMPLETE — {elapsed_total}s elapsed")
    print(f"{'='*60}")
    passed = sum(1 for _, ok, _ in results if ok)
    total  = len(results)
    for name, ok, detail in results:
        tag = f"{GREEN}✓{RESET}" if ok else f"{RED}✗{RESET}"
        print(f"  {tag} {name}" + (f"  [{detail}]" if detail else ""))
    print(f"\n  {passed}/{total} checks passed")
    if passed == total:
        print(f"  {GREEN}{BOLD}ALL CHECKS PASSED{RESET}")
    else:
        print(f"  {RED}{BOLD}{total-passed} FAILED{RESET}")
    print()
    return passed == total


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="QuantumBTC local testnet simulation")
    parser.add_argument("--fast", action="store_true",
                        help="Run a 3-minute smoke test instead of 30-minute full run")
    args = parser.parse_args()

    if args.fast:
        # Fast mode: 20s per phase, 60s final storm = ~3 min total
        phase_dur = 20
        final_dur = 60
        print(f"\n{BOLD}QuantumBTC Local Testnet — FAST MODE (~3 min){RESET}\n")
    else:
        # Full mode: 5 min per phase, 10 min final storm = ~30 min total
        phase_dur = 300
        final_dur = 600
        print(f"\n{BOLD}QuantumBTC Local Testnet — FULL MODE (~30 min){RESET}\n")

    print(f"  Nodes:   5 (regtest, Falcon-512 hybrid)")
    print(f"  Wallets: 25 (5 per node)")
    print(f"  Phase duration: {phase_dur}s")
    print(f"  Final storm:    {final_dur}s\n")

    ok = run(phase_dur, final_dur)
    sys.exit(0 if ok else 1)
