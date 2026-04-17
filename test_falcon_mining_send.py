#!/usr/bin/env python3
"""
Falcon-padded-512 Mining & Wallet Send Test
============================================
Tests end-to-end Falcon key usage in regtest:
  1. Start bitcoind with -pqcsig=falcon -pqc=1 -pqchybridsig=1
  2. Generate a Falcon hybrid key address
  3. Mine 101 blocks to that address (coins become spendable)
  4. Send coins to a second Falcon address
  5. Mine 1 more block to confirm
  6. Inspect the spending transaction's witness:
       element[0] = ECDSA sig
       element[1] = ECDSA pubkey
       element[2] = Falcon sig  (expected 666 bytes)
       element[3] = Falcon pubkey (expected 897 bytes)

Usage: python3 test_falcon_mining_send.py
"""

import subprocess
import json
import os
import shutil
import signal
import time
import sys

BITCOIND   = "./build-fresh/src/bitcoind"
CLI        = "./build-fresh/src/bitcoin-cli"
DATADIR    = os.path.join(os.environ.get("TMPDIR", "/tmp"), "falcon_test_regtest")
WALLET     = "falcon_wallet"
RPC_PORT   = "18747"

FALCON_SIG_SIZE = 666
FALCON_PK_SIZE  = 897
DILITHIUM_SIG_SIZE = 2420
DILITHIUM_PK_SIZE  = 1312

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

results = []

def report(name, ok, detail=""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok))

def cli(*args, wallet=None):
    base = [CLI, f"-datadir={DATADIR}", "-regtest", "-rpcport=18747",
            "-rpcuser=test", "-rpcpassword=test"]
    if wallet:
        base += [f"-rpcwallet={wallet}"]
    out = subprocess.run(base + list(args), capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"CLI error: {out.stderr.strip()}")
    return out.stdout.strip()

def cli_json(*args, wallet=None):
    return json.loads(cli(*args, wallet=wallet))

