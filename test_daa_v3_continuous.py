#!/usr/bin/env python3
"""
QBTC DAA v3 — Continuous Mining Test
=====================================

Each miner node gets its own thread that mines as fast as possible.
No artificial delays.  The DAA should push difficulty up as block times
drop below the 10 s target and ease off when miners leave.

Phases:
  1. BOOTSTRAP — node-0 mines 260 blocks (past EMA activation), funds wallets
  2. GROWTH    — add miners one at a time; each mines continuously
  3. SPAM      — blast transactions from all wallets
  4. SETTLE    — stop spam, keep mining, watch difficulty relax
"""
from __future__ import annotations

import argparse, csv, json, os, random, shutil, statistics
import subprocess, sys, threading, time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CHAIN = "qbtctestnet"

# ─────────────────────────────────────────────────────────────────────────────

def _resolve_bin(repo: Path, env: Optional[str], name: str) -> str:
    for p in [env and Path(env), repo / "build-fresh" / "src" / name,
              repo / "src" / name]:
        if p and p.exists():
            return str(p.resolve())
    return name


@dataclass
class Sample:
    ts: int = 0
    elapsed: int = 0
    phase: str = ""
    miners: int = 0
    wallets: int = 0
    height: int = 0
    difficulty: float = 0.0
    bits: str = ""
    mempool: int = 0
    tips: int = 0
    tx_ok: int = 0
    tx_fail: int = 0
    blocks_mined: int = 0
    avg_bt: float = 0.0

    def as_dict(self) -> dict:
        return self.__dict__.copy()


