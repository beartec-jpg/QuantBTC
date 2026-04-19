#!/usr/bin/env python3
"""Remote qBTC wallet drainer.

Sweeps almost all funds from the miner wallet on each live node to a single
collection address, leaving a small reserve for fees and maintenance.

Examples:
  python3 contrib/qbtc-testnet/remote_wallet_drainer.py --once
  python3 contrib/qbtc-testnet/remote_wallet_drainer.py --interval 1800 --keep 1.0
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

DEFAULT_ADDRESS = "qbtct1qdtnzfm4r0w5853rjy3gy4xgft3chmklgx2yh6a"
SATOSHI = Decimal("0.00000001")


@dataclass(frozen=True)
class Node:
    name: str
    ip: str
    rpc_user: str
    rpc_pass: str
    wallet: str = "miner"


NODES = [
    Node("S1", "46.62.156.169", "qbtcseed", "seednode1_rpc_2026"),
    Node("S2", "37.27.47.236", "qbtcseed", "seednode2_rpc_2026"),
    Node("S3", "89.167.109.241", "qbtcverify", "verify_node3_2026"),
]


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def rpc(node: Node, method: str, params: list | None = None, wallet: bool = False):
    url = f"http://{node.ip}:28332/"
    if wallet:
        url += f"wallet/{node.wallet}"
    payload = json.dumps(
        {"jsonrpc": "1.0", "id": node.name, "method": method, "params": params or []}
    ).encode()
    request = urllib.request.Request(url, data=payload, headers={"Content-Type": "text/plain"})
    token = base64.b64encode(f"{node.rpc_user}:{node.rpc_pass}".encode()).decode()
    request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=12) as response:
        body = json.loads(response.read().decode())
    if body.get("error"):
        raise RuntimeError(body["error"])
    return body["result"]


def format_amount(value: Decimal) -> str:
    return str(value.quantize(SATOSHI, rounding=ROUND_DOWN))


def drain_once(address: str, keep: Decimal, max_per_sweep: Decimal, dry_run: bool = False) -> int:
    failures = 0
    for node in NODES:
        try:
            balance = Decimal(str(rpc(node, "getbalance", wallet=True)))
            available = (balance - keep).quantize(SATOSHI, rounding=ROUND_DOWN)
            send_amount = min(available, max_per_sweep).quantize(SATOSHI, rounding=ROUND_DOWN)
            if send_amount <= Decimal("0"):
                print(f"[{utc_now()}] {node.name}: skip balance={balance} keep={keep}")
                continue

            if dry_run:
                print(f"[{utc_now()}] {node.name}: dry-run would send {send_amount} to {address}")
                continue

            txid = rpc(node, "sendtoaddress", [address, format_amount(send_amount)], wallet=True)
            print(
                f"[{utc_now()}] {node.name}: sent {send_amount} QBTC to {address} txid={txid}",
                flush=True,
            )
        except (urllib.error.URLError, TimeoutError, RuntimeError, ValueError) as exc:
            failures += 1
            print(f"[{utc_now()}] {node.name}: ERROR {exc}", file=sys.stderr, flush=True)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Sweep live qBTC node wallets to one address")
    parser.add_argument("--address", default=DEFAULT_ADDRESS, help="Destination qBTC testnet address")
    parser.add_argument("--keep", type=Decimal, default=Decimal("1.0"), help="Amount to leave on each node")
    parser.add_argument("--interval", type=int, default=1800, help="Loop interval in seconds")
    parser.add_argument("--max-per-sweep", type=Decimal, default=Decimal("50.0"), help="Maximum amount to send per node on each pass")
    parser.add_argument("--once", action="store_true", help="Run only one sweep pass")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be sent without broadcasting")
    args = parser.parse_args()

    try:
        result = rpc(NODES[0], "validateaddress", [args.address])
    except Exception as exc:
        print(f"Address validation failed: {exc}", file=sys.stderr)
        return 1

    if not result.get("isvalid"):
        print("Destination address is invalid for qBTC.", file=sys.stderr)
        return 1

    if args.once:
        return drain_once(args.address, args.keep, args.max_per_sweep, args.dry_run)

    print(
        f"[{utc_now()}] starting remote wallet drainer -> {args.address} "
        f"interval={args.interval}s keep={args.keep} max_per_sweep={args.max_per_sweep}",
        flush=True,
    )
    while True:
        drain_once(args.address, args.keep, args.max_per_sweep, args.dry_run)
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
