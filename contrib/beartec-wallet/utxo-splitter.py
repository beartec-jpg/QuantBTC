#!/usr/bin/env python3
"""
utxo-splitter.py — UTXO management tool for QuantumBTC high-throughput operation.

Splits large UTXOs into many smaller ones, or consolidates many small UTXOs
into fewer large ones. Designed to account for PQC witness overhead (~3,836 bytes
per input) when selecting consolidation batch sizes.

Usage:
    # Split: take each wallet's UTXOs and fan out into N outputs of fixed size
    python3 utxo-splitter.py split --rpcuser USER --rpcpass PASS --wallet miner \
        --target-count 50 --split-amount 0.1

    # Consolidate: merge many small UTXOs into fewer large ones
    python3 utxo-splitter.py consolidate --rpcuser USER --rpcpass PASS --wallet miner \
        --max-inputs 15 --target-utxos 10

    # Status: show UTXO count and distribution for a wallet
    python3 utxo-splitter.py status --rpcuser USER --rpcpass PASS --wallet miner

Options:
    --rpcuser USER        RPC username
    --rpcpass PASS        RPC password
    --rpcport PORT        RPC port (default: 28332)
    --wallet NAME         Wallet name (default: miner)
    --target-count N      Target number of UTXOs after split (default: 50)
    --split-amount AMT    Amount per split output in QBTC (default: 0.1)
    --max-inputs N        Max inputs per consolidation tx (default: 15)
    --target-utxos N      Stop consolidating when UTXO count <= this (default: 10)
    --fee-rate RATE       Fee rate in sat/vB (default: 10)
    --dry-run             Show what would be done without sending transactions
"""

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
import base64

# PQC witness constants
PQC_WITNESS_PER_INPUT = 3836   # bytes: ECDSA sig + EC pubkey + Dilithium sig + Dilithium pubkey
PQC_INPUT_WEIGHT = 4299        # WU per input (1-in/2-out typical)
PQC_OUTPUT_WEIGHT = 124        # WU per output (P2WPKH)
TX_OVERHEAD_WEIGHT = 44        # WU for version, locktime, etc.
COINBASE_WEIGHT = 4            # WU
MAX_BLOCK_WEIGHT = 4_000_000   # 4M WU standard limit
MAX_TX_WEIGHT = 400_000        # policy limit for single tx (~100 kB)


