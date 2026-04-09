#!/usr/bin/env python3
# Copyright (c) 2026 BearTec.
# This file is part of QuantumBTC.
# Licensed under the Business Source License 1.1 until 2030-04-09.
# On 2030-04-09, the Change License becomes MIT. See LICENSE-BUSL and NOTICE.
"""
sustained_test.py — Long-duration endurance test for QuantumBTC.

Sends transactions at a controlled rate (default 15-20 tx/s) for 30-60 minutes
using multiple wallets. Monitors UTXO health, mempool depth, block fill, and
reports any stalls, failures, or degradation over time.

Usage:
    python3 sustained_test.py <rpcuser> <rpcpass> <rpcport> [options]

Options:
    --duration MINS   Test duration in minutes (default: 30)
    --rate TPS        Target tx/s (default: 15)
    --wallets W1,W2   Comma-separated wallet names (default: auto-detect)
    --dest ADDR       Destination address (default: rotate among wallets)
    --amount AMT      Amount per tx in QBTC (default: 0.0001)
    --report FILE     Write JSON report to this path (default: /tmp/sustained_results.json)

Designed for QuantumBTC testnet with PQC hybrid transactions.
"""

import sys, json, time, base64, urllib.request, urllib.error, argparse, os
from collections import defaultdict

def rpc(user, pw, port, method, params=None, wallet=None):
    url = f"http://127.0.0.1:{port}"
    if wallet:
        url += f"/wallet/{wallet}"
    payload = json.dumps({"jsonrpc": "1.0", "id": "st", "method": method, "params": params or []}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    req.add_header("Authorization", "Basic " + base64.b64encode(f"{user}:{pw}".encode()).decode())
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            r = json.loads(resp.read())
            if r.get("error"):
                return None, r["error"]["message"]
            return r["result"], None
    except Exception as e:
        return None, str(e)


def get_wallets(user, pw, port):
    r, _ = rpc(user, pw, port, "listwallets")
    return r or []


def get_addr(user, pw, port, wallet):
    r, _ = rpc(user, pw, port, "getnewaddress", [], wallet=wallet)
    return r


def get_utxo_count(user, pw, port, wallet):
    r, _ = rpc(user, pw, port, "listunspent", [1, 9999999], wallet=wallet)
    return len(r) if r else 0


def get_balance(user, pw, port, wallet):
    r, _ = rpc(user, pw, port, "getbalance", [], wallet=wallet)
    return float(r) if r else 0.0


def get_height(user, pw, port):
    r, _ = rpc(user, pw, port, "getblockcount")
    return r or 0


def get_mempool(user, pw, port):
    r, _ = rpc(user, pw, port, "getmempoolinfo")
    return r if r else {"size": 0, "bytes": 0}


def get_block(user, pw, port, height):
    bh, _ = rpc(user, pw, port, "getblockhash", [height])
    if not bh:
        return None
    blk, _ = rpc(user, pw, port, "getblock", [bh, 1])
    return blk


def main():
    parser = argparse.ArgumentParser(description="QuantumBTC sustained endurance test")
    parser.add_argument("rpcuser", help="RPC username")
    parser.add_argument("rpcpass", help="RPC password")
    parser.add_argument("rpcport", type=int, help="RPC port")
    parser.add_argument("--duration", type=int, default=30, help="Duration in minutes (default: 30)")
    parser.add_argument("--rate", type=float, default=15, help="Target tx/s (default: 15)")
    parser.add_argument("--wallets", type=str, default="", help="Comma-separated wallet names")
    parser.add_argument("--amount", type=float, default=0.0001, help="Amount per tx (default: 0.0001)")
    parser.add_argument("--report", type=str, default="/tmp/sustained_results.json", help="Report output path")
    args = parser.parse_args()

    user, pw, port = args.rpcuser, args.rpcpass, args.rpcport
    duration_secs = args.duration * 60
    target_rate = args.rate
    amount = args.amount

    # Discover wallets
    if args.wallets:
        wallets = [w.strip() for w in args.wallets.split(",")]
    else:
        wallets = [w for w in get_wallets(user, pw, port) if w not in ("", "miner")]
        if not wallets:
            wallets = get_wallets(user, pw, port)

    print(f"=== QuantumBTC Sustained Endurance Test ===")
    print(f"Duration: {args.duration} min, Rate: {target_rate} tx/s, Wallets: {len(wallets)}")
    print(f"Wallets: {', '.join(wallets[:10])}{'...' if len(wallets) > 10 else ''}")

    # Get destination addresses (one per wallet, round-robin)
    destinations = []
    for w in wallets:
        addr = get_addr(user, pw, port, w)
        if addr:
            destinations.append(addr)
    if not destinations:
        print("ERROR: No destination addresses available")
        sys.exit(1)

    # Baseline
    start_height = get_height(user, pw, port)
    start_mempool = get_mempool(user, pw, port)
    print(f"Start: height={start_height}, mempool={start_mempool['size']}")

    # Check initial UTXO health
    print("\nInitial UTXO health:")
    wallet_utxos = {}
    for w in wallets:
        uc = get_utxo_count(user, pw, port, w)
        bal = get_balance(user, pw, port, w)
        wallet_utxos[w] = uc
        print(f"  {w}: {uc} UTXOs, {bal:.4f} QBTC")
    total_utxos = sum(wallet_utxos.values())
    print(f"  Total: {total_utxos} UTXOs")

    # Tracking
    total_sent = 0
    total_failed = 0
    minute_stats = []  # per-minute stats
    wallet_idx = 0
    dest_idx = 0

    start_time = time.time()
    minute_start = start_time
    minute_sent = 0
    minute_failed = 0
    sleep_interval = 1.0 / target_rate if target_rate > 0 else 1.0

    print(f"\n--- Running for {args.duration} minutes at ~{target_rate} tx/s ---")

    while True:
        elapsed = time.time() - start_time
        if elapsed >= duration_secs:
            break

        # Send one transaction
        wallet = wallets[wallet_idx % len(wallets)]
        dest = destinations[dest_idx % len(destinations)]
        wallet_idx += 1
        dest_idx += 1

        txid, err = rpc(user, pw, port, "sendtoaddress", [dest, amount], wallet=wallet)
        if txid:
            total_sent += 1
            minute_sent += 1
        else:
            total_failed += 1
            minute_failed += 1

        # Rate control
        time.sleep(sleep_interval)

        # Minute checkpoint
        if time.time() - minute_start >= 60:
            mp = get_mempool(user, pw, port)
            h = get_height(user, pw, port)
            minute_elapsed = time.time() - minute_start
            actual_rate = minute_sent / minute_elapsed if minute_elapsed > 0 else 0
            success_pct = minute_sent / max(minute_sent + minute_failed, 1) * 100

            minute_data = {
                "minute": len(minute_stats) + 1,
                "sent": minute_sent,
                "failed": minute_failed,
                "actual_tps": round(actual_rate, 1),
                "success_pct": round(success_pct, 1),
                "height": h,
                "mempool_size": mp["size"],
                "mempool_bytes": mp["bytes"],
            }
            minute_stats.append(minute_data)

            mins_done = len(minute_stats)
            mins_left = args.duration - mins_done
            print(f"  [{mins_done:3d}m] sent={total_sent} fail={total_failed} "
                  f"tps={actual_rate:.1f} ok={success_pct:.0f}% "
                  f"mempool={mp['size']} height={h} ({mins_left}m left)")

            minute_start = time.time()
            minute_sent = 0
            minute_failed = 0

    end_time = time.time()
    total_elapsed = end_time - start_time
    end_height = get_height(user, pw, port)
    end_mempool = get_mempool(user, pw, port)

    # Final UTXO health
    print("\nFinal UTXO health:")
    end_utxos = {}
    for w in wallets:
        uc = get_utxo_count(user, pw, port, w)
        end_utxos[w] = uc
        delta = uc - wallet_utxos.get(w, 0)
        print(f"  {w}: {uc} UTXOs (delta: {delta:+d})")

    # Analyze blocks
    blocks_mined = end_height - start_height
    block_tx_counts = []
    for h in range(start_height + 1, end_height + 1):
        blk = get_block(user, pw, port, h)
        if blk:
            ntx = blk.get("nTx", 0) - 1
            block_tx_counts.append(ntx)

    avg_block_txs = sum(block_tx_counts) / len(block_tx_counts) if block_tx_counts else 0
    max_block_txs = max(block_tx_counts) if block_tx_counts else 0
    empty_blocks = sum(1 for c in block_tx_counts if c == 0)

    # Calculate sustained metrics
    avg_tps = total_sent / total_elapsed if total_elapsed > 0 else 0
    success_rate = total_sent / max(total_sent + total_failed, 1) * 100

    # Detect stalls (minute with 0 sent)
    stall_minutes = [m for m in minute_stats if m["sent"] == 0]

    # Consistency: standard deviation of per-minute TPS
    if minute_stats:
        tps_values = [m["actual_tps"] for m in minute_stats]
        avg_minute_tps = sum(tps_values) / len(tps_values)
        variance = sum((x - avg_minute_tps) ** 2 for x in tps_values) / len(tps_values)
        tps_stddev = variance ** 0.5
    else:
        avg_minute_tps = 0
        tps_stddev = 0

    print(f"\n{'=' * 60}")
    print(f"  QuantumBTC Sustained Endurance Test Results")
    print(f"{'=' * 60}")
    print(f"  Duration:            {total_elapsed / 60:.1f} minutes")
    print(f"  Blocks mined:        {blocks_mined} ({start_height}→{end_height})")
    print(f"  Txs sent:            {total_sent}")
    print(f"  Txs failed:          {total_failed}")
    print(f"  Success rate:        {success_rate:.1f}%")
    print(f"  Avg TPS:             {avg_tps:.1f}")
    print(f"  Target TPS:          {target_rate}")
    print(f"  TPS std deviation:   {tps_stddev:.2f}")
    print(f"  Stall minutes:       {len(stall_minutes)}")
    print(f"  Avg block txs:       {avg_block_txs:.0f}")
    print(f"  Max block txs:       {max_block_txs}")
    print(f"  Empty blocks:        {empty_blocks}")
    print(f"  Final mempool:       {end_mempool['size']}")
    print(f"  UTXO delta:          {sum(end_utxos.values()) - total_utxos:+d}")

    results = {
        "test": "sustained_endurance",
        "duration_minutes": round(total_elapsed / 60, 1),
        "target_tps": target_rate,
        "blocks_mined": blocks_mined,
        "start_height": start_height,
        "end_height": end_height,
        "total_sent": total_sent,
        "total_failed": total_failed,
        "success_rate_pct": round(success_rate, 1),
        "avg_tps": round(avg_tps, 1),
        "tps_stddev": round(tps_stddev, 2),
        "stall_minutes": len(stall_minutes),
        "avg_block_txs": round(avg_block_txs, 1),
        "max_block_txs": max_block_txs,
        "empty_blocks": empty_blocks,
        "final_mempool": end_mempool["size"],
        "minute_stats": minute_stats,
        "block_tx_counts": block_tx_counts,
    }
    with open(args.report, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nReport: {args.report}")
    print("SUSTAINED_TEST_COMPLETE")


if __name__ == "__main__":
    main()
