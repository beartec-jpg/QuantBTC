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
POOL_NAME = os.environ.get("QBTC_POOL_NAME", "BearTec QBTC Pool")
POOL_FEE = float(os.environ.get("QBTC_POOL_FEE", "1.0"))


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
                    total_paid REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS shares (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    worker_name TEXT NOT NULL,
                    job_id TEXT NOT NULL,
                    accepted INTEGER NOT NULL,
                    submitted_at INTEGER NOT NULL,
                    nonce TEXT,
                    ntime TEXT,
                    extranonce2 TEXT,
                    difficulty REAL DEFAULT 1.0
                );

                CREATE INDEX IF NOT EXISTS idx_shares_worker_time ON shares(worker_name, submitted_at);
                """
            )

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

    def record_share(self, worker_name: str, job_id: str, accepted: bool, nonce: str, ntime: str, extranonce2: str) -> None:
        now = int(time.time())
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO shares(worker_name, job_id, accepted, submitted_at, nonce, ntime, extranonce2)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (worker_name, job_id, 1 if accepted else 0, now, nonce, ntime, extranonce2),
            )
            if accepted:
                conn.execute(
                    """
                    INSERT INTO workers(worker_name, payout_address, authorized_at, last_seen, accepted_shares, pending_balance)
                    VALUES (?, ?, ?, ?, 1, 0.01)
                    ON CONFLICT(worker_name) DO UPDATE SET
                        last_seen=excluded.last_seen,
                        accepted_shares=workers.accepted_shares + 1,
                        pending_balance=workers.pending_balance + 0.01
                    """,
                    (worker_name, worker_name.split(".", 1)[0], now, now),
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
                    (worker_name, worker_name.split(".", 1)[0], now, now),
                )
            conn.commit()

    def stats(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            worker_row = conn.execute(
                """
                SELECT
                    COUNT(*) AS authorized_workers,
                    COALESCE(SUM(accepted_shares), 0) AS accepted_shares,
                    COALESCE(SUM(invalid_shares), 0) AS invalid_shares,
                    COALESCE(SUM(pending_balance), 0) AS pending_payouts,
                    COALESCE(SUM(total_paid), 0) AS total_paid
                FROM workers
                """
            ).fetchone()
            workers = [dict(r) for r in conn.execute(
                """
                SELECT worker_name, payout_address, last_seen, accepted_shares, invalid_shares,
                       pending_balance, total_paid
                FROM workers
                ORDER BY last_seen DESC
                LIMIT 25
                """
            )]
        return {
            "authorized_workers": int(worker_row["authorized_workers"] or 0),
            "accepted_shares": int(worker_row["accepted_shares"] or 0),
            "invalid_shares": int(worker_row["invalid_shares"] or 0),
            "pending_payouts": round(float(worker_row["pending_payouts"] or 0.0), 8),
            "total_paid": round(float(worker_row["total_paid"] or 0.0), 8),
            "workers": workers,
        }

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


class PoolServer:
    def __init__(self, rpc: RPCClient, db: PoolDB):
        self.rpc = rpc
        self.db = db
        self.clients: dict[int, PoolClient] = {}
        self.clients_lock = asyncio.Lock()
        self.job_lock = asyncio.Lock()
        self.current_job: dict[str, Any] = {
            "job_id": "bootstrap",
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
                    self.db.record_share(worker_name, job_id, accepted, nonce, ntime, extranonce2)
                    if accepted:
                        await self.send_json(writer, {"id": req_id, "result": True, "error": None})
                    else:
                        await self.send_json(writer, {"id": req_id, "result": None, "error": [23, "stale-or-unauthorized-share", None]})
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
                    next_job = {
                        "job_id": secrets.token_hex(6),
                        "prevhash": prevhash,
                        "coinb1": "",
                        "coinb2": "",
                        "merkle_branches": [],
                        "version": f"{int(tmpl.get('version', 0)):08x}",
                        "nbits": tmpl.get("bits", "1d00ffff"),
                        "ntime": ntime,
                        "clean_jobs": True,
                        "height": int(tmpl.get("height", 0)),
                    }
                    changed = next_job["prevhash"] != self.current_job.get("prevhash") or next_job["ntime"] != self.current_job.get("ntime")
                    self.current_job = next_job
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
            await asyncio.sleep(60)

    def stats_snapshot(self) -> dict[str, Any]:
        db_stats = self.db.stats()
        return {
            "pool_name": POOL_NAME,
            "running": True,
            "pool_fee_percent": POOL_FEE,
            "connected_miners": sum(1 for c in self.clients.values() if c.authorized),
            "last_template_height": int(self.current_job.get("height", 0)),
            "last_job_id": self.current_job.get("job_id"),
            **db_stats,
        }


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
        await stop_event.wait()
        updater_task.cancel()
        payout_task.cancel()
        httpd.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