def rpc_call(user, pw, port, method, params=None, wallet=None):
    """Make a JSON-RPC call to bitcoind."""
    url = f"http://127.0.0.1:{port}"
    if wallet:
        url += f"/wallet/{wallet}"
    payload = json.dumps({
        "jsonrpc": "1.0",
        "id": "utxo-splitter",
        "method": method,
        "params": params or []
    }).encode()
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    credentials = base64.b64encode(f"{user}:{pw}".encode()).decode()
    req.add_header("Authorization", f"Basic {credentials}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("error"):
                return None, result["error"]["message"]
            return result["result"], None
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            err = json.loads(body)
            return None, err.get("error", {}).get("message", body)
        except json.JSONDecodeError:
            return None, body
    except Exception as e:
        return None, str(e)


def get_utxos(args, min_conf=1):
    """Get list of UTXOs for the wallet."""
    result, err = rpc_call(args.rpcuser, args.rpcpass, args.rpcport,
                           "listunspent", [min_conf, 9999999], wallet=args.wallet)
    if err:
        print(f"Error listing UTXOs: {err}", file=sys.stderr)
        sys.exit(1)
    return result


def estimate_consolidation_weight(num_inputs, num_outputs=1):
    """Estimate transaction weight for a consolidation tx with PQC witnesses."""
    return TX_OVERHEAD_WEIGHT + (num_inputs * PQC_INPUT_WEIGHT) + (num_outputs * PQC_OUTPUT_WEIGHT)


def max_safe_inputs():
    """Maximum inputs that fit in a single transaction under policy weight limit."""
    # MAX_TX_WEIGHT = overhead + n*input_weight + 1*output_weight
    n = (MAX_TX_WEIGHT - TX_OVERHEAD_WEIGHT - PQC_OUTPUT_WEIGHT) // PQC_INPUT_WEIGHT
    return min(n, 50)  # cap at 50 for safety


def cmd_status(args):
    """Show UTXO count and size distribution for a wallet."""
    utxos = get_utxos(args, min_conf=0)
    if not utxos:
        print(f"Wallet '{args.wallet}': 0 UTXOs")
        return

    amounts = [u["amount"] for u in utxos]
    confirmed = sum(1 for u in utxos if u["confirmations"] > 0)
    total = sum(amounts)

    # Distribution buckets
    buckets = [
        ("< 0.001", 0, 0.001),
        ("0.001 – 0.01", 0.001, 0.01),
        ("0.01 – 0.1", 0.01, 0.1),
        ("0.1 – 1.0", 0.1, 1.0),
        ("1.0 – 10.0", 1.0, 10.0),
        ("> 10.0", 10.0, float("inf")),
    ]

    print(f"\nWallet: {args.wallet}")
    print(f"  Total UTXOs:     {len(utxos)} ({confirmed} confirmed)")
    print(f"  Total balance:   {total:.8f} QBTC")
    print(f"\n  UTXO Distribution:")
    print(f"  {'Range':20s}  {'Count':>6s}  {'Sum QBTC':>14s}")
    print(f"  {'─'*20}  {'─'*6}  {'─'*14}")
    for label, lo, hi in buckets:
        in_range = [a for a in amounts if lo <= a < hi]
        if in_range:
            print(f"  {label:20s}  {len(in_range):6d}  {sum(in_range):14.8f}")

    # Throughput estimate
    print(f"\n  Throughput estimate:")
    print(f"    UTXOs available:         {confirmed}")
    print(f"    Max instant tx burst:    {confirmed} txs")
    print(f"    At 10s blocks:           ~{confirmed / 10:.0f} tx/s for one block")
    if confirmed > 0:
        avg_amt = total / confirmed
        print(f"    Avg UTXO size:           {avg_amt:.8f} QBTC")
    max_inp = max_safe_inputs()
    print(f"    Max inputs per tx:       {max_inp} (PQC weight limit)")


def cmd_split(args):
    """Split UTXOs into many smaller ones using sendmany."""
    utxos = get_utxos(args)
    if not utxos:
        print("No confirmed UTXOs to split.")
        return

    current_count = len(utxos)
    need = max(0, args.target_count - current_count)
    if need == 0:
        print(f"Already have {current_count} UTXOs (target: {args.target_count}). Nothing to do.")
        return

    print(f"Current UTXOs: {current_count}, Target: {args.target_count}, Need: {need} more")
    print(f"Split amount: {args.split_amount} QBTC per output")

    # Calculate how many outputs per sendmany (limited by PQC witness weight)
    # With 1 input: weight = overhead + 1*input + N*output
    max_outputs = (MAX_TX_WEIGHT - TX_OVERHEAD_WEIGHT - PQC_INPUT_WEIGHT) // PQC_OUTPUT_WEIGHT
    max_outputs = min(max_outputs, 250)  # sane cap
    batch_size = min(need, max_outputs)

    total_cost = need * args.split_amount
    total_balance = sum(u["amount"] for u in utxos)
    if total_cost > total_balance * 0.95:
        print(f"WARNING: Splitting {need} × {args.split_amount} = {total_cost:.8f} QBTC")
        print(f"         Wallet balance is only {total_balance:.8f} QBTC")
        print(f"         Reduce --split-amount or --target-count")
        return

    sent = 0
    tx_count = 0
    while sent < need:
        batch = min(batch_size, need - sent)
        # Get a fresh address for each output
        outputs = {}
        for _ in range(batch):
            addr, err = rpc_call(args.rpcuser, args.rpcpass, args.rpcport,
                                 "getnewaddress", [], wallet=args.wallet)
            if err:
                print(f"Error getting address: {err}", file=sys.stderr)
                return
            outputs[addr] = args.split_amount

        if args.dry_run:
            print(f"  [dry-run] sendmany with {batch} outputs × {args.split_amount} QBTC")
            sent += batch
            tx_count += 1
            continue

        txid, err = rpc_call(args.rpcuser, args.rpcpass, args.rpcport,
                             "sendmany", ["", outputs], wallet=args.wallet)
        if err:
            print(f"  sendmany failed ({batch} outputs): {err}")
            # Try smaller batch
            if batch > 5:
                batch_size = batch // 2
                print(f"  Retrying with batch_size={batch_size}")
                continue
            else:
                print("  Batch too small, giving up.")
                break
        else:
            sent += batch
            tx_count += 1
            print(f"  Split tx {tx_count}: {batch} outputs (txid={txid[:16]}...) [{sent}/{need}]")

    print(f"\nDone: {tx_count} transactions, {sent} new UTXOs created")
    if not args.dry_run:
        print("Wait for confirmations before using the new UTXOs.")


def cmd_consolidate(args):
    """Merge many small UTXOs into fewer large ones."""
    utxos = get_utxos(args)
    if not utxos:
        print("No confirmed UTXOs to consolidate.")
        return

    if len(utxos) <= args.target_utxos:
        print(f"Already have {len(utxos)} UTXOs (target: ≤{args.target_utxos}). Nothing to do.")
        return

    max_inp = min(args.max_inputs, max_safe_inputs())
    print(f"Current UTXOs: {len(utxos)}, Target: ≤{args.target_utxos}")
    print(f"Max inputs per consolidation tx: {max_inp} (PQC-aware)")

    # Sort by amount ascending (consolidate smallest first)
    utxos.sort(key=lambda u: u["amount"])

    round_num = 0
    while len(utxos) > args.target_utxos:
        round_num += 1
        batch = utxos[:max_inp]
        batch_total = sum(u["amount"] for u in batch)

        # Estimate fee
        weight = estimate_consolidation_weight(len(batch), 1)
        vsize = (weight + 3) // 4
        fee = vsize * args.fee_rate / 1e8  # sat/vB → QBTC
        net = batch_total - fee

        if net <= 0:
            print(f"  Round {round_num}: batch of {len(batch)} too small to cover fee ({fee:.8f} QBTC)")
            utxos = utxos[len(batch):]
            continue

        # Build raw transaction inputs
        inputs = [{"txid": u["txid"], "vout": u["vout"]} for u in batch]

        # Get destination address
        addr, err = rpc_call(args.rpcuser, args.rpcpass, args.rpcport,
                             "getnewaddress", [], wallet=args.wallet)
        if err:
            print(f"Error getting address: {err}", file=sys.stderr)
            return

        if args.dry_run:
            print(f"  [dry-run] Round {round_num}: merge {len(batch)} UTXOs "
                  f"({batch_total:.8f} → {net:.8f} QBTC, fee ~{fee:.8f})")
            utxos = utxos[len(batch):]
            continue

        # Use sendtoaddress with coin control if available, otherwise fund+sign+send raw
        # Simpler approach: use fundrawtransaction
        raw_hex, err = rpc_call(args.rpcuser, args.rpcpass, args.rpcport,
                                "createrawtransaction", [inputs, [{addr: round(net, 8)}]],
                                wallet=args.wallet)
        if err:
            print(f"  Round {round_num}: createrawtransaction failed: {err}")
            utxos = utxos[len(batch):]
            continue

        signed, err = rpc_call(args.rpcuser, args.rpcpass, args.rpcport,
                               "signrawtransactionwithwallet", [raw_hex],
                               wallet=args.wallet)
        if err:
            print(f"  Round {round_num}: signrawtransaction failed: {err}")
            utxos = utxos[len(batch):]
            continue

        if not signed.get("complete"):
            print(f"  Round {round_num}: signing incomplete")
            utxos = utxos[len(batch):]
            continue

        txid, err = rpc_call(args.rpcuser, args.rpcpass, args.rpcport,
                             "sendrawtransaction", [signed["hex"]],
                             wallet=args.wallet)
        if err:
            print(f"  Round {round_num}: sendrawtransaction failed: {err}")
            utxos = utxos[len(batch):]
            continue

        print(f"  Round {round_num}: merged {len(batch)} → 1 "
              f"({batch_total:.8f} → {net:.8f} QBTC, txid={txid[:16]}...)")
        utxos = utxos[len(batch):]

    remaining = get_utxos(args, min_conf=0)
    print(f"\nDone: {round_num} rounds, now {len(remaining)} UTXOs (target: ≤{args.target_utxos})")


def main():
    parser = argparse.ArgumentParser(
        description="UTXO management tool for QuantumBTC high-throughput operation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument("command", choices=["split", "consolidate", "status"],
                        help="Operation to perform")
    parser.add_argument("--rpcuser", required=True, help="RPC username")
    parser.add_argument("--rpcpass", required=True, help="RPC password")
    parser.add_argument("--rpcport", type=int, default=28332, help="RPC port (default: 28332)")
    parser.add_argument("--wallet", default="miner", help="Wallet name (default: miner)")
    parser.add_argument("--target-count", type=int, default=50,
                        help="Target UTXO count for split (default: 50)")
    parser.add_argument("--split-amount", type=float, default=0.1,
                        help="Amount per split output in QBTC (default: 0.1)")
    parser.add_argument("--max-inputs", type=int, default=15,
                        help="Max inputs per consolidation tx (default: 15)")
    parser.add_argument("--target-utxos", type=int, default=10,
                        help="Stop consolidating when UTXO count <= this (default: 10)")
    parser.add_argument("--fee-rate", type=int, default=10,
                        help="Fee rate in sat/vB (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show planned operations without executing")

    args = parser.parse_args()

    if args.command == "status":
        cmd_status(args)
    elif args.command == "split":
        cmd_split(args)
    elif args.command == "consolidate":
        cmd_consolidate(args)


if __name__ == "__main__":
    main()
