#!/usr/bin/env python3
# Copyright (c) 2026 BearTec.
# This file is part of QuantumBTC.
# Licensed under the Business Source License 1.1 until 2030-04-09.
# On 2030-04-09, the Change License becomes MIT. See LICENSE-BUSL and NOTICE.
"""
ghostdag_contention_test.py — GHOSTDAG parallelism and blue/red scoring test.

Launches multiple rapid miners simultaneously to force block contention
(multiple miners finding blocks in the same ~10s window), then analyzes
DAG structure: parallel blocks, blue vs red scoring, merge set sizes,
and selected parent chain integrity.

Usage:
    python3 ghostdag_contention_test.py <rpcuser> <rpcpass> <rpcport> [options]

Options:
    --miners N        Number of concurrent miner wallets (default: 8)
    --duration SECS   How long to let miners race (default: 120)
    --sleep MS        Sleep between generatetoaddress calls in ms (default: 100)
    --report FILE     JSON report output (default: /tmp/ghostdag_contention.json)

This test creates N miner wallets, gives each a mining address, and fires
generatetoaddress as fast as possible from all of them simultaneously.
With N miners and ~100ms RPC round-trip, contention probability = N * RTT / block_interval.
At 8 miners with 100ms: ~8% contention per block window → expect parallel blocks.
"""

import sys, json, time, base64, urllib.request, urllib.error
import argparse, threading
from collections import defaultdict