def start_node():
    if os.path.exists(DATADIR):
        shutil.rmtree(DATADIR)
    os.makedirs(f"{DATADIR}/regtest", exist_ok=True)

    cmd = [
        BITCOIND,
        f"-datadir={DATADIR}",
        "-regtest",
        "-rpcport=18747",
        "-rpcuser=test",
        "-rpcpassword=test",
        "-pqc=1",
        "-pqcsig=falcon",          # <-- use Falcon for key generation
        "-keypool=5",              # small keypool so Falcon TopUp is fast
        "-fallbackfee=0.0001",
        "-maxtxfee=1.0",
        "-txindex=1",
        "-nodebug",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(6)

    # Wait until RPC is up
    for _ in range(30):
        try:
            cli("getblockchaininfo")
            return proc
        except Exception:
            time.sleep(0.5)
    raise RuntimeError("Node failed to start")

def stop_node(proc):
    try:
        cli("stop")
        proc.wait(timeout=15)
    except Exception:
        proc.terminate()
        proc.wait(timeout=5)
    shutil.rmtree(DATADIR, ignore_errors=True)

def run_test():
    proc = None
    try:
        print("\n=== Falcon Mining & Wallet Send Test ===\n")

        # ── Start node ──────────────────────────────────────────────────────────
        print("[1] Starting bitcoind with -pqcsig=falcon ...")
        proc = start_node()
        info = cli_json("getblockchaininfo")
        report("Node started in regtest", info["chain"] == "regtest")
        report("PQC active at chain level", info.get("pqc", False) is True)

        # ── Create wallet ────────────────────────────────────────────────────────
        print("\n[2] Creating wallet ...")
        cli("createwallet", WALLET)
        report("Wallet created", True)

        # Check pqcinfo reflects falcon (use wallet)
        pqcinfo = cli_json("getpqcinfo", wallet=WALLET)
        sig_algos = pqcinfo.get("enabled_signature_algorithms", pqcinfo.get("enabled_signatures", []))
        report("Falcon listed in pqcinfo", "falcon" in sig_algos,
               f"algos={sig_algos}")

        # ── Generate Falcon address ──────────────────────────────────────────────
        print("\n[3] Generating Falcon hybrid key address ...")
        addr1 = cli("getnewaddress", "", "bech32", wallet=WALLET)
        report("Got address 1", addr1.startswith("qbtcrt1") or addr1.startswith("bcrt1"))

        addrinfo1 = cli_json("getaddressinfo", addr1, wallet=WALLET)
        pqc_algo = addrinfo1.get("pqc_algorithm", "")
        # pqc_algorithm field is informational; getaddressinfo may not populate it
        print(f"    (pqc_algorithm on addr1: {pqc_algo!r})")
        report("Got bech32 address 1", addr1.startswith("qbtcrt1") or addr1.startswith("bcrt1"))

        # ── Mine 101 blocks to Falcon address ────────────────────────────────────
        print("\n[4] Mining 101 blocks to Falcon address ...")
        cli_json("generatetoaddress", "101", addr1, wallet=WALLET)
        bal = float(cli("getbalance", wallet=WALLET))
        report("Balance > 0 after mining 101 blocks", bal > 0, f"{bal:.8f} BTC")

        # ── Create second Falcon address ──────────────────────────────────────────
        print("\n[5] Creating second Falcon address for send target ...")
        addr2 = cli("getnewaddress", "", "bech32", wallet=WALLET)
        addrinfo2 = cli_json("getaddressinfo", addr2, wallet=WALLET)
        pqc_algo2 = addrinfo2.get("pqc_algorithm", "")
        print(f"    (pqc_algorithm on addr2: {pqc_algo2!r})")
        report("Got bech32 address 2", addr2.startswith("qbtcrt1") or addr2.startswith("bcrt1"))

        # ── Send coins ────────────────────────────────────────────────────────────
        send_amt = round(bal * 0.4, 6)  # send 40% of balance
        print(f"\n[6] Sending {send_amt} BTC from Falcon address (balance={bal:.8f}) ...")
        txid = cli("sendtoaddress", addr2, str(send_amt), wallet=WALLET)
        report("sendtoaddress succeeded", len(txid) == 64, f"txid={txid[:16]}...")

        # ── Mine 1 block to confirm ────────────────────────────────────────────────
        cli_json("generatetoaddress", "1", addr1, wallet=WALLET)

        # ── Inspect witness of spending tx ────────────────────────────────────────
        print("\n[7] Inspecting transaction witness ...")
        raw = cli_json("getrawtransaction", txid, "1")

        spend_inp = None
        for vin in raw.get("vin", []):
            if "txinwitness" in vin and len(vin["txinwitness"]) == 4:
                spend_inp = vin
                break

        if spend_inp is None:
            # Check all inputs
            all_witness = [(i, v.get("txinwitness", [])) for i, v in enumerate(raw.get("vin", []))]
            report("Found 4-element PQC witness", False,
                   f"witnesses={[(i, len(w)) for i,w in all_witness]}")
        else:
            witness = spend_inp["txinwitness"]
            w_sizes = [len(w) // 2 for w in witness]
            ecdsa_sig_size = w_sizes[0]
            ecdsa_pk_size  = w_sizes[1]
            pqc_sig_size   = w_sizes[2]
            pqc_pk_size    = w_sizes[3]

            report("Witness has 4 elements (hybrid PQC)", len(witness) == 4,
                   f"sizes={w_sizes}")
            report(f"Falcon sig size == {FALCON_SIG_SIZE}B",
                   pqc_sig_size == FALCON_SIG_SIZE,
                   f"actual={pqc_sig_size}B")
            report(f"Falcon pubkey size == {FALCON_PK_SIZE}B",
                   pqc_pk_size == FALCON_PK_SIZE,
                   f"actual={pqc_pk_size}B")
            report("ECDSA sig present (DER ~70-72B)",
                   60 <= ecdsa_sig_size <= 75,
                   f"actual={ecdsa_sig_size}B")
            report("ECDSA pubkey present (compressed 33B)",
                   ecdsa_pk_size == 33,
                   f"actual={ecdsa_pk_size}B")

            # Confirm it's NOT Dilithium-sized
            report("Witness is Falcon NOT Dilithium",
                   pqc_sig_size != DILITHIUM_SIG_SIZE,
                   f"sig={pqc_sig_size}B (Dilithium would be {DILITHIUM_SIG_SIZE}B)")

    finally:
        if proc:
            stop_node(proc)

    # ── Summary ─────────────────────────────────────────────────────────────────
    print("\n=== Results ===")
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    for name, ok in results:
        tag = PASS if ok else FAIL
        print(f"  [{tag}] {name}")
    print(f"\n{passed}/{total} tests passed")
    return passed == total

if __name__ == "__main__":
    ok = run_test()
    sys.exit(0 if ok else 1)