class DAAv3Test:
    def __init__(self, a: argparse.Namespace):
        self.args = a
        self.repo = Path(__file__).resolve().parent
        self.bitcoind = _resolve_bin(self.repo, a.bitcoind, "bitcoind")
        self.cli_bin = _resolve_bin(self.repo, a.cli, "bitcoin-cli")
        self.datadir = Path(a.datadir).resolve()
        self.outdir = Path(a.outdir).resolve()
        self.outdir.mkdir(parents=True, exist_ok=True)

        self.nodes = [{"id": i,
                       "rpc": a.base_rpc + i * 100,
                       "p2p": a.base_p2p + i * 100}
                      for i in range(a.nodes)]

        self.procs: Dict[int, subprocess.Popen] = {}
        self.joined: List[int] = []
        self.addrs: Dict[Tuple[int,str], str] = {}   # (nid, wallet) -> addr
        self.miners_active: List[Tuple[int,str]] = []
        self.all_wallets: List[Tuple[int,str]] = []

        self.samples: List[Sample] = []
        self.tx_ok = 0
        self.tx_fail = 0
        self.blocks_mined = 0
        self.rng = random.Random(a.seed)

        self.stop_flag = threading.Event()
        self.spam_flag = threading.Event()        # set when spam is on
        self.lock = threading.Lock()
        self.t0 = 0.0

        # per-miner stop events so we can stop individual miners
        self.miner_stops: Dict[int, threading.Event] = {}

    # ── helpers ──────────────────────────────────────────────────────────────

    def log(self, msg: str):
        ts = time.strftime("%H:%M:%S")
        e = int(time.time() - self.t0) if self.t0 else 0
        m, s = divmod(e, 60)
        print(f"[{ts}] t+{m:02d}:{s:02d}  {msg}", flush=True)

    def _dd(self, nid: int) -> Path:
        return self.datadir / f"node{nid}"

    def cli(self, nid: int, *args, wallet: str | None = None,
            timeout: int = 120) -> str:
        n = self.nodes[nid]
        cmd = [self.cli_bin, f"-{CHAIN}", f"-datadir={self._dd(nid)}",
               f"-rpcport={n['rpc']}"]
        if wallet:
            cmd.append(f"-rpcwallet={wallet}")
        cmd.extend(args)
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout).strip()[:300])
        return r.stdout.strip()

    def cli_json(self, nid, *args, **kw):
        return json.loads(self.cli(nid, *args, **kw))

    def height(self, nid=0) -> int:
        try: return int(self.cli_json(nid, "getblockchaininfo")["blocks"])
        except: return 0

    def balance(self, nid, w) -> float:
        try: return float(self.cli(nid, "getbalance", wallet=w))
        except: return 0.0

    # ── node lifecycle ───────────────────────────────────────────────────────

    def start_node(self, nid: int):
        dd = self._dd(nid)
        dd.mkdir(parents=True, exist_ok=True)
        n = self.nodes[nid]
        addnode = [f"-addnode=127.0.0.1:{self.nodes[o]['p2p']}"
                   for o in self.joined]
        cmd = [
            self.bitcoind, f"-{CHAIN}", "-daemon=0", "-server=1", "-listen=1",
            "-listenonion=0", "-discover=0", "-dnsseed=0", "-fixedseeds=0",
            "-txindex=1", "-fallbackfee=0.0001", "-pqc=1",
            f"-datadir={dd}", f"-rpcport={n['rpc']}", f"-port={n['p2p']}",
            f"-bind=127.0.0.1:{n['p2p']}",
            f"-rpcbind=127.0.0.1:{n['rpc']}",
            "-rpcallowip=127.0.0.0/8",
        ] + addnode
        self.procs[nid] = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for _ in range(90):
            try:
                self.cli_json(nid, "getblockchaininfo"); break
            except: time.sleep(1)
        else:
            raise RuntimeError(f"node {nid} didn't start")

        # bidirectional peering
        for o in self.joined:
            try: self.cli(nid, "addnode",
                          f"127.0.0.1:{self.nodes[o]['p2p']}", "onetry")
            except: pass
            try: self.cli(o, "addnode",
                          f"127.0.0.1:{n['p2p']}", "onetry")
            except: pass
        self.joined.append(nid)

        peers = 0
        try: peers = int(self.cli(nid, "getconnectioncount"))
        except: pass
        self.log(f"Node {nid} up  rpc={n['rpc']} p2p={n['p2p']} peers={peers}")

    def create_wallets(self, nid: int):
        for w in range(self.args.wallets_per_node):
            name = f"n{nid}w{w}"
            try: self.cli(nid, "createwallet", name)
            except:
                try: self.cli(nid, "loadwallet", name)
                except: pass
            addr = self.cli(nid, "getnewaddress", wallet=name)
            self.addrs[(nid, name)] = addr
            with self.lock:
                self.all_wallets.append((nid, name))

    def fund_wallets(self, nid: int, funder=(0, "n0w0")):
        fn, fw = funder
        funded = 0
        for w in range(self.args.wallets_per_node):
            name = f"n{nid}w{w}"
            if (nid, name) == funder:
                continue
            addr = self.addrs[(nid, name)]
            try:
                self.cli(fn, "sendtoaddress", addr,
                         f"{self.args.fund:.8f}", wallet=fw)
                funded += 1
            except: pass
        if funded:
            self._mine_one(fn, fw)
        self.log(f"  funded {funded} wallets on node {nid}")

    def _mine_one(self, nid, w, count=1) -> int:
        addr = self.addrs[(nid, w)]
        try:
            self.cli_json(nid, "generatetoaddress", str(count), addr,
                          wallet=w, timeout=max(300, count * 120))
            with self.lock:
                self.blocks_mined += count
            return count
        except:
            return 0

    def wait_sync(self, nid, timeout=120):
        tgt = self.height(0)
        end = time.time() + timeout
        while time.time() < end:
            if self.height(nid) >= tgt: return
            time.sleep(1)

    # ── continuous mining thread (one per miner) ─────────────────────────────

    def _miner_loop(self, nid: int, wallet: str, stop_ev: threading.Event):
        """Mine continuously on node `nid` using `wallet` until stop_ev."""
        addr = self.addrs[(nid, wallet)]
        while not stop_ev.is_set() and not self.stop_flag.is_set():
            try:
                self.cli_json(nid, "generatetoaddress", "1", addr,
                              wallet=wallet, timeout=300)
                with self.lock:
                    self.blocks_mined += 1
            except Exception:
                # node busy / reorging — brief pause then retry
                time.sleep(0.5)

    def start_miner(self, nid: int):
        wallet = f"n{nid}w0"
        ev = threading.Event()
        self.miner_stops[nid] = ev
        with self.lock:
            self.miners_active.append((nid, wallet))
        t = threading.Thread(target=self._miner_loop,
                             args=(nid, wallet, ev), daemon=True)
        t.start()
        self.log(f"Miner {nid} started (continuous)")

    def stop_miner(self, nid: int):
        ev = self.miner_stops.get(nid)
        if ev:
            ev.set()
        with self.lock:
            self.miners_active = [(n,w) for n,w in self.miners_active
                                  if n != nid]
        self.log(f"Miner {nid} stopped")

    # ── tx spam thread ───────────────────────────────────────────────────────

    def _spam_loop(self):
        while not self.stop_flag.is_set():
            if not self.spam_flag.is_set():
                time.sleep(0.5); continue
            with self.lock:
                ws = list(self.all_wallets)
            if len(ws) < 2:
                time.sleep(0.5); continue
            src_nid, src_w = self.rng.choice(ws)
            dst_nid, dst_w = self.rng.choice(ws)
            if (src_nid, src_w) == (dst_nid, dst_w):
                continue
            bal = self.balance(src_nid, src_w)
            if bal < 0.01:
                time.sleep(0.2); continue
            amt = round(self.rng.uniform(0.001, min(0.05, bal * 0.15)), 8)
            dst = self.addrs[(dst_nid, dst_w)]
            try:
                self.cli(src_nid, "sendtoaddress", dst,
                         f"{amt:.8f}", wallet=src_w)
                with self.lock: self.tx_ok += 1
            except:
                with self.lock: self.tx_fail += 1
            # small breathing room to not overload RPC
            time.sleep(0.1)

    # ── sampling ─────────────────────────────────────────────────────────────

    def sample(self, phase: str) -> Sample:
        info = self.cli_json(0, "getblockchaininfo")
        bh = self.cli(0, "getbestblockhash")
        blk = self.cli_json(0, "getblock", bh)
        mp = self.cli_json(0, "getmempoolinfo")

        h = int(info["blocks"])
        span = min(20, h - 1)
        avg_bt = 0.0
        if span >= 2:
            try:
                cur = bh; times = []
                for _ in range(span + 1):
                    hdr = self.cli_json(0, "getblockheader", cur)
                    times.append(int(hdr["time"]))
                    cur = hdr.get("previousblockhash", "")
                    if not cur: break
                if len(times) >= 2:
                    avg_bt = (times[0] - times[-1]) / (len(times) - 1)
            except: pass

        s = Sample(
            ts=int(time.time()), elapsed=int(time.time()-self.t0),
            phase=phase, miners=len(self.miners_active),
            wallets=len(self.all_wallets), height=h,
            difficulty=float(info.get("difficulty", 0)),
            bits=blk.get("bits", ""),
            mempool=int(mp.get("size", 0)),
            tips=int(info.get("dag_tips", 0)),
            tx_ok=self.tx_ok, tx_fail=self.tx_fail,
            blocks_mined=self.blocks_mined, avg_bt=round(avg_bt, 2))
        self.samples.append(s)
        return s

    def print_sample(self, s: Sample):
        self.log(
            f"[{s.phase:<14}] h={s.height:<6} diff={s.difficulty:<14.8f} "
            f"miners={s.miners}  mempool={s.mempool:<4} tips={s.tips}  "
            f"tx={s.tx_ok}/{s.tx_fail}  avg_bt={s.avg_bt:.1f}s  "
            f"mined={s.blocks_mined}")

    def sample_loop(self, phase: str, duration_sec: float):
        end = time.time() + duration_sec
        nxt = time.time() + self.args.sample_sec
        while time.time() < end and not self.stop_flag.is_set():
            if time.time() >= nxt:
                s = self.sample(phase)
                self.print_sample(s)
                nxt = time.time() + self.args.sample_sec
            time.sleep(0.5)

    # ── phases ───────────────────────────────────────────────────────────────

    def bootstrap(self):
        self.log("=" * 60)
        self.log("BOOTSTRAP: node-0, mine 260 blocks, fund wallets")
        self.log("=" * 60)
        self.start_node(0)
        self.create_wallets(0)

        target = self.args.bootstrap_blocks
        self.log(f"Mining {target} bootstrap blocks...")
        stuck = 0
        while self.height(0) < target:
            h = self.height(0)
            batch = min(10, target - h)
            mined = self._mine_one(0, "n0w0", batch)
            if not mined:
                stuck += 1
                if stuck > 10: break
                time.sleep(1); continue
            stuck = 0
            cur = self.height(0)
            if cur % 50 == 0 or cur >= target:
                self.log(f"  bootstrap: {cur}/{target}")

        self.log(f"Bootstrap done: h={self.height(0)}")

        # wait for maturity
        for _ in range(60):
            if self.balance(0, "n0w0") > 1.0: break
            self._mine_one(0, "n0w0", 5)
            time.sleep(0.5)
        self.log(f"Funder balance: {self.balance(0, 'n0w0'):.2f} QBTC")

        self.fund_wallets(0)
        self._mine_one(0, "n0w0", 3)

    def growth(self):
        grow_sec = self.args.grow_min * 60
        self.log("=" * 60)
        self.log("GROWTH: starting continuous miners one by one")
        self.log("=" * 60)

        # start miner-0 + spam threads
        self.start_miner(0)
        for _ in range(self.args.spam_threads):
            threading.Thread(target=self._spam_loop, daemon=True).start()
        # light background tx during growth
        self.spam_flag.set()

        for nid in range(1, self.args.nodes):
            self.log(f"--- Running with {len(self.miners_active)} miner(s) "
                     f"for {self.args.grow_min} min ---")
            self.sample_loop(f"grow_{len(self.miners_active)}", grow_sec)

            self.log(f"Adding miner-{nid}")
            self.start_node(nid)
            self.wait_sync(nid, 180)
            self.create_wallets(nid)
            self.fund_wallets(nid)
            self._mine_one(0, "n0w0", 2)
            self.start_miner(nid)
            s = self.sample(f"grow_{len(self.miners_active)}")
            self.print_sample(s)

        # run with all miners for one more interval
        self.log(f"--- Running with all {len(self.miners_active)} miners "
                 f"for {self.args.grow_min} min ---")
        self.sample_loop(f"grow_{len(self.miners_active)}", grow_sec)

    def spam_phase(self):
        self.log("=" * 60)
        self.log(f"SPAM: {self.args.spam_min} min full blast")
        self.log("=" * 60)
        self.spam_flag.set()
        self.sample_loop("spam", self.args.spam_min * 60)

    def settle(self):
        self.log("=" * 60)
        self.log(f"SETTLE: {self.args.settle_min} min cool-down")
        self.log("=" * 60)
        self.spam_flag.clear()

        # optionally stop half the miners to drop hash rate
        half = len(self.miners_active) // 2
        for i in range(half):
            nid = self.args.nodes - 1 - i
            self.stop_miner(nid)

        self.sample_loop("settle", self.args.settle_min * 60)

    # ── reporting ────────────────────────────────────────────────────────────

    def write_csv(self) -> Path:
        out = self.outdir / "daa_v3_metrics.csv"
        if not self.samples: return out
        ds = [s.as_dict() for s in self.samples]
        with out.open("w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(ds[0].keys()))
            w.writeheader(); w.writerows(ds)
        return out

    def write_report(self) -> Path:
        out = self.outdir / "daa_v3_report.md"

        def rows(pfx): return [s for s in self.samples
                                if s.phase.startswith(pfx)]
        def med(rs): return statistics.median([s.difficulty for s in rs]) \
                            if rs else 0
        def avg(rs): return statistics.fmean([s.difficulty for s in rs]) \
                            if rs else 0
        def mx(rs):  return max((s.difficulty for s in rs), default=0)
        def mn(rs):  return min((s.difficulty for s in rs), default=0)
        def abt(rs):
            v = [s.avg_bt for s in rs if s.avg_bt > 0]
            return statistics.fmean(v) if v else 0

        growth = rows("grow_")
        spam   = rows("spam")
        settle = rows("settle")

        bmed = med(growth); apk = mx(spam); smed = med(settle)
        ar = (apk / bmed) if bmed else 0
        sr = (smed / bmed) if bmed else 0
        tot = self.samples[-1].elapsed if self.samples else 0
        fh  = self.samples[-1].height if self.samples else 0

        L = [
            "# qBTC DAA v3 — Continuous Mining Report", "",
            f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Chain:** {CHAIN}",
            f"**Elapsed:** {tot//60}m {tot%60}s", "",
            "## Config", "",
            "| Param | Value |", "| --- | --- |",
            f"| Nodes | {self.args.nodes} |",
            f"| Wallets/node | {self.args.wallets_per_node} |",
            f"| Grow interval | {self.args.grow_min} min |",
            f"| Spam duration | {self.args.spam_min} min |",
            f"| Settle duration | {self.args.settle_min} min |",
            f"| Bootstrap blocks | {self.args.bootstrap_blocks} |",
            f"| Mining | continuous (no delay) |", "",
            "## Summary", "",
            "| Metric | Value |", "| --- | --- |",
            f"| Final height | {fh} |",
            f"| Blocks mined | {self.blocks_mined} |",
            f"| TX ok / fail | {self.tx_ok} / {self.tx_fail} |", "",
            "## Difficulty", "",
            "| Phase | Median | Mean | Min | Max | Avg BT |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
            f"| Growth | {med(growth):.8f} | {avg(growth):.8f} | "
            f"{mn(growth):.8f} | {mx(growth):.8f} | {abt(growth):.2f}s |",
            f"| Spam | {med(spam):.8f} | {avg(spam):.8f} | "
            f"{mn(spam):.8f} | {mx(spam):.8f} | {abt(spam):.2f}s |",
            f"| Settle | {med(settle):.8f} | {avg(settle):.8f} | "
            f"{mn(settle):.8f} | {mx(settle):.8f} | {abt(settle):.2f}s |", "",
            f"| Attack/baseline ratio | {ar:.4f}x |",
            f"| Settle/baseline ratio | {sr:.4f}x |", "",
            "## Samples", "",
            "| t | Phase | Height | Difficulty | Mempool | BT | Miners |",
            "| ---: | --- | ---: | ---: | ---: | ---: | ---: |",
        ]
        for s in self.samples:
            L.append(f"| {s.elapsed} | {s.phase} | {s.height} | "
                     f"{s.difficulty:.8f} | {s.mempool} | "
                     f"{s.avg_bt:.1f} | {s.miners} |")

        L += ["", "## Growth Steps", "",
              "| Step | Miners | Median diff | Avg BT |",
              "| --- | ---: | ---: | ---: |"]
        for n in range(1, self.args.nodes + 1):
            rs = [s for s in self.samples if s.phase == f"grow_{n}"]
            if rs:
                L.append(f"| grow_{n} | {rs[-1].miners} | "
                         f"{med(rs):.8f} | {abt(rs):.2f} |")

        L += ["", "## Verdict", ""]
        if ar > 1.2:
            L.append("**PASS:** Difficulty responded to increased mining.")
        else:
            L.append("**INVESTIGATE:** Difficulty did not notably rise under"
                      " load.")
        if 0.3 < sr < 2.5:
            L.append("**PASS:** Settle difficulty close to baseline.")
        else:
            L.append(f"**NOTE:** Settle/baseline = {sr:.4f}x")
        L.append("")

        out.write_text("\n".join(L), encoding="utf-8")
        return out

    # ── cleanup ──────────────────────────────────────────────────────────────

    def stop_all(self):
        self.stop_flag.set()
        for ev in self.miner_stops.values():
            ev.set()
        self.log("Stopping nodes...")
        for nid in self.joined:
            try: self.cli(nid, "stop", timeout=30)
            except: pass
        for p in self.procs.values():
            try: p.wait(timeout=15)
            except:
                try: p.terminate()
                except: pass
        if not self.args.keep_data:
            shutil.rmtree(self.datadir, ignore_errors=True)

    # ── main ─────────────────────────────────────────────────────────────────

    def run(self) -> int:
        self.t0 = time.time()
        print("=" * 70)
        print(f"  qBTC DAA v3 — Continuous Mining Test")
        print(f"  {self.args.nodes} nodes, {self.args.wallets_per_node} "
              f"wallets/node, mining = CONTINUOUS")
        print(f"  Grow {self.args.grow_min}m/node | "
              f"Spam {self.args.spam_min}m | Settle {self.args.settle_min}m")
        print("=" * 70, flush=True)

        try:
            self.bootstrap()
            self.growth()
            self.spam_phase()
            self.settle()

            s = self.sample("final")
            self.print_sample(s)
            self.stop_flag.set()

            csv_p = self.write_csv()
            rpt_p = self.write_report()
            e = time.time() - self.t0
            print()
            self.log(f"DONE — {e/60:.1f} min")
            self.log(f"CSV:    {csv_p}")
            self.log(f"Report: {rpt_p}")
            return 0
        except KeyboardInterrupt:
            self.log("Interrupted"); self.stop_flag.set(); return 130
        except Exception as exc:
            self.log(f"FATAL: {exc}"); self.stop_flag.set(); return 1
        finally:
            self.stop_all()


def main():
    p = argparse.ArgumentParser("qBTC DAA v3 continuous mining test")
    p.add_argument("--bitcoind", default=os.environ.get("BITCOIND"))
    p.add_argument("--cli", default=os.environ.get("CLI"))
    p.add_argument("--nodes", type=int, default=4)
    p.add_argument("--wallets-per-node", type=int, default=3)
    p.add_argument("--grow-min", type=float, default=3,
                   help="Minutes between adding each miner")
    p.add_argument("--spam-min", type=float, default=5)
    p.add_argument("--settle-min", type=float, default=4)
    p.add_argument("--sample-sec", type=int, default=10)
    p.add_argument("--spam-threads", type=int, default=4)
    p.add_argument("--fund", type=float, default=25.0)
    p.add_argument("--bootstrap-blocks", type=int, default=260,
                   help="Must be >= EMA activation height (256)")
    p.add_argument("--base-rpc", type=int, default=28332)
    p.add_argument("--base-p2p", type=int, default=28333)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--datadir", default=str(
        Path(os.environ.get("TMPDIR", ".tmp")) / "qbtc-daa-v3"))
    p.add_argument("--outdir",
                   default=str(Path.cwd() / "test-results" / "daa-v3"))
    p.add_argument("--keep-data", action="store_true")
    return p.parse_args()


if __name__ == "__main__":
    sys.exit(DAAv3Test(main()).run())
