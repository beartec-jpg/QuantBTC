#!/usr/bin/env python3
"""BearTec QBTC pool MVP service.

Features provided now:
- public Stratum V1-style JSON-RPC listener
- worker authorization and share accounting in SQLite
- live getblocktemplate polling from the local QBTC node
- simple HTTP stats API for the BearTec frontend
- payout engine scaffold (dry-run by default)

Notes:
- This is an MVP bridge for testnet and operator validation.
- Share submission acceptance is intentionally lightweight for now; it records
  submissions against known jobs and is ready to be upgraded to full
  proof-of-work/share verification in the next iteration.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import secrets
import signal
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib import request


RPC_URL = os.environ.get("QBTC_POOL_RPC_URL", "http://127.0.0.1:28332/")
RPC_USER = os.environ.get("QBTC_POOL_RPC_USER", "qbtcverify")
RPC_PASS = os.environ.get("QBTC_POOL_RPC_PASS", "verify_node3_2026")
STRATUM_HOST = os.environ.get("QBTC_POOL_HOST", "0.0.0.0")
STRATUM_PORT = int(os.environ.get("QBTC_POOL_PORT", "3333"))
HTTP_HOST = os.environ.get("QBTC_POOL_HTTP_HOST", "0.0.0.0")
HTTP_PORT = int(os.environ.get("QBTC_POOL_HTTP_PORT", "8088"))
DB_PATH = os.environ.get("QBTC_POOL_DB", "/var/lib/qbtc-pool/pool.db")
PAYOUT_THRESHOLD = float(os.environ.get("QBTC_POOL_PAYOUT_THRESHOLD", "25.0"))
ENABLE_PAYOUTS = os.environ.get("QBTC_POOL_ENABLE_PAYOUTS", "0") == "1"
PAYOUT_INTERVAL_SEC = int(os.environ.get("QBTC_POOL_PAYOUT_INTERVAL_SEC", "3600"))
POOL_NAME = os.environ.get("QBTC_POOL_NAME", "BearTec QBTC Pool")
POOL_FEE = float(os.environ.get("QBTC_POOL_FEE", "1.0"))
SHARE_REWARD = float(os.environ.get("QBTC_POOL_SHARE_REWARD", "0.01"))
REWARD_METHOD = os.environ.get("QBTC_POOL_REWARD_METHOD", "PPS").upper()
HISTORY_WINDOW_SEC = int(os.environ.get("QBTC_POOL_HISTORY_WINDOW_SEC", str(24 * 60 * 60)))
HISTORY_BUCKET_SEC = int(os.environ.get("QBTC_POOL_HISTORY_BUCKET_SEC", "300"))
SNAPSHOT_INTERVAL_SEC = int(os.environ.get("QBTC_POOL_SNAPSHOT_INTERVAL_SEC", "60"))
if REWARD_METHOD not in {"PPS", "PPLNS"}:
    REWARD_METHOD = "PPS"


def ensure_parent_dir(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


class RPCClient:
    def __init__(self, url: str, user: str, password: str):
        self.url = url
        token = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {
            "Authorization": f"Basic {token}",
            "Content-Type": "text/plain",
        }

    def call(self, method: str, params: list[Any] | None = None) -> Any:
        payload = json.dumps({
            "jsonrpc": "1.0",
            "id": method,
            "method": method,
            "params": params or [],
        }).encode()
        req = request.Request(self.url, data=payload, headers=self.headers, method="POST")
        with request.urlopen(req, timeout=15) as resp:
            body = json.loads(resp.read().decode())
        if body.get("error"):
            raise RuntimeError(str(body["error"]))
        return body.get("result")


class PoolDB:
    def __init__(self, path: str):
        ensure_parent_dir(path)
        self.path = path
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS workers (
                    worker_name TEXT PRIMARY KEY,
                    payout_address TEXT,
                    authorized_at INTEGER,
                    last_seen INTEGER,
                    accepted_shares INTEGER DEFAULT 0,
                    invalid_shares INTEGER DEFAULT 0,
                    pending_balance REAL DEFAULT 0,
                    total_paid REAL DEFAULT 0,
                    weighted_shares REAL DEFAULT 0,
                    last_share_at INTEGER
                );

                CREATE TABLE IF NOT EXISTS shares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    worker_name TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    round_id TEXT,
                    accepted INTEGER NOT NULL,
                    submitted_at INTEGER NOT NULL,
                    nonce TEXT,
                    ntime TEXT,
                    extranonce2 TEXT,
                    difficulty REAL DEFAULT 1.0,
                    reward_value REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS rounds (
                    round_id TEXT PRIMARY KEY,
                    height INTEGER,
                    prevhash TEXT,
                    started_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL,
                    status TEXT DEFAULT 'open',
                    total_shares INTEGER DEFAULT 0,
                    accepted_shares INTEGER DEFAULT 0,
                    weighted_shares REAL DEFAULT 0,
                    total_rewards REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS pool_history (
                    sampled_at INTEGER PRIMARY KEY,
                    accepted_shares INTEGER DEFAULT 0,
                    invalid_shares INTEGER DEFAULT 0,
                    connected_miners INTEGER DEFAULT 0,
                    pending_payouts REAL DEFAULT 0
                );

                CREATE INDEX IF NOT EXISTS idx_shares_worker_time ON shares(worker_name, submitted_at);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_shares_unique_submission ON shares(worker_name, job_id, nonce, ntime, extranonce2);
                CREATE INDEX IF NOT EXISTS idx_pool_history_time ON pool_history(sampled_at);
                """
            )
            for statement in (
                "ALTER TABLE workers ADD COLUMN weighted_shares REAL DEFAULT 0",
                "ALTER TABLE workers ADD COLUMN last_share_at INTEGER",
                "ALTER TABLE shares ADD COLUMN round_id TEXT",
                "ALTER TABLE shares ADD COLUMN reward_value REAL DEFAULT 0",
            ):
                try:
                    conn.execute(statement)
                except sqlite3.OperationalError:
                    pass
            try:
                conn.execute("CREATE INDEX IF NOT EXISTS idx_shares_round_time ON shares(round_id, submitted_at)")
            except sqlite3.OperationalError:
                pass

    def authorize_worker(self, worker_name: str) -> None:
        now = int(time.time())
        payout_address = worker_name.split(".", 1)[0] if "." in worker_name else worker_name
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO workers(worker_name, payout_address, authorized_at, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(worker_name) DO UPDATE SET last_seen=excluded.last_seen
                """,
                (worker_name, payout_address, now, now),
            )
            conn.commit()

    def ensure_round(self, round_id: str, height: int, prevhash: str) -> None:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO rounds(round_id, height, prevhash, started_at, updated_at, status)
                VALUES (?, ?, ?, ?, ?, 'open')
                ON CONFLICT(round_id) DO UPDATE SET
                    updated_at=excluded.updated_at,
                    height=excluded.height,
                    prevhash=excluded.prevhash,
                    status='open'
                """,
                (round_id, height, prevhash, now, now),
            )
            conn.execute(
                "UPDATE rounds SET status='closed' WHERE round_id != ? AND status='open'",
                (round_id,),
            )
            conn.commit()

    def record_share(
        self,
        worker_name: str,
        job_id: str,
        round_id: str,
        accepted: bool,
        nonce: str,
        ntime: str,
        extranonce2: str,
        difficulty: float = 1.0,
    ) -> tuple[bool, str]:
        now = int(time.time())
        payout_address = worker_name.split(".", 1)[0] if "." in worker_name else worker_name
        difficulty = max(float(difficulty or 1.0), 1.0)
        reward_value = round(difficulty * SHARE_REWARD, 8) if accepted else 0.0

        with self._lock, self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO shares(worker_name, job_id, round_id, accepted, submitted_at, nonce, ntime, extranonce2, difficulty, reward_value)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (worker_name, job_id, round_id, 1 if accepted else 0, now, nonce, ntime, extranonce2, difficulty, reward_value),
                )
            except sqlite3.IntegrityError:
                conn.execute(
                    """
                    INSERT INTO workers(worker_name, payout_address, authorized_at, last_seen, invalid_shares)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(worker_name) DO UPDATE SET
                        last_seen=excluded.last_seen,
                        invalid_shares=workers.invalid_shares + 1
                    """,
                    (worker_name, payout_address, now, now),
                )
                conn.commit()
                return False, "duplicate-share"

            if round_id:
                conn.execute(
                    """
                    INSERT INTO rounds(round_id, height, prevhash, started_at, updated_at, status, total_shares, accepted_shares, weighted_shares, total_rewards)
                    VALUES (?, 0, '', ?, ?, 'open', 1, ?, ?, ?)
                    ON CONFLICT(round_id) DO UPDATE SET
                        updated_at=excluded.updated_at,
                        total_shares=rounds.total_shares + 1,
                        accepted_shares=rounds.accepted_shares + ?,
                        weighted_shares=rounds.weighted_shares + ?,
                        total_rewards=rounds.total_rewards + ?
                    """,
                    (round_id, now, now, 1 if accepted else 0, difficulty if accepted else 0.0, reward_value, 1 if accepted else 0, difficulty if accepted else 0.0, reward_value),
                )
            if accepted:
                conn.execute(
                    """
                    INSERT INTO workers(worker_name, payout_address, authorized_at, last_seen, last_share_at, accepted_shares, weighted_shares, pending_balance)
                    VALUES (?, ?, ?, ?, ?, 1, ?, ?)
                    ON CONFLICT(worker_name) DO UPDATE SET
                        last_seen=excluded.last_seen,
                        last_share_at=excluded.last_share_at,
                        accepted_shares=workers.accepted_shares + 1,
                        weighted_shares=workers.weighted_shares + ?,
                        pending_balance=workers.pending_balance + ?
                    """,
                    (worker_name, payout_address, now, now, now, difficulty, reward_value, difficulty, reward_value),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO workers(worker_name, payout_address, authorized_at, last_seen, invalid_shares)
                    VALUES (?, ?, ?, ?, 1)
                    ON CONFLICT(worker_name) DO UPDATE SET
                        last_seen=excluded.last_seen,
                        invalid_shares=workers.invalid_shares + 1
                    """,
                    (worker_name, payout_address, now, now),
                )
            conn.commit()
            return accepted, "accepted" if accepted else "stale-or-unauthorized-share"

    def stats(self) -> dict[str, Any]:
        since = int(time.time()) - 86400
        with self._lock, self._connect() as conn:
            worker_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS authorized_workers,
                    COALESCE(SUM(accepted_shares), 0) AS accepted_shares,
                    COALESCE(SUM(invalid_shares), 0) AS invalid_shares,
                    COALESCE(SUM(weighted_shares), 0) AS weighted_shares,
                    COALESCE(SUM(pending_balance), 0) AS pending_payouts,
                    COALESCE(SUM(total_paid), 0) AS total_paid,
                    CASE
                        WHEN COALESCE(SUM(accepted_shares), 0) + COALESCE(SUM(invalid_shares), 0) > 0
                        THEN ROUND((COALESCE(SUM(accepted_shares), 0) * 100.0) /
                          (COALESCE(SUM(accepted_shares), 0) + COALESCE(SUM(invalid_shares), 0)), 2)
                        ELSE 100.0
                    END AS acceptance_rate
                FROM workers
                """
            ).fetchone()
            earnings_row = conn.execute(
                """
                SELECT COALESCE(SUM(reward_value), 0) AS earnings_24h
                FROM shares
                WHERE accepted = 1 AND submitted_at >= ?
                """,
                (since,),
            ).fetchone()
            round_row = conn.execute(
                """
                SELECT round_id, height, started_at, updated_at, total_shares, accepted_shares, weighted_shares, total_rewards
                FROM rounds
                ORDER BY started_at DESC
                LIMIT 1
                """
            ).fetchone()
            worker_rows = conn.execute(
                """
                SELECT w.worker_name, w.payout_address, w.last_seen, w.last_share_at,
                       w.accepted_shares, w.invalid_shares, w.weighted_shares,
                       w.pending_balance, w.total_paid,
                       CASE
                           WHEN (w.accepted_shares + w.invalid_shares) > 0
                           THEN ROUND((w.accepted_shares * 100.0) / (w.accepted_shares + w.invalid_shares), 2)
                           ELSE 100.0
                       END AS acceptance_rate,
                       COALESCE((
                         SELECT SUM(s.reward_value)
                         FROM shares s
                         WHERE s.worker_name = w.worker_name AND s.accepted = 1 AND s.submitted_at >= ?
                       ), 0) AS earnings_24h
                FROM workers w
                ORDER BY w.last_seen DESC
                LIMIT 25
                """,
                (since,),
            ).fetchall()

        workers: list[dict[str, Any]] = []
        for row in worker_rows:
            item = dict(row)
            pending_balance = round(float(item.get("pending_balance") or 0.0), 8)
            earnings_24h = round(float(item.get("earnings_24h") or 0.0), 8)
            item["pending_balance"] = pending_balance
            item["total_paid"] = round(float(item.get("total_paid") or 0.0), 8)
            item["weighted_shares"] = round(float(item.get("weighted_shares") or 0.0), 4)
            item["earnings_24h"] = earnings_24h
            item["remaining_to_payout"] = round(max(PAYOUT_THRESHOLD - pending_balance, 0.0), 8)
            if earnings_24h > 0:
                item["estimated_hours_to_payout"] = round(item["remaining_to_payout"] / (earnings_24h / 24.0), 2)
            else:
                item["estimated_hours_to_payout"] = None
            workers.append(item)

        return {
            "authorized_workers": int(worker_row["authorized_workers"] or 0),
            "accepted_shares": int(worker_row["accepted_shares"] or 0),
            "invalid_shares": int(worker_row["invalid_shares"] or 0),
            "weighted_shares": round(float(worker_row["weighted_shares"] or 0.0), 4),
            "pending_payouts": round(float(worker_row["pending_payouts"] or 0.0), 8),
            "total_paid": round(float(worker_row["total_paid"] or 0.0), 8),
            "pool_acceptance_rate": round(float(worker_row["acceptance_rate"] or 100.0), 2),
            "pool_earnings_24h": round(float(earnings_row["earnings_24h"] or 0.0), 8),
            "reward_method": REWARD_METHOD,
            "share_reward": SHARE_REWARD,
            "payout_threshold": PAYOUT_THRESHOLD,
            "payout_interval_sec": PAYOUT_INTERVAL_SEC,
            "current_round_id": round_row["round_id"] if round_row else None,
            "current_round_height": int(round_row["height"] or 0) if round_row else None,
            "current_round_shares": int(round_row["accepted_shares"] or 0) if round_row else 0,
            "current_round_weighted_shares": round(float(round_row["weighted_shares"] or 0.0), 4) if round_row else 0.0,
            "workers": workers,
        }

    def record_pool_snapshot(self, snapshot: dict[str, Any]) -> None:
        sampled_at = int(time.time())
        sampled_at -= sampled_at % max(SNAPSHOT_INTERVAL_SEC, 60)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO pool_history(sampled_at, accepted_shares, invalid_shares, connected_miners, pending_payouts)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(sampled_at) DO UPDATE SET
                    accepted_shares=excluded.accepted_shares,
                    invalid_shares=excluded.invalid_shares,
                    connected_miners=excluded.connected_miners,
                    pending_payouts=excluded.pending_payouts
                """,
                (
                    sampled_at,
                    int(snapshot.get("accepted_shares") or 0),
                    int(snapshot.get("invalid_shares") or 0),
                    int(snapshot.get("connected_miners") or 0),
                    float(snapshot.get("pending_payouts") or 0.0),
                ),
            )
            conn.execute(
                "DELETE FROM pool_history WHERE sampled_at < ?",
                (int(time.time()) - max(HISTORY_WINDOW_SEC * 2, 172800),),
            )
            conn.commit()

    def history_24h(self) -> list[dict[str, Any]]:
        now = int(time.time())
        bucket = max(HISTORY_BUCKET_SEC, 60)
        start = now - HISTORY_WINDOW_SEC
        start -= start % bucket

        with self._lock, self._connect() as conn:
            share_rows = conn.execute(
                """
                SELECT ((submitted_at - ?) / ?) AS bucket_id,
                       SUM(CASE WHEN accepted = 1 THEN 1 ELSE 0 END) AS accepted_count,
                       SUM(CASE WHEN accepted = 0 THEN 1 ELSE 0 END) AS rejected_count
                FROM shares
                WHERE submitted_at >= ?
                GROUP BY bucket_id
                ORDER BY bucket_id ASC
                """,
                (start, bucket, start),
            ).fetchall()
            snapshot_rows = conn.execute(
                """
                SELECT ((sampled_at - ?) / ?) AS bucket_id,
                       MAX(connected_miners) AS connected_miners,
                       MAX(pending_payouts) AS pending_payouts
                FROM pool_history
                WHERE sampled_at >= ?
                GROUP BY bucket_id
                ORDER BY bucket_id ASC
                """,
                (start, bucket, start),
            ).fetchall()

        share_map = {
            int(row["bucket_id"]): {
                "accepted": int(row["accepted_count"] or 0),
                "rejected": int(row["rejected_count"] or 0),
            }
            for row in share_rows
        }
        snapshot_map = {
            int(row["bucket_id"]): {
                "workers": int(row["connected_miners"] or 0),
                "pending": round(float(row["pending_payouts"] or 0.0), 8),
            }
            for row in snapshot_rows
        }

        accepted_total = 0
        rejected_total = 0
        last_workers = 0
        last_pending = 0.0
        points: list[dict[str, Any]] = []

        bucket_count = max(int(HISTORY_WINDOW_SEC / bucket), 1)
        for bucket_id in range(bucket_count + 1):
            accepted_delta = share_map.get(bucket_id, {}).get("accepted", 0)
            rejected_delta = share_map.get(bucket_id, {}).get("rejected", 0)
            accepted_total += accepted_delta
            rejected_total += rejected_delta
            if bucket_id in snapshot_map:
                last_workers = snapshot_map[bucket_id]["workers"]
                last_pending = snapshot_map[bucket_id]["pending"]
            ts = start + (bucket_id * bucket)
            points.append({
                "time": time.strftime("%H:%M", time.localtime(ts)),
                "timestamp": ts * 1000,
                "accepted24h": accepted_total,
                "rejected24h": rejected_total,
                "workers": last_workers,
                "pending": round(last_pending, 8),
                "hashrate": round((accepted_delta * 4294967296) / bucket, 2) if accepted_delta > 0 else 0.0,
            })
        return points

    def matured_payouts(self, threshold: float) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT worker_name, payout_address, pending_balance
                FROM workers
                WHERE pending_balance >= ?
                ORDER BY pending_balance DESC
                """,
                (threshold,),
            ).fetchall()
        return [dict(r) for r in rows]

    def mark_paid(self, worker_name: str, amount: float) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                UPDATE workers
                SET pending_balance = MAX(pending_balance - ?, 0),
                    total_paid = total_paid + ?
                WHERE worker_name = ?
                """,
                (amount, amount, worker_name),
            )
            conn.commit()


@dataclass
class PoolClient:
    writer: asyncio.StreamWriter
    subscription_id: str = field(default_factory=lambda: secrets.token_hex(8))
    authorized: bool = False
    worker_name: str | None = None
    difficulty: float = 1.0


class PoolServer:
    def __init__(self, rpc: RPCClient, db: PoolDB):
        self.rpc = rpc
        self.db = db
        self.clients: dict[int, PoolClient] = {}
        self.clients_lock = asyncio.Lock()
        self.job_lock = asyncio.Lock()
        self.current_job: dict[str, Any] = {
            "job_id": "bootstrap",
            "round_id": "bootstrap",
            "prevhash": "00" * 32,
            "coinb1": "",
            "coinb2": "",
            "merkle_branches": [],
            "version": "20000000",
            "nbits": "1d00ffff",
            "ntime": f"{int(time.time()):08x}",
            "clean_jobs": True,
            "height": 0,
        }

    async def send_json(self, writer: asyncio.StreamWriter, payload: dict[str, Any]) -> None:
        writer.write((json.dumps(payload) + "\n").encode())
        await writer.drain()

    async def notify(self, writer: asyncio.StreamWriter, method: str, params: list[Any]) -> None:
        await self.send_json(writer, {"id": None, "method": method, "params": params})

    async def broadcast_job(self) -> None:
        async with self.clients_lock:
            clients = list(self.clients.values())
        params = [
            self.current_job["job_id"],
            self.current_job["prevhash"],
            self.current_job["coinb1"],
            self.current_job["coinb2"],
            self.current_job["merkle_branches"],
            self.current_job["version"],
            self.current_job["nbits"],
            self.current_job["ntime"],
            self.current_job["clean_jobs"],
        ]
        for client in clients:
            if client.authorized:
                try:
                    await self.notify(client.writer, "mining.notify", params)
                except Exception:
                    pass

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        client_id = id(writer)
        client = PoolClient(writer=writer)
        async with self.clients_lock:
            self.clients[client_id] = client
        try:
            peer = writer.get_extra_info("peername")
            print(f"client connected: {peer}")
            while True:
                line = await reader.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line.decode().strip())
                except json.JSONDecodeError:
                    await self.send_json(writer, {"id": None, "result": None, "error": [20, "invalid json", None]})
                    continue

                method = msg.get("method")
                params = msg.get("params", [])
                req_id = msg.get("id")

                if method == "mining.subscribe":
                    await self.send_json(writer, {
                        "id": req_id,
                        "result": [[["mining.notify", client.subscription_id], ["mining.set_difficulty", client.subscription_id]], client.subscription_id, 4],
                        "error": None,
                    })
                    await self.notify(writer, "mining.set_difficulty", [1])
                    await self.broadcast_job()
                elif method == "mining.authorize":
                    worker_name = params[0] if params else f"anonymous.{client.subscription_id}"
                    client.worker_name = worker_name
                    client.authorized = True
                    self.db.authorize_worker(worker_name)
                    await self.send_json(writer, {"id": req_id, "result": True, "error": None})
                    await self.notify(writer, "mining.set_difficulty", [1])
                    job = self.current_job
                    await self.notify(writer, "mining.notify", [job["job_id"], job["prevhash"], job["coinb1"], job["coinb2"], job["merkle_branches"], job["version"], job["nbits"], job["ntime"], True])
                elif method == "mining.submit":
                    worker_name = params[0] if len(params) > 0 else (client.worker_name or "unknown")
                    job_id = params[1] if len(params) > 1 else ""
                    extranonce2 = params[2] if len(params) > 2 else ""
                    ntime = params[3] if len(params) > 3 else ""
                    nonce = params[4] if len(params) > 4 else ""
                    accepted = bool(client.authorized and job_id == self.current_job.get("job_id"))
                    share_ok, reason = self.db.record_share(
                        worker_name,
                        job_id,
                        str(self.current_job.get("round_id", "")),
                        accepted,
                        nonce,
                        ntime,
                        extranonce2,
                        client.difficulty,
                    )
                    if share_ok:
                        await self.send_json(writer, {"id": req_id, "result": True, "error": None})
                    else:
                        await self.send_json(writer, {"id": req_id, "result": None, "error": [23, reason, None]})
                elif method in {"mining.extranonce.subscribe", "mining.configure"}:
                    await self.send_json(writer, {"id": req_id, "result": True, "error": None})
                else:
                    await self.send_json(writer, {"id": req_id, "result": None, "error": [24, f"unsupported method: {method}", None]})
        finally:
            async with self.clients_lock:
                self.clients.pop(client_id, None)
            writer.close()
            await writer.wait_closed()

    async def template_updater(self) -> None:
        while True:
            try:
                tmpl = await asyncio.to_thread(self.rpc.call, "getblocktemplate", [{"rules": ["segwit"]}])
                async with self.job_lock:
                    prevhash = tmpl.get("previousblockhash", "")
                    ntime = f"{int(tmpl.get('curtime', int(time.time()))):08x}"
                    height = int(tmpl.get("height", 0))
                    round_id = f"{height}:{prevhash[:16]}"
                    next_job = {
                        "job_id": secrets.token_hex(6),
                        "round_id": round_id,
                        "prevhash": prevhash,
                        "coinb1": "",
                        "coinb2": "",
                        "merkle_branches": [],
                        "version": f"{int(tmpl.get('version', 0)):08x}",
                        "nbits": tmpl.get("bits", "1d00ffff"),
                        "ntime": ntime,
                        "clean_jobs": True,
                        "height": height,
                    }
                    changed = next_job["prevhash"] != self.current_job.get("prevhash") or next_job["ntime"] != self.current_job.get("ntime")
                    self.current_job = next_job
                await asyncio.to_thread(self.db.ensure_round, round_id, height, prevhash)
                if changed:
                    await self.broadcast_job()
            except Exception as exc:
                print(f"template updater error: {exc}")
            await asyncio.sleep(10)

    async def payout_loop(self) -> None:
        while True:
            try:
                for payout in self.db.matured_payouts(PAYOUT_THRESHOLD):
                    if not ENABLE_PAYOUTS:
                        print(f"payout dry-run: worker={payout['worker_name']} amount={payout['pending_balance']}")
                        continue
                    address = payout["payout_address"]
                    amount = round(float(payout["pending_balance"]), 8)
                    txid = await asyncio.to_thread(self.rpc.call, "sendtoaddress", [address, amount])
                    print(f"payout sent: worker={payout['worker_name']} txid={txid}")
                    self.db.mark_paid(payout["worker_name"], amount)
            except Exception as exc:
                print(f"payout loop error: {exc}")
            await asyncio.sleep(max(PAYOUT_INTERVAL_SEC, 60))

    async def metrics_loop(self) -> None:
        while True:
            try:
                self.stats_snapshot(include_history=False, record_sample=True)
            except Exception as exc:
                print(f"metrics loop error: {exc}")
            await asyncio.sleep(max(SNAPSHOT_INTERVAL_SEC, 30))

    def stats_snapshot(self, include_history: bool = True, record_sample: bool = True) -> dict[str, Any]:
        db_stats = self.db.stats()
        snapshot = {
            "pool_name": POOL_NAME,
            "running": True,
            "pool_fee_percent": POOL_FEE,
            "connected_miners": sum(1 for c in self.clients.values() if c.authorized),
            "last_template_height": int(self.current_job.get("height", 0)),
            "last_job_id": self.current_job.get("job_id"),
            "reward_method": REWARD_METHOD,
            "share_reward": SHARE_REWARD,
            "payout_threshold": PAYOUT_THRESHOLD,
            "payout_interval_sec": PAYOUT_INTERVAL_SEC,
            **db_stats,
        }
        if record_sample:
            self.db.record_pool_snapshot(snapshot)
        if include_history:
            snapshot["history_24h"] = self.db.history_24h()
        return snapshot


class StatsHandler(BaseHTTPRequestHandler):
    server_version = "QBTCPool/0.1"

    def _json(self, code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        pool: PoolServer = self.server.pool  # type: ignore[attr-defined]
        if self.path == "/health":
            self._json(200, {"ok": True, "service": "qbtc-pool"})
        elif self.path == "/stats":
            self._json(200, pool.stats_snapshot())
        elif self.path == "/workers":
            self._json(200, {"workers": pool.db.stats()["workers"]})
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def start_http_server(pool: PoolServer) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), StatsHandler)
    httpd.pool = pool  # type: ignore[attr-defined]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


async def main() -> None:
    rpc = RPCClient(RPC_URL, RPC_USER, RPC_PASS)
    db = PoolDB(DB_PATH)
    pool = PoolServer(rpc, db)

    await asyncio.to_thread(rpc.call, "startsv2transport", [])
    await asyncio.to_thread(rpc.call, "getblockcount", [])

    httpd = start_http_server(pool)
    server = await asyncio.start_server(pool.handle_client, STRATUM_HOST, STRATUM_PORT)

    print(f"{POOL_NAME} listening on {STRATUM_HOST}:{STRATUM_PORT}")
    print(f"HTTP stats on {HTTP_HOST}:{HTTP_PORT}")

    stop_event = asyncio.Event()

    def _stop(*_: Any) -> None:
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, _stop)

    async with server:
        updater_task = asyncio.create_task(pool.template_updater())
        payout_task = asyncio.create_task(pool.payout_loop())
        metrics_task = asyncio.create_task(pool.metrics_loop())
        await stop_event.wait()
        updater_task.cancel()
        payout_task.cancel()
        metrics_task.cancel()
        httpd.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
