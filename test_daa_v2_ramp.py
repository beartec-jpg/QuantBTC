#!/usr/bin/env python3
"""
QBTC Load-Aware DAA v2 staged realism test.

This script brings up a private multi-node qbtctestnet, ramps from a small
baseline to a larger miner/wallet set, captures difficulty during the steady
low-load period, then pushes a coordinated spam phase and finally ramps back
down to measure whether difficulty settles back toward baseline.

Default shape:
  - Gradual ramp-up from 1 to N nodes
  - 5 wallets per node
  - low-load transaction activity during ramp-up
  - full-wallet spam attack phase
  - gradual ramp-down back to baseline
  - CSV + Markdown report written at the end

Typical run on a larger Codespace:
  python3 test_daa_v2_ramp.py --nodes 8 --wallets-per-node 5 \
      --phase-minutes 4 --attack-minutes 8 --sample-seconds 15
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

CHAIN = "qbtctestnet"
DEFAULT_BASE_PORT = 28332
DEFAULT_P2P_PORT = 28333

WalletRef = Tuple[int, str]
WalletInfo = Tuple[int, str, str]


@dataclass
class Phase:
    name: str
    duration_sec: int
    active_nodes: int
    wallet_interval: float
    mine_interval: float
    amount_min: float
    amount_max: float


class TestAbort(RuntimeError):
    pass


class QBtcRampTest:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.repo_root = Path(__file__).resolve().parent
        self.bitcoind = self._resolve_binary(args.bitcoind, "bitcoind")
        self.cli = self._resolve_binary(args.cli, "bitcoin-cli")
        self.datadir_root = Path(args.datadir_root).resolve()
        self.output_dir = Path(args.output_dir).resolve()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.nodes = [
            {
                "id": i,
                "rpc_port": args.base_rpc_port + i * 100,
                "p2p_port": args.base_p2p_port + i * 100,
                "datadir": self.datadir_root / f"node{i}",
            }
            for i in range(args.nodes)
        ]

        self.node_procs: List[subprocess.Popen] = []
        self.wallets: List[WalletInfo] = []
        self.wallet_addrs: Dict[WalletRef, str] = {}
        self.samples: List[dict] = []
        self.phase_bounds: List[dict] = []
        self.tx_ok = 0
        self.tx_fail = 0
        self.mined_blocks = 0
        self.random = random.Random(args.seed)
        self.miner_wallet: WalletRef = (0, "n0w0")
        self.miner_addr = ""

    def _resolve_binary(self, explicit: str | None, name: str) -> str:
        candidates = []
        if explicit:
            candidates.append(Path(explicit))
        candidates.extend([
            self.repo_root / "src" / name,
            self.repo_root / "build-fresh" / "src" / name,
        ])
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return str(Path(candidate).resolve())
        return name

    def log(self, msg: str) -> None:
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {msg}", flush=True)

    def node_cli(self, node_id: int, *args: str, wallet: str | None = None, timeout: int = 120) -> str:
        node = self.nodes[node_id]
        cmd = [
            self.cli,
            f"-{CHAIN}",
            f"-datadir={node['datadir']}",
            f"-rpcport={node['rpc_port']}",
        ]
        if wallet:
            cmd.append(f"-rpcwallet={wallet}")
        cmd.extend(args)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if proc.returncode != 0:
            stderr = (proc.stderr or proc.stdout).strip()
            raise RuntimeError(f"node{node_id} cli failed: {' '.join(cmd)}\n{stderr}")
        return proc.stdout.strip()

    def node_cli_json(self, node_id: int, *args: str, wallet: str | None = None, timeout: int = 120):
        return json.loads(self.node_cli(node_id, *args, wallet=wallet, timeout=timeout))

    def wait_ready(self, node_id: int, timeout: int = 90) -> None:
        deadline = time.time() + timeout
        last_err = ""
        while time.time() < deadline:
            try:
                self.node_cli_json(node_id, "getblockchaininfo")
                return
            except Exception as exc:
                last_err = str(exc)
                time.sleep(1)
        raise TestAbort(f"node {node_id} failed to start in time: {last_err}")

    def start_nodes(self) -> None:
        self.log(f"Starting {self.args.nodes} qBTC nodes...")
        if self.datadir_root.exists() and not self.args.keep_existing_datadir:
            shutil.rmtree(self.datadir_root)
        self.datadir_root.mkdir(parents=True, exist_ok=True)

        for node in self.nodes:
            datadir = Path(node["datadir"])
            datadir.mkdir(parents=True, exist_ok=True)

            addnode_args = []
            for other in self.nodes[: node["id"]]:
                addnode_args.append(f"-addnode=127.0.0.1:{other['p2p_port']}")

            cmd = [
                self.bitcoind,
                f"-{CHAIN}",
                "-daemon=0",
                "-server=1",
                "-listen=1",
                "-listenonion=0",
                "-discover=0",
                "-dnsseed=0",
                "-fixedseeds=0",
                "-txindex=1",
                "-fallbackfee=0.0001",
                "-pqc=1",
                f"-datadir={datadir}",
                f"-rpcport={node['rpc_port']}",
                f"-port={node['p2p_port']}",
                f"-bind=127.0.0.1:{node['p2p_port']}",
                f"-rpcbind=127.0.0.1:{node['rpc_port']}",
                "-rpcallowip=127.0.0.0/8",
            ] + addnode_args

            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.node_procs.append(proc)

        for node in self.nodes:
            self.wait_ready(node["id"])
            info = self.node_cli_json(node["id"], "getblockchaininfo")
            self.log(f"node {node['id']} ready: height={info['blocks']} peers={self.node_cli_json(node['id'], 'getconnectioncount')}")

        self.mesh_connect()

    def mesh_connect(self) -> None:
        self.log("Connecting nodes into a mesh...")
        for i in range(self.args.nodes):
            for j in range(self.args.nodes):
                if i == j:
                    continue
                try:
                    self.node_cli(i, "addnode", f"127.0.0.1:{self.nodes[j]['p2p_port']}", "onetry")
                except Exception:
                    pass
        time.sleep(3)

    def create_wallets(self) -> None:
        self.log(f"Creating {self.args.nodes * self.args.wallets_per_node} wallets...")
        for node_id in range(self.args.nodes):
            for w in range(self.args.wallets_per_node):
                name = f"n{node_id}w{w}"
                try:
                    self.node_cli(node_id, "createwallet", name)
                except Exception:
                    try:
                        self.node_cli(node_id, "loadwallet", name)
                    except Exception:
                        pass
                addr = self.node_cli(node_id, "getnewaddress", wallet=name)
                self.wallets.append((node_id, name, addr))
                self.wallet_addrs[(node_id, name)] = addr

        self.miner_wallet = (0, "n0w0")
        self.miner_addr = self.wallet_addrs[self.miner_wallet]

    def mine(self, node_id: int, wallet: str, count: int = 1) -> None:
        addr = self.wallet_addrs[(node_id, wallet)]
        self.node_cli_json(node_id, "generatetoaddress", str(count), addr, wallet=wallet, timeout=180)
        self.mined_blocks += count

    def sync_height(self, min_height: int | None = None, timeout: int = 120) -> None:
        deadline = time.time() + timeout
        last_heights: Sequence[int] = []
        while time.time() < deadline:
            heights = [self.node_cli_json(nid, "getblockchaininfo")["blocks"] for nid in range(self.args.nodes)]
            last_heights = heights
            if len(set(heights)) == 1 and (min_height is None or heights[0] >= min_height):
                return
            time.sleep(1)
        raise TestAbort(f"nodes did not sync in time: heights={last_heights}")

    def fund_wallets(self) -> None:
        self.log(f"Mining {self.args.initial_blocks} blocks for mature funds...")
        miner_name = self.miner_wallet[1]
        batch = 25
        remaining = self.args.initial_blocks
        while remaining > 0:
            mine_now = min(batch, remaining)
            self.mine(0, miner_name, mine_now)
            remaining -= mine_now
        self.sync_height(min_height=self.args.initial_blocks)

        self.log(f"Funding wallets with {self.args.fund_amount:.3f} QBTC each...")
        funded = 0
        for node_id, name, addr in self.wallets:
            if (node_id, name) == self.miner_wallet:
                continue
            try:
                self.node_cli(0, "sendtoaddress", addr, f"{self.args.fund_amount:.8f}", wallet=miner_name)
                funded += 1
            except Exception as exc:
                self.log(f"warn: funding {name} failed: {exc}")
            if funded % 10 == 0:
                self.mine(0, miner_name, 1)
        self.mine(0, miner_name, 6)
        self.sync_height()
        self.log(f"Funding complete: {funded}/{len(self.wallets) - 1} wallets funded")

    def get_wallet_balance(self, node_id: int, wallet: str) -> float:
        try:
            bal = self.node_cli(node_id, "getbalance", wallet=wallet)
            return float(bal)
        except Exception:
            return 0.0

    def top_up_low_wallets(self, active_wallets: Sequence[WalletRef], threshold: float = 0.1, amount: float = 1.5) -> None:
        miner_name = self.miner_wallet[1]
        topped = 0
        for node_id, wallet in active_wallets:
            if (node_id, wallet) == self.miner_wallet:
                continue
            if self.get_wallet_balance(node_id, wallet) >= threshold:
                continue
            addr = self.wallet_addrs[(node_id, wallet)]
            try:
                self.node_cli(0, "sendtoaddress", addr, f"{amount:.8f}", wallet=miner_name)
                topped += 1
            except Exception:
                pass
            if topped and topped % 8 == 0:
                self.mine(0, miner_name, 1)
        if topped:
            self.mine(0, miner_name, 1)

    def pick_destination(self, sender: WalletRef, active_wallets: Sequence[WalletRef]) -> str:
        if len(active_wallets) < 2:
            return self.wallet_addrs[sender]
        while True:
            dst = self.random.choice(active_wallets)
            if dst != sender:
                return self.wallet_addrs[dst]

    def send_one(self, sender: WalletRef, active_wallets: Sequence[WalletRef], amount_min: float, amount_max: float) -> None:
        node_id, wallet = sender
        bal = self.get_wallet_balance(node_id, wallet)
        if bal <= max(amount_min * 2, 0.01):
            self.tx_fail += 1
            return
        dest = self.pick_destination(sender, active_wallets)
        amount = min(round(self.random.uniform(amount_min, amount_max), 8), max(0.001, bal * 0.25))
        try:
            self.node_cli(node_id, "sendtoaddress", dest, f"{amount:.8f}", wallet=wallet)
            self.tx_ok += 1
        except Exception:
            self.tx_fail += 1

    def collect_metrics(self, phase: str, active_nodes: int, active_wallets: Sequence[WalletRef]) -> dict:
        node0 = self.node_cli_json(0, "getblockchaininfo")
        blockhash = self.node_cli(0, "getbestblockhash")
        block = self.node_cli_json(0, "getblock", blockhash)
        try:
            rpc_difficulty = float(self.node_cli(0, "getdifficulty"))
        except Exception:
            rpc_difficulty = float(node0.get("difficulty", 0.0) or 0.0)
        mempool = self.node_cli_json(0, "getmempoolinfo")
        return {
            "timestamp": int(time.time()),
            "elapsed_sec": int(time.time() - self.start_time),
            "phase": phase,
            "active_miners": active_nodes,
            "active_wallets": len(active_wallets),
            "height": int(node0.get("blocks", 0)),
            "difficulty": float(node0.get("difficulty", rpc_difficulty) or rpc_difficulty),
            "rpc_difficulty": rpc_difficulty,
            "bits": block.get("bits", ""),
            "mempool_size": int(mempool.get("size", 0)),
            "mempool_bytes": int(mempool.get("bytes", 0)),
            "dag_tips": int(node0.get("dag_tips", 0)),
            "connections": int(self.node_cli(0, "getconnectioncount")),
            "tx_ok": self.tx_ok,
            "tx_fail": self.tx_fail,
            "mined_blocks": self.mined_blocks,
        }

    def run_phase(self, phase: Phase) -> None:
        active_node_ids = list(range(phase.active_nodes))
        active_wallets: List[WalletRef] = [
            (node_id, f"n{node_id}w{w}")
            for node_id in active_node_ids
            for w in range(self.args.wallets_per_node)
        ]
        active_miners: List[WalletRef] = [(node_id, f"n{node_id}w0") for node_id in active_node_ids]

        self.log(
            f"Phase {phase.name}: {phase.duration_sec}s | miners={len(active_miners)} | "
            f"wallets={len(active_wallets)} | tx-interval={phase.wallet_interval:.2f}s"
        )

        started = time.time()
        next_sample = started
        next_topup = started + 30
        last_send_due: Dict[WalletRef, float] = {w: started for w in active_wallets}
        last_mine_due: Dict[WalletRef, float] = {m: started for m in active_miners}

        phase_start = self.collect_metrics(phase.name + "_start", len(active_miners), active_wallets)
        self.samples.append(phase_start)

        while time.time() - started < phase.duration_sec:
            now = time.time()

            for miner in active_miners:
                if now >= last_mine_due[miner]:
                    nid, wallet = miner
                    try:
                        self.mine(nid, wallet, 1)
                    except Exception:
                        pass
                    jitter = self.random.uniform(0.0, max(0.25, phase.mine_interval * 0.15))
                    last_mine_due[miner] = now + phase.mine_interval + jitter

            senders = list(active_wallets)
            self.random.shuffle(senders)
            for sender in senders:
                if now >= last_send_due[sender]:
                    self.send_one(sender, active_wallets, phase.amount_min, phase.amount_max)
                    jitter = self.random.uniform(0.0, max(0.02, phase.wallet_interval * 0.25))
                    last_send_due[sender] = now + phase.wallet_interval + jitter

            if now >= next_topup:
                self.top_up_low_wallets(active_wallets)
                next_topup = now + 45

            if now >= next_sample:
                self.samples.append(self.collect_metrics(phase.name, len(active_miners), active_wallets))
                next_sample = now + self.args.sample_seconds

            time.sleep(0.05)

        phase_end = self.collect_metrics(phase.name + "_end", len(active_miners), active_wallets)
        self.samples.append(phase_end)
        self.phase_bounds.append({"phase": phase.name, "start": phase_start, "end": phase_end})

    def build_phases(self) -> List[Phase]:
        phases: List[Phase] = []
        low_min = self.args.low_amount_min
        low_max = self.args.low_amount_max
        attack_min = self.args.attack_amount_min
        attack_max = self.args.attack_amount_max

        for n in range(1, self.args.nodes + 1):
            phases.append(
                Phase(
                    name=f"baseline_ramp_{n}",
                    duration_sec=int(self.args.phase_minutes * 60),
                    active_nodes=n,
                    wallet_interval=self.args.low_wallet_interval,
                    mine_interval=self.args.mine_interval,
                    amount_min=low_min,
                    amount_max=low_max,
                )
            )

        phases.append(
            Phase(
                name="spam_attack",
                duration_sec=int(self.args.attack_minutes * 60),
                active_nodes=self.args.nodes,
                wallet_interval=self.args.attack_wallet_interval,
                mine_interval=self.args.attack_mine_interval,
                amount_min=attack_min,
                amount_max=attack_max,
            )
        )

        for n in range(self.args.nodes - 1, 0, -1):
            phases.append(
                Phase(
                    name=f"recovery_ramp_{n}",
                    duration_sec=int(self.args.phase_minutes * 60),
                    active_nodes=n,
                    wallet_interval=self.args.recovery_wallet_interval,
                    mine_interval=self.args.mine_interval,
                    amount_min=low_min,
                    amount_max=low_max,
                )
            )

        return phases

    def write_csv(self) -> Path:
        out = self.output_dir / self.args.csv_name
        if not self.samples:
            return out
        with out.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(self.samples[0].keys()))
            writer.writeheader()
            writer.writerows(self.samples)
        return out

    def summarize_phase(self, phase_name: str) -> dict:
        rows = [row for row in self.samples if row["phase"] == phase_name]
        if not rows:
            return {}
        diffs = [float(r["difficulty"]) for r in rows]
        mempools = [int(r["mempool_size"]) for r in rows]
        return {
            "phase": phase_name,
            "samples": len(rows),
            "difficulty_min": min(diffs),
            "difficulty_max": max(diffs),
            "difficulty_avg": statistics.fmean(diffs),
            "mempool_avg": statistics.fmean(mempools) if mempools else 0.0,
            "mempool_max": max(mempools) if mempools else 0,
            "height_start": rows[0]["height"],
            "height_end": rows[-1]["height"],
            "tx_ok_delta": rows[-1]["tx_ok"] - rows[0]["tx_ok"],
            "tx_fail_delta": rows[-1]["tx_fail"] - rows[0]["tx_fail"],
        }

    def write_markdown_report(self) -> Path:
        out = self.output_dir / self.args.report_name
        baseline_rows = [r for r in self.samples if r["phase"].startswith("baseline_ramp_")]
        attack_rows = [r for r in self.samples if r["phase"] == "spam_attack"]
        recovery_rows = [r for r in self.samples if r["phase"].startswith("recovery_ramp_")]

        def median_diff(rows: Sequence[dict]) -> float:
            if not rows:
                return 0.0
            vals = [float(r["difficulty"]) for r in rows]
            return statistics.median(vals)

        baseline_median = median_diff(baseline_rows)
        attack_peak = max((float(r["difficulty"]) for r in attack_rows), default=0.0)
        recovery_final = float(recovery_rows[-1]["difficulty"]) if recovery_rows else 0.0

        attack_ratio = (attack_peak / baseline_median) if baseline_median > 0 else 0.0
        recovery_ratio = (recovery_final / baseline_median) if baseline_median > 0 else 0.0

        lines = [
            "# qBTC Load-Aware DAA v2 Ramp Test Report",
            "",
            "## Run Configuration",
            "",
            f"- Nodes: {self.args.nodes}",
            f"- Wallets per node: {self.args.wallets_per_node}",
            f"- Phase minutes: {self.args.phase_minutes}",
            f"- Attack minutes: {self.args.attack_minutes}",
            f"- Chain: {CHAIN}",
            f"- Successful sends: {self.tx_ok}",
            f"- Failed sends: {self.tx_fail}",
            f"- Blocks mined: {self.mined_blocks}",
            "",
            "## Difficulty Summary",
            "",
            f"- Baseline median difficulty: {baseline_median:.8f}",
            f"- Attack peak difficulty: {attack_peak:.8f}",
            f"- Attack / baseline ratio: {attack_ratio:.4f}x",
            f"- Recovery final difficulty: {recovery_final:.8f}",
            f"- Recovery / baseline ratio: {recovery_ratio:.4f}x",
            "",
            "## Phase Table",
            "",
            "| Phase | Samples | Height Δ | Avg difficulty | Peak difficulty | Avg mempool | Max mempool | TX ok | TX fail |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]

        seen = []
        for row in self.samples:
            phase = row["phase"]
            if phase.endswith("_start") or phase.endswith("_end") or phase in seen:
                continue
            seen.append(phase)
            summary = self.summarize_phase(phase)
            if not summary:
                continue
            height_delta = int(summary["height_end"]) - int(summary["height_start"])
            lines.append(
                f"| {phase} | {summary['samples']} | {height_delta} | "
                f"{summary['difficulty_avg']:.8f} | {summary['difficulty_max']:.8f} | "
                f"{summary['mempool_avg']:.2f} | {summary['mempool_max']} | "
                f"{summary['tx_ok_delta']} | {summary['tx_fail_delta']} |"
            )

        lines.extend([
            "",
            "## Interpretation",
            "",
            "Use this run as a go/no-go check for the new sqrt-based load-aware DAA:",
            "",
            "1. Peak attack difficulty should rise above the baseline band.",
            "2. Recovery phases should trend downward after spam stops.",
            "3. The final recovery band should move back toward the earlier baseline band.",
            "",
            "If the attack ratio trends toward the configured cap and recovery relaxes back down,",
            "the algorithm is behaving as intended under realistic staged load.",
        ])

        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out

    def stop_nodes(self) -> None:
        self.log("Stopping nodes...")
        for node_id in range(self.args.nodes):
            try:
                self.node_cli(node_id, "stop", timeout=30)
            except Exception:
                pass
        for proc in self.node_procs:
            try:
                proc.wait(timeout=20)
            except Exception:
                try:
                    proc.terminate()
                except Exception:
                    pass
        if not self.args.keep_datadir:
            shutil.rmtree(self.datadir_root, ignore_errors=True)

    def run(self) -> int:
        self.start_time = time.time()
        try:
            self.start_nodes()
            self.create_wallets()
            self.fund_wallets()

            for phase in self.build_phases():
                self.run_phase(phase)

            csv_path = self.write_csv()
            report_path = self.write_markdown_report()
            self.log(f"CSV report written to: {csv_path}")
            self.log(f"Markdown report written to: {report_path}")
            return 0
        except KeyboardInterrupt:
            self.log("Interrupted by user")
            return 130
        except Exception as exc:
            self.log(f"FATAL: {exc}")
            return 1
        finally:
            self.stop_nodes()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Realistic staged qBTC DAA v2 ramp/spam/recovery test")
    parser.add_argument("--bitcoind", default=os.environ.get("BITCOIND"), help="Path to bitcoind")
    parser.add_argument("--cli", default=os.environ.get("CLI"), help="Path to bitcoin-cli")
    parser.add_argument("--nodes", type=int, default=8, help="Number of miners/nodes to ramp up to")
    parser.add_argument("--wallets-per-node", type=int, default=5, help="Wallets created per node")
    parser.add_argument("--phase-minutes", type=float, default=3.0, help="Minutes for each ramp phase")
    parser.add_argument("--attack-minutes", type=float, default=6.0, help="Minutes for the spam phase")
    parser.add_argument("--sample-seconds", type=int, default=15, help="Metric sample interval")
    parser.add_argument("--low-wallet-interval", type=float, default=15.0, help="Seconds between sends per wallet during low-load phases")
    parser.add_argument("--recovery-wallet-interval", type=float, default=20.0, help="Seconds between sends per wallet during recovery phases")
    parser.add_argument("--attack-wallet-interval", type=float, default=0.75, help="Seconds between sends per wallet during the attack phase")
    parser.add_argument("--mine-interval", type=float, default=8.0, help="Seconds between mine attempts per active miner during baseline/recovery")
    parser.add_argument("--attack-mine-interval", type=float, default=5.0, help="Seconds between mine attempts per active miner during the attack phase")
    parser.add_argument("--fund-amount", type=float, default=12.0, help="Initial funding amount per wallet")
    parser.add_argument("--initial-blocks", type=int, default=220, help="Initial blocks to mine for mature spendable balance")
    parser.add_argument("--low-amount-min", type=float, default=0.001, help="Minimum send amount during low-load phases")
    parser.add_argument("--low-amount-max", type=float, default=0.01, help="Maximum send amount during low-load phases")
    parser.add_argument("--attack-amount-min", type=float, default=0.001, help="Minimum send amount during attack phase")
    parser.add_argument("--attack-amount-max", type=float, default=0.03, help="Maximum send amount during attack phase")
    parser.add_argument("--base-rpc-port", type=int, default=DEFAULT_BASE_PORT, help="Base RPC port for node 0")
    parser.add_argument("--base-p2p-port", type=int, default=DEFAULT_P2P_PORT, help="Base P2P port for node 0")
    parser.add_argument("--seed", type=int, default=42, help="PRNG seed for reproducibility")
    parser.add_argument(
        "--datadir-root",
        default=str(Path(os.environ.get("TMPDIR", str(Path.cwd() / ".tmp"))) / "qbtc-daa-v2-ramp"),
        help="Root directory for node datadirs",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path.cwd() / "test-results" / "daa-v2-ramp"),
        help="Directory for CSV and Markdown outputs",
    )
    parser.add_argument("--csv-name", default="daa_v2_ramp_metrics.csv", help="CSV metrics filename")
    parser.add_argument("--report-name", default="daa_v2_ramp_report.md", help="Markdown report filename")
    parser.add_argument("--keep-datadir", action="store_true", help="Keep datadirs after completion")
    parser.add_argument("--keep-existing-datadir", action="store_true", help="Do not delete existing datadir root before startup")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    tester = QBtcRampTest(args)
    return tester.run()


if __name__ == "__main__":
    sys.exit(main())
