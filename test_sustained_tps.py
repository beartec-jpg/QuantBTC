#!/usr/bin/env python3
"""
test_sustained_tps.py — Sustained throughput endurance test for QuantumBTC.

Maintains a target TPS for an extended duration (30–60 min) using many wallets,
monitoring mempool depth, block production, UTXO health, and chain stability
throughout the run.

Usage:
    python3 test_sustained_tps.py <rpcuser> <rpcpass> <rpcport> <node_id> \
        [--tps 15] [--duration 1800] [--wallets alice,bob,carol,...]

Default: 15 tx/s for 1800s (30 min) using all wallets found in wallet_addrs.json.
"""

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error
import base64
from collections import defaultdict

# Cross-node destination addresses (10 addresses per target set)
DEST_ADDRS = {
    1: [
        "qbtct1qjkjjyyvqwux836x6e0gys2n56qn6mw8z2rf08n",
        "qbtct1q4pfxalzxn6wv9rcm9z06qp9u5r0stuc5t0t2h3",
        "qbtct1q4x0c85j8ymdr5zkpld9ttak2rxkt0cqu63ascf",
        "qbtct1qnhc63vjrhgdrrytupd4cj6jafqqfysnpfezj67",
        "qbtct1qvru38pkry8crtr3l09rd4sgcp9skfn8tscv4j8",
    ],
    2: [
        "qbtct1qy3wn75agu4zm2g3lgp688xk8jz3k9n0m93v9gd",
        "qbtct1q2uhp6v2f4kkq9948wmfnqdpnf4jplgxaluqwkq",
        "qbtct1q4x0c85j8ymdr5zkpld9ttak2rxkt0cqu63ascf",
        "qbtct1qnhc63vjrhgdrrytupd4cj6jafqqfysnpfezj67",
        "qbtct1qvru38pkry8crtr3l09rd4sgcp9skfn8tscv4j8",
    ],
    3: [
        "qbtct1qy3wn75agu4zm2g3lgp688xk8jz3k9n0m93v9gd",
        "qbtct1q2uhp6v2f4kkq9948wmfnqdpnf4jplgxaluqwkq",
        "qbtct1qjkjjyyvqwux836x6e0gys2n56qn6mw8z2rf08n",
        "qbtct1q4pfxalzxn6wv9rcm9z06qp9u5r0stuc5t0t2h3",
        "qbtct1qtmj8prrwkmh9et0evufm4pa93qga2mjcdy2cv0",
    ],
}


def rpc(user, pw, port, method, params=None, wallet=None):
    url = f"http://127.0.0.1:{port}"
    if wallet:
        url += f"/wallet/{wallet}"
    payload = json.dumps({"jsonrpc": "1.0", "id": "sustained", "method": method, "params": params or []}).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    credentials = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req.add_header("Authorization", f"Basic {credentials}")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            r = json.loads(resp.read())
            if r.get("error"):
                return None, r["error"]["message"]
            return r["result"], None
    except Exception as e:
        return None, str(e)


def get_wallets(user, pw, port):
    """List loaded wallets."""
    r, _ = rpc(user, pw, port, "listwallets")
    return r or []


def get_height(user, pw, port):
    r, _ = rpc(user, pw, port, "getblockcount")
    return r or 0


def get_mempool(user, pw, port):
    r, _ = rpc(user, pw, port, "getmempoolinfo")
    return r if r else {"size": 0, "bytes": 0}


def get_block(user, pw, port, height):
    h, _ = rpc(user, pw, port, "getblockhash", [height])
    if not h:
        return None
    b, _ = rpc(user, pw, port, "getblock", [h, 1])
    return b


def get_sigcache(user, pw, port):
    r, _ = rpc(user, pw, port, "getpqcsigcachestats")
    return r


