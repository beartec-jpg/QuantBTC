#!/usr/bin/env python3
"""
sim-miner.py — Throttled SHA256d stratum CPU miner for QBTC pool simulation.

Usage:
    python3 sim-miner.py --pool HOST:PORT --user ADDRESS.WORKERNAME [--cpu 15] [--password x]

The --cpu flag sets the target CPU usage percentage (default 15).
"""

import argparse
import hashlib
import json
import logging
import os
import random
import socket
import struct
import threading
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("sim-miner")


# ---------------------------------------------------------------------------
# SHA256d helpers
# ---------------------------------------------------------------------------

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def uint32_le(n: int) -> bytes:
    return struct.pack("<I", n & 0xFFFFFFFF)


def build_header(version: str, prevhash: str, merkle_root: str,
                 ntime: str, nbits: str, nonce: int) -> bytes:
    return (
        bytes.fromhex(version)[::-1]
        + bytes.fromhex(prevhash)[::-1]
        + bytes.fromhex(merkle_root)
        + bytes.fromhex(ntime)[::-1]
        + bytes.fromhex(nbits)[::-1]
        + uint32_le(nonce)
    )


def calc_merkle_root(coinbase_hash: bytes, branches: list[str]) -> bytes:
    root = coinbase_hash
    for branch in branches:
        root = sha256d(root + bytes.fromhex(branch))
    return root


def difficulty_to_target(difficulty: float) -> int:
    """Convert pool difficulty to 256-bit target integer."""
    base = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
    return int(base / max(difficulty, 1e-9))


# ---------------------------------------------------------------------------
# Stratum client
# ---------------------------------------------------------------------------

