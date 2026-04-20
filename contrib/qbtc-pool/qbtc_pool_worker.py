#!/usr/bin/env python3
import hashlib
import json
import os
import random
import select
import socket
import sys
import time

HOST = os.environ.get("QBTC_POOL_HOST", "89.167.109.241")
PORT = int(os.environ.get("QBTC_POOL_PORT", "3333"))
USER = sys.argv[1]
PASSWORD = os.environ.get("QBTC_POOL_PASSWORD", "x")
ACTIVE_SEC = int(os.environ.get("QBTC_POOL_ACTIVE_SEC", "60"))
CYCLE_SEC = int(os.environ.get("QBTC_POOL_CYCLE_SEC", "300"))
BATCH_SIZE = int(os.environ.get("QBTC_POOL_BATCH_SIZE", "25000"))
MIN_DIFFICULTY = float(os.environ.get("QBTC_POOL_MIN_DIFFICULTY", "0.000001"))
DIFF1_TARGET = 0x00000000FFFF0000000000000000000000000000000000000000000000000000


def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def difficulty_to_target(difficulty: float) -> int:
    difficulty = max(float(difficulty or 0.00025), MIN_DIFFICULTY)
    return max(1, int(DIFF1_TARGET / difficulty))


def json_send(sock: socket.socket, payload: dict) -> None:
    sock.sendall((json.dumps(payload) + "\n").encode())


def build_merkle_root(job: dict, extranonce1: str, extranonce2: str) -> bytes:
    coinbase = bytes.fromhex(job.get("coinb1", "") + extranonce1 + extranonce2 + job.get("coinb2", ""))
    merkle_root = sha256d(coinbase)
    for branch in job.get("merkle_branches", []):
        merkle_root = sha256d(merkle_root + bytes.fromhex(branch))
    return merkle_root


def connect_and_mine() -> None:
    sock = socket.create_connection((HOST, PORT), timeout=10)
    sock.setblocking(False)
    file = sock.makefile("r")

    req_id = random.randint(1000, 5000)
    extranonce1 = ""
    extranonce2_size = 4
    difficulty = 0.00025
    job: dict | None = None

    json_send(sock, {"id": req_id, "method": "mining.subscribe", "params": []})
    json_send(sock, {"id": req_id + 1, "method": "mining.authorize", "params": [USER, PASSWORD]})

    while True:
        ready, _, _ = select.select([sock], [], [], 0.1)
        if ready:
            try:
                line = file.readline()
            except Exception:
                break
            if not line:
                break
            try:
                msg = json.loads(line.strip())
            except Exception:
                continue

            if msg.get("id") == req_id and isinstance(msg.get("result"), list):
                result = msg.get("result") or []
                extranonce1 = str(result[1]) if len(result) > 1 else ""
                extranonce2_size = int(result[2]) if len(result) > 2 else 4
            elif msg.get("method") == "mining.set_difficulty":
                params = msg.get("params") or []
                if params:
                    difficulty = max(float(params[0]), MIN_DIFFICULTY)
            elif msg.get("method") == "mining.notify":
                params = msg.get("params") or []
                if len(params) >= 9:
                    job = {
                        "job_id": params[0],
                        "prevhash": params[1],
                        "coinb1": params[2],
                        "coinb2": params[3],
                        "merkle_branches": params[4] or [],
                        "version": params[5],
                        "nbits": params[6],
                        "ntime": params[7],
                    }

        now = time.time()
        active_window = (int(now) % CYCLE_SEC) < ACTIVE_SEC
        if not active_window or not job or not extranonce1:
            continue

        extranonce2 = random.getrandbits(extranonce2_size * 8).to_bytes(extranonce2_size, "big").hex()
        merkle_root = build_merkle_root(job, extranonce1, extranonce2)
        header_prefix = bytes.fromhex(
            job["version"] + job["prevhash"] + merkle_root[::-1].hex() + job["ntime"] + job["nbits"]
        )
        target = difficulty_to_target(difficulty)

        for _ in range(BATCH_SIZE):
            nonce = f"{random.getrandbits(32):08x}"
            header = header_prefix + bytes.fromhex(nonce)
            share_hash = int.from_bytes(sha256d(header)[::-1], "big")
            if share_hash <= target:
                json_send(sock, {
                    "id": int(time.time()),
                    "method": "mining.submit",
                    "params": [USER, job["job_id"], extranonce2, job["ntime"], nonce],
                })
                break


def main() -> None:
    while True:
        try:
            connect_and_mine()
        except Exception:
            time.sleep(3)


if __name__ == "__main__":
    main()