def main():
    parser = argparse.ArgumentParser(description="Sustained TPS endurance test")
    parser.add_argument("rpcuser")
    parser.add_argument("rpcpass")
    parser.add_argument("rpcport", type=int)
    parser.add_argument("node_id", type=int, choices=[1, 2, 3])
    parser.add_argument("--tps", type=float, default=15, help="Target tx/s (default: 15)")
    parser.add_argument("--duration", type=int, default=1800, help="Duration in seconds (default: 1800)")
    parser.add_argument("--wallets", type=str, default=None,
                        help="Comma-separated wallet names (default: auto-detect)")
    parser.add_argument("--amount", type=float, default=0.0001, help="Amount per tx (default: 0.0001)")
    args = parser.parse_args()

    # Discover wallets
    if args.wallets:
        wallets = args.wallets.split(",")
    else:
        all_wallets = get_wallets(args.rpcuser, args.rpcpass, args.rpcport)
        wallets = [w for w in all_wallets if w not in ("", "miner")]
        if not wallets:
            wallets = [w for w in all_wallets if w]
    if not wallets:
        print("ERROR: No wallets found. Create wallets first.", file=sys.stderr)
        sys.exit(1)

    dests = DEST_ADDRS.get(args.node_id, DEST_ADDRS[1])

    print(f"=== QuantumBTC Sustained TPS Test ===")
    print(f"Node: {args.node_id}, Target: {args.tps} tx/s, Duration: {args.duration}s ({args.duration/60:.0f} min)")
    print(f"Wallets: {len(wallets)}, Destinations: {len(dests)}")

    # Baseline
    start_height = get_height(args.rpcuser, args.rpcpass, args.rpcport)
    start_mempool = get_mempool(args.rpcuser, args.rpcpass, args.rpcport)
    start_cache = get_sigcache(args.rpcuser, args.rpcpass, args.rpcport)
    print(f"Start: height={start_height}, mempool={start_mempool['size']}")

    # Tracking
    interval = 1.0 / args.tps if args.tps > 0 else 1.0
    wallet_idx = 0
    dest_idx = 0
    total_sent = 0
    total_failed = 0
    start_time = time.time()

    # Per-minute stats
    minute_stats = []
    minute_sent = 0
    minute_failed = 0
    last_minute = 0

    # Checkpoint every 60s
    checkpoints = []

    print(f"\n{'Min':>4s} {'Sent':>6s} {'Fail':>5s} {'TPS':>6s} {'Mempool':>8s} {'Height':>7s} {'Status':>10s}")
    print(f"{'─'*4} {'─'*6} {'─'*5} {'─'*6} {'─'*8} {'─'*7} {'─'*10}")

    while True:
        elapsed = time.time() - start_time
        if elapsed >= args.duration:
            break

        current_minute = int(elapsed // 60)

        # Log checkpoint every minute
        if current_minute > last_minute:
            mp = get_mempool(args.rpcuser, args.rpcpass, args.rpcport)
            h = get_height(args.rpcuser, args.rpcpass, args.rpcport)
            actual_tps = minute_sent / 60.0 if minute_sent > 0 else 0
            status = "OK" if minute_failed < minute_sent * 0.1 else "DEGRADED"
            if minute_sent == 0:
                status = "STALLED"

            print(f"{last_minute:4d} {minute_sent:6d} {minute_failed:5d} {actual_tps:6.1f} {mp['size']:8d} {h:7d} {status:>10s}")

            checkpoints.append({
                "minute": last_minute,
                "sent": minute_sent,
                "failed": minute_failed,
                "tps": round(actual_tps, 1),
                "mempool_size": mp["size"],
                "mempool_bytes": mp.get("bytes", 0),
                "height": h,
                "status": status,
            })

            minute_sent = 0
            minute_failed = 0
            last_minute = current_minute

        # Send one transaction
        wallet = wallets[wallet_idx % len(wallets)]
        wallet_idx += 1
        dest = dests[dest_idx % len(dests)]
        dest_idx += 1

        txid, err = rpc(args.rpcuser, args.rpcpass, args.rpcport,
                        "sendtoaddress", [dest, args.amount], wallet=wallet)
        if txid:
            total_sent += 1
            minute_sent += 1
        else:
            total_failed += 1
            minute_failed += 1

        # Rate-limit to target TPS
        next_send = start_time + (total_sent + total_failed) * interval
        now = time.time()
        if next_send > now:
            time.sleep(next_send - now)

    # Final stats
    end_time = time.time()
    end_height = get_height(args.rpcuser, args.rpcpass, args.rpcport)
    end_mempool = get_mempool(args.rpcuser, args.rpcpass, args.rpcport)
    end_cache = get_sigcache(args.rpcuser, args.rpcpass, args.rpcport)
    total_elapsed = end_time - start_time
    blocks_mined = end_height - start_height

    # Analyze blocks
    block_tx_counts = []
    for h in range(start_height + 1, end_height + 1):
        blk = get_block(args.rpcuser, args.rpcpass, args.rpcport, h)
        if blk:
            block_tx_counts.append(blk.get("nTx", 1) - 1)

    # Cache delta
    cache_delta = {}
    if start_cache and end_cache:
        for key in ("ecdsa_hits", "ecdsa_misses", "dilithium_hits", "dilithium_misses"):
            cache_delta[key] = end_cache.get(key, 0) - start_cache.get(key, 0)
        for prefix in ("ecdsa", "dilithium"):
            hits = cache_delta.get(f"{prefix}_hits", 0)
            total = hits + cache_delta.get(f"{prefix}_misses", 0)
            cache_delta[f"{prefix}_hit_rate"] = hits / total if total > 0 else 0

    avg_tps = total_sent / total_elapsed if total_elapsed > 0 else 0
    success_pct = total_sent / max(total_sent + total_failed, 1) * 100
    avg_block_txs = sum(block_tx_counts) / len(block_tx_counts) if block_tx_counts else 0

    # Count healthy minutes (>= 80% of target TPS)
    healthy = sum(1 for c in checkpoints if c["tps"] >= args.tps * 0.8)
    degraded = sum(1 for c in checkpoints if c["status"] == "DEGRADED")
    stalled = sum(1 for c in checkpoints if c["status"] == "STALLED")

    print(f"\n{'='*60}")
    print(f"  Sustained TPS Test Results (Node {args.node_id})")
    print(f"{'='*60}")
    print(f"  Duration:           {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    print(f"  Target TPS:         {args.tps}")
    print(f"  Actual avg TPS:     {avg_tps:.1f}")
    print(f"  Total sent:         {total_sent}")
    print(f"  Total failed:       {total_failed}")
    print(f"  Success rate:       {success_pct:.1f}%")
    print(f"  Blocks mined:       {blocks_mined} ({start_height}→{end_height})")
    print(f"  Avg txs/block:      {avg_block_txs:.0f}")
    print(f"  Final mempool:      {end_mempool['size']}")
    print(f"  Healthy minutes:    {healthy}/{len(checkpoints)} ({healthy/max(len(checkpoints),1)*100:.0f}%)")
    print(f"  Degraded minutes:   {degraded}")
    print(f"  Stalled minutes:    {stalled}")
    if cache_delta:
        print(f"  Sig cache (ECDSA):  {cache_delta.get('ecdsa_hits',0)} hits / "
              f"{cache_delta.get('ecdsa_misses',0)} misses "
              f"({cache_delta.get('ecdsa_hit_rate',0)*100:.1f}% hit rate)")
        print(f"  Sig cache (Dilith): {cache_delta.get('dilithium_hits',0)} hits / "
              f"{cache_delta.get('dilithium_misses',0)} misses "
              f"({cache_delta.get('dilithium_hit_rate',0)*100:.1f}% hit rate)")
    print()

    # Write results
    results = {
        "node_id": args.node_id,
        "target_tps": args.tps,
        "actual_tps": round(avg_tps, 1),
        "duration_secs": round(total_elapsed),
        "total_sent": total_sent,
        "total_failed": total_failed,
        "success_pct": round(success_pct, 1),
        "blocks_mined": blocks_mined,
        "avg_block_txs": round(avg_block_txs, 1),
        "healthy_minutes": healthy,
        "total_minutes": len(checkpoints),
        "checkpoints": checkpoints,
        "block_tx_counts": block_tx_counts,
        "sig_cache_delta": cache_delta,
        "final_mempool": end_mempool["size"],
    }
    outfile = f"/tmp/sustained_tps_n{args.node_id}.json"
    with open(outfile, "w") as f:
        json.dump(results, f, indent=2)
    print(f"Results saved to {outfile}")
    print("SUSTAINED_TEST_COMPLETE")


if __name__ == "__main__":
    main()