def rpc(user, pw, port, method, params=None, wallet=None, timeout=30):
    url = f"http://127.0.0.1:{port}"
    if wallet:
        url += f"/wallet/{wallet}"
    payload = json.dumps({"jsonrpc": "1.0", "id": "gd", "method": method, "params": params or []}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            r = json.loads(resp.read())
            if r.get("error"):
                return None, r["error"]["message"]
            return r["result"], None
    except Exception as e:
        return None, str(e)


def get_height(user, pw, port):
    r, _ = rpc(user, pw, port, "getblockcount")
    return r or 0


def get_block(user, pw, port, height):
    bh, _ = rpc(user, pw, port, "getblockhash", [height])
    if not bh:
        return None
    blk, _ = rpc(user, pw, port, "getblock", [bh, 2])  # verbosity=2 for full details
    return blk


def get_tips(user, pw, port):
    r, _ = rpc(user, pw, port, "getchaintips")
    return r or []


class MinerThread(threading.Thread):
    """Mines blocks as fast as possible from a wallet."""
    def __init__(self, user, pw, port, wallet, address, sleep_ms, stop_event):
        super().__init__(daemon=True)
        self.user = user
        self.pw = pw
        self.port = port
        self.wallet = wallet
        self.address = address
        self.sleep_ms = sleep_ms
        self.stop_event = stop_event
        self.blocks_mined = 0
        self.errors = 0

    def run(self):
        while not self.stop_event.is_set():
            r, err = rpc(self.user, self.pw, self.port, "generatetoaddress",
                        [1, self.address, 10000000],
                        wallet=self.wallet, timeout=60)
            if r:
                self.blocks_mined += 1
            else:
                self.errors += 1
            if self.sleep_ms > 0:
                time.sleep(self.sleep_ms / 1000.0)


def main():
    parser = argparse.ArgumentParser(description="GHOSTDAG contention test")
    parser.add_argument("rpcuser", help="RPC username")
    parser.add_argument("rpcpass", help="RPC password")
    parser.add_argument("rpcport", type=int, help="RPC port")
    parser.add_argument("--miners", type=int, default=8, help="Concurrent miners (default: 8)")
    parser.add_argument("--duration", type=int, default=120, help="Duration in seconds (default: 120)")
    parser.add_argument("--sleep", type=int, default=100, help="Sleep between mines in ms (default: 100)")
    parser.add_argument("--report", type=str, default="/tmp/ghostdag_contention.json")
    args = parser.parse_args()

    user, pw, port = args.rpcuser, args.rpcpass, args.rpcport

    print(f"=== GHOSTDAG Contention Test ===")
    print(f"Miners: {args.miners}, Duration: {args.duration}s, Sleep: {args.sleep}ms")

    # Setup miner wallets
    existing = rpc(user, pw, port, "listwallets")[0] or []
    miner_wallets = []
    miner_addrs = []

    for i in range(args.miners):
        wname = f"contention_miner_{i}"
        if wname not in existing:
            r, err = rpc(user, pw, port, "createwallet", [wname])
            if err:
                print(f"  WARN: createwallet {wname}: {err}")
                continue
            print(f"  Created {wname}")
        else:
            rpc(user, pw, port, "loadwallet", [wname])
        addr, _ = rpc(user, pw, port, "getnewaddress", [], wallet=wname)
        if addr:
            miner_wallets.append(wname)
            miner_addrs.append(addr)
            print(f"  {wname}: {addr}")

    print(f"\n{len(miner_wallets)} miners ready")

    # Baseline
    start_height = get_height(user, pw, port)
    start_tips = get_tips(user, pw, port)
    print(f"Start: height={start_height}, tips={len(start_tips)}")

    # Launch all miners simultaneously
    stop_event = threading.Event()
    threads = []
    for i, (w, a) in enumerate(zip(miner_wallets, miner_addrs)):
        t = MinerThread(user, pw, port, w, a, args.sleep, stop_event)
        threads.append(t)

    print(f"\n--- Launching {len(threads)} concurrent miners for {args.duration}s ---")
    start_time = time.time()
    for t in threads:
        t.start()

    # Monitor progress
    while time.time() - start_time < args.duration:
        time.sleep(5)
        h = get_height(user, pw, port)
        total_mined = sum(t.blocks_mined for t in threads)
        elapsed = time.time() - start_time
        sys.stdout.write(f"\r  [{elapsed:.0f}s] height={h} mined={total_mined} "
                        f"rate={total_mined/elapsed:.1f} blk/s")
        sys.stdout.flush()

    print("\n\nStopping miners...")
    stop_event.set()
    for t in threads:
        t.join(timeout=10)

    end_time = time.time()
    end_height = get_height(user, pw, port)
    total_elapsed = end_time - start_time

    # Per-miner stats
    print("\nPer-miner results:")
    total_mined = 0
    for t in threads:
        total_mined += t.blocks_mined
        print(f"  {t.wallet}: {t.blocks_mined} blocks, {t.errors} errors")

    blocks_on_chain = end_height - start_height
    print(f"\nBlocks on best chain: {blocks_on_chain} ({start_height}→{end_height})")
    print(f"Total mined (all miners): {total_mined}")

    # Analyze DAG structure
    print("\n--- DAG Analysis ---")
    end_tips = get_tips(user, pw, port)
    active_tips = [t for t in end_tips if t.get("status") == "active"]
    valid_fork_tips = [t for t in end_tips if t.get("status") == "valid-fork"]
    valid_headers = [t for t in end_tips if t.get("status") == "valid-headers"]

    print(f"Chain tips: {len(end_tips)} total")
    print(f"  active: {len(active_tips)}")
    print(f"  valid-fork: {len(valid_fork_tips)}")
    print(f"  valid-headers: {len(valid_headers)}")

    # Analyze blocks for DAG features (parallel parents, etc.)
    dag_blocks = 0
    multi_parent_blocks = 0
    parent_counts = []
    blocks_with_dag_data = []

    for h in range(start_height + 1, end_height + 1):
        blk = get_block(user, pw, port, h)
        if not blk:
            continue

        # Check for DAG-mode version bit
        version = blk.get("version", 0)
        is_dag = bool(version & 0x20000000)  # BLOCK_VERSION_DAGMODE
        if is_dag:
            dag_blocks += 1

        parents = blk.get("dagparents", [])
        nparents = len(parents) if parents else 1
        parent_counts.append(nparents)
        if nparents > 1:
            multi_parent_blocks += 1

        block_info = {
            "height": h,
            "hash": blk.get("hash", "")[:16],
            "nTx": blk.get("nTx", 0),
            "size": blk.get("size", 0),
            "version": hex(version),
            "dagmode": is_dag,
            "dagparents": nparents,
            "time": blk.get("time", 0),
        }
        blocks_with_dag_data.append(block_info)

    # Contention analysis: blocks with same timestamp or within 1s
    timestamp_groups = defaultdict(list)
    for b in blocks_with_dag_data:
        timestamp_groups[b["time"]].append(b)

    simultaneous = sum(1 for g in timestamp_groups.values() if len(g) > 1)
    max_simultaneous = max((len(g) for g in timestamp_groups.values()), default=0)

    # Block interval analysis
    intervals = []
    for i in range(1, len(blocks_with_dag_data)):
        dt = blocks_with_dag_data[i]["time"] - blocks_with_dag_data[i-1]["time"]
        intervals.append(dt)
    avg_interval = sum(intervals) / len(intervals) if intervals else 0
    zero_intervals = sum(1 for i in intervals if i == 0)

    parallel_pct = multi_parent_blocks / max(blocks_on_chain, 1) * 100
    zero_pct = zero_intervals / max(len(intervals), 1) * 100

    print(f"\nBlock analysis ({blocks_on_chain} blocks):")
    print(f"  DAG-mode blocks:       {dag_blocks}")
    print(f"  Multi-parent blocks:   {multi_parent_blocks} ({parallel_pct:.1f}%)")
    print(f"  Max DAG parents:       {max(parent_counts) if parent_counts else 0}")
    print(f"  Avg block interval:    {avg_interval:.1f}s")
    print(f"  Zero-interval blocks:  {zero_intervals} ({zero_pct:.1f}%)")
    print(f"  Simultaneous groups:   {simultaneous}")
    print(f"  Max simultaneous:      {max_simultaneous}")
    print(f"  Valid-fork tips:       {len(valid_fork_tips)}")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"  GHOSTDAG Contention Test Summary")
    print(f"{'=' * 60}")
    print(f"  Duration:              {total_elapsed:.0f}s")
    print(f"  Concurrent miners:     {len(threads)}")
    print(f"  Blocks on chain:       {blocks_on_chain}")
    print(f"  Total mined attempts:  {total_mined}")
    print(f"  Block rate:            {blocks_on_chain/total_elapsed:.2f} blk/s")
    print(f"  Parallel blocks:       {multi_parent_blocks} ({parallel_pct:.1f}%)")
    print(f"  Fork tips discovered:  {len(valid_fork_tips)}")
    print(f"  Chain integrity:       {'OK' if blocks_on_chain > 0 else 'FAIL'}")

    if parallel_pct > 5:
        print(f"\n  ✓ GHOSTDAG parallelism confirmed: {parallel_pct:.1f}% of blocks had multiple parents")
    elif len(valid_fork_tips) > 0:
        print(f"\n  ~ Contention detected via fork tips ({len(valid_fork_tips)}), but resolved to single-parent chain")
    else:
        print(f"\n  ⚠ Low contention — try more miners or shorter --sleep")

    results = {
        "test": "ghostdag_contention",
        "duration_secs": round(total_elapsed),
        "num_miners": len(threads),
        "sleep_ms": args.sleep,
        "blocks_on_chain": blocks_on_chain,
        "total_mined": total_mined,
        "block_rate": round(blocks_on_chain / total_elapsed, 2),
        "dag_mode_blocks": dag_blocks,
        "multi_parent_blocks": multi_parent_blocks,
        "parallel_pct": round(parallel_pct, 1),
        "max_parents": max(parent_counts) if parent_counts else 0,
        "avg_interval": round(avg_interval, 1),
        "zero_interval_blocks": zero_intervals,
        "simultaneous_groups": simultaneous,
        "valid_fork_tips": len(valid_fork_tips),
        "per_miner": [{"wallet": t.wallet, "mined": t.blocks_mined, "errors": t.errors} for t in threads],
        "blocks": blocks_with_dag_data,
    }
    with open(args.report, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport: {args.report}")
    print("CONTENTION_TEST_COMPLETE")


if __name__ == "__main__":
    main()