class StratumClient:
    def __init__(self, host: str, port: int, user: str, password: str, cpu_target: float):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.cpu_target = cpu_target  # 0.0–1.0

        self._sock: socket.socket | None = None
        self._buf = b""
        self._req_id = 0
        self._lock = threading.Lock()

        # Stratum state
        self.extranonce1 = ""
        self.extranonce2_size = 4
        self.difficulty = 1.0
        self.job: dict | None = None
        self._job_event = threading.Event()

    # ------------------------------------------------------------------ I/O

    def _connect(self):
        log.info("Connecting to %s:%d ...", self.host, self.port)
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(30)
        s.connect((self.host, self.port))
        self._sock = s
        log.info("Connected.")

    def _send(self, obj: dict):
        with self._lock:
            self._req_id += 1
            obj.setdefault("id", self._req_id)
            data = json.dumps(obj) + "\n"
            self._sock.sendall(data.encode())

    def _recv_line(self) -> str:
        while b"\n" not in self._buf:
            chunk = self._sock.recv(4096)
            if not chunk:
                raise ConnectionError("Pool closed connection")
            self._buf += chunk
        line, self._buf = self._buf.split(b"\n", 1)
        return line.decode().strip()

    # ------------------------------------------------------------ Handshake

    def _wait_for_reply(self, req_id: int) -> dict:
        """Read lines until we get a response matching req_id, queuing notifications."""
        while True:
            line = self._recv_line()
            if not line:
                continue
            msg = json.loads(line)
            if msg.get("id") == req_id:
                return msg
            # Queue notifications to handle after handshake
            self._handle_message(msg)

    def subscribe(self):
        self._send({
            "id": 1,
            "method": "mining.subscribe",
            "params": ["sim-miner/0.1"],
        })
        resp = self._wait_for_reply(1)
        result = resp.get("result", [])
        if isinstance(result, list) and len(result) >= 3:
            self.extranonce1 = result[1]
            self.extranonce2_size = int(result[2])
        log.info("Subscribed. extranonce1=%s size=%d", self.extranonce1, self.extranonce2_size)

    def authorize(self):
        self._send({
            "id": 2,
            "method": "mining.authorize",
            "params": [self.user, self.password],
        })
        resp = self._wait_for_reply(2)
        if not resp.get("result"):
            raise RuntimeError(f"Authorization failed: {resp}")
        log.info("Authorized as %s", self.user)

    # -------------------------------------------------------- Message loop

    def _handle_message(self, msg: dict):
        method = msg.get("method")
        if method == "mining.set_difficulty":
            self.difficulty = float(msg["params"][0])
            log.info("Difficulty set to %.4f", self.difficulty)
        elif method == "mining.notify":
            p = msg["params"]
            self.job = {
                "job_id":   p[0],
                "prevhash": p[1],
                "coinb1":   p[2],
                "coinb2":   p[3],
                "branches": p[4],
                "version":  p[5],
                "nbits":    p[6],
                "ntime":    p[7],
                "clean":    bool(p[8]) if len(p) > 8 else False,
            }
            self._job_event.set()
            log.debug("New job %s (clean=%s)", p[0], self.job["clean"])

    def listen(self):
        """Background thread: receive and dispatch pool messages."""
        while True:
            try:
                line = self._recv_line()
                if not line:
                    continue
                msg = json.loads(line)
                self._handle_message(msg)
            except Exception as exc:
                log.error("Listener error: %s", exc)
                time.sleep(2)

    # ------------------------------------------------------------ Mining

    def _make_extranonce2(self) -> str:
        return os.urandom(self.extranonce2_size).hex()

    def _submit(self, job_id: str, extranonce2: str, ntime: str, nonce: int):
        nonce_hex = f"{nonce:08x}"
        log.info("Submitting share job=%s nonce=%s", job_id, nonce_hex)
        self._send({
            "method": "mining.submit",
            "params": [self.user, job_id, extranonce2, ntime, nonce_hex],
        })

    def mine_loop(self):
        """Mine with throttled CPU usage."""
        target_ratio = max(0.01, min(1.0, self.cpu_target))
        batch = 5000  # hashes per batch before checking throttle / job change

        while True:
            self._job_event.wait(timeout=30)
            if self.job is None:
                continue

            job = self.job
            extranonce2 = self._make_extranonce2()
            coinbase_raw = (
                bytes.fromhex(job["coinb1"])
                + bytes.fromhex(self.extranonce1)
                + bytes.fromhex(extranonce2)
                + bytes.fromhex(job["coinb2"])
            )
            coinbase_hash = sha256d(coinbase_raw)
            merkle_root_bytes = calc_merkle_root(coinbase_hash, job["branches"])
            merkle_root_hex = merkle_root_bytes.hex()

            target = difficulty_to_target(self.difficulty)
            nonce = random.randint(0, 0xFFFFFFFF)
            hashes = 0

            t0 = time.monotonic()

            while self.job is job:  # keep mining until new job
                for _ in range(batch):
                    header = build_header(
                        job["version"], job["prevhash"], merkle_root_hex,
                        job["ntime"], job["nbits"], nonce,
                    )
                    h = int.from_bytes(sha256d(header)[::-1], "big")
                    if h <= target:
                        self._submit(job["job_id"], extranonce2, job["ntime"], nonce)
                        # Pick new extranonce2 after share
                        extranonce2 = self._make_extranonce2()
                        coinbase_raw = (
                            bytes.fromhex(job["coinb1"])
                            + bytes.fromhex(self.extranonce1)
                            + bytes.fromhex(extranonce2)
                            + bytes.fromhex(job["coinb2"])
                        )
                        coinbase_hash = sha256d(coinbase_raw)
                        merkle_root_bytes = calc_merkle_root(coinbase_hash, job["branches"])
                        merkle_root_hex = merkle_root_bytes.hex()
                    nonce = (nonce + 1) & 0xFFFFFFFF
                    hashes += 1

                # Throttle: sleep so active_time / total_time ≈ target_ratio
                elapsed = time.monotonic() - t0
                sleep_time = elapsed * (1.0 - target_ratio) / target_ratio
                if sleep_time > 0:
                    time.sleep(sleep_time)
                t0 = time.monotonic()

            self._job_event.clear()

    # --------------------------------------------------------------- Run

    def run(self):
        while True:
            try:
                self._connect()
                self._sock.settimeout(60)
                self.subscribe()
                self.authorize()

                listener = threading.Thread(target=self.listen, daemon=True)
                listener.start()

                self.mine_loop()

            except Exception as exc:
                log.error("Connection lost: %s — reconnecting in 10s", exc)
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._buf = b""
                self.job = None
                self._job_event.clear()
                time.sleep(10)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Throttled QBTC stratum miner")
    parser.add_argument("--pool", default="89.167.109.241:3333",
                        help="Pool host:port (default: 89.167.109.241:3333)")
    parser.add_argument("--user", required=True,
                        help="Worker username, e.g. ADDRESS.workername")
    parser.add_argument("--password", default="x", help="Worker password")
    parser.add_argument("--cpu", type=float, default=15.0,
                        help="Target CPU usage percent (default: 15)")
    args = parser.parse_args()

    host, port = args.pool.rsplit(":", 1)
    client = StratumClient(
        host=host,
        port=int(port),
        user=args.user,
        password=args.password,
        cpu_target=args.cpu / 100.0,
    )
    client.run()


if __name__ == "__main__":
    main()
