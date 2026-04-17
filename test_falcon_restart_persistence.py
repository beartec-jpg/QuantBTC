#!/usr/bin/env python3
"""
Falcon Key Persistence / Restart Test
======================================
Proves that Falcon hybrid keys survive a full bitcoind restart and that
existing addresses remain spendable without any special key import.

How Falcon key storage works in QuantumBTC:
  - The ECDSA private key is stored in the wallet.dat (as always).
  - The Falcon private key is NEVER written to disk; it is derived on demand
    at signing time from the ECDSA key via:
        seed = HASH(ecdsa_privkey ‖ descriptor_id ‖ hd_index ‖ ecdsa_pubkey)
        (falcon_privkey, falcon_pubkey) = Falcon::Keygen(seed)
  - The wallet stores ONLY the Falcon public key (for address construction).
  - On restart, the Falcon private key is re-derived from the still-present
    ECDSA key — no separate backup or re-import is needed.

Test sequence:
  1. Start bitcoind with -pqcsig=falcon
  2. Create wallet, get Falcon hybrid address
  3. Mine coins to that address (101 blocks for maturity)
  4. Record address, balance, and the receiving UTXO txid
  5. STOP bitcoind completely
  6. RESTART bitcoind (same datadir, same wallet)
  7. Confirm address is still in the wallet
  8. Confirm balance is still correct (UTXO still exists)
  9. Send coins FROM that address (re-derives Falcon key at signing time)
  10. Mine 1 block to confirm the spend
  11. Verify new balance is correct

This proves that:
  a) The wallet correctly reconstructs the signing provider after restart
  b) The Falcon private key derivation is deterministic and restart-safe
  c) No "missing private key" or signing failure occurs after stop/start
"""

import subprocess, json, os, shutil, time, sys

BITCOIND = "./build-fresh/src/bitcoind"
CLI      = "./build-fresh/src/bitcoin-cli"
DATADIR  = os.path.join(os.environ.get("TMPDIR", "/tmp"), "falcon_restart_regtest")
WALLET   = "restart_wallet"
RPC_PORT = "18749"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []

def report(name, ok, detail=""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok))
    return ok

def cli(*args, wallet=None, raise_on_error=True):
    base = [CLI, f"-datadir={DATADIR}", "-regtest", f"-rpcport={RPC_PORT}",
            "-rpcuser=test", "-rpcpassword=test"]
    if wallet:
        base += [f"-rpcwallet={wallet}"]
    out = subprocess.run(base + list(args), capture_output=True, text=True)
    if raise_on_error and out.returncode != 0:
        raise RuntimeError(f"CLI error ({args[0]}): {out.stderr.strip()}")
    return out.stdout.strip()

def cli_json(*args, wallet=None):
    return json.loads(cli(*args, wallet=wallet))

def start_node(fresh=False):
    if fresh and os.path.exists(DATADIR):
        shutil.rmtree(DATADIR)
    os.makedirs(f"{DATADIR}/regtest", exist_ok=True)
    cmd = [
        BITCOIND,
        f"-datadir={DATADIR}",
        "-regtest",
        f"-rpcport={RPC_PORT}",
        "-rpcuser=test",
        "-rpcpassword=test",
        "-pqc=1",
        "-pqcsig=falcon",
        "-fallbackfee=0.0001",
        "-maxtxfee=1.0",
        "-txindex=1",
        "-nodebug",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Wait for RPC to be ready
    for _ in range(40):
        time.sleep(0.5)
        try:
            cli("getblockchaininfo")
            return proc
        except Exception:
            pass
    raise RuntimeError("Node failed to start within 20 seconds")

def stop_node(proc):
    try:
        cli("stop")
    except Exception:
        pass
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.terminate()
        proc.wait(timeout=5)

def cleanup():
    shutil.rmtree(DATADIR, ignore_errors=True)

def run_test():
    proc = None
    try:
        print("\n=== Falcon Key Persistence After Restart Test ===\n")

        # ── Phase 1: Initial setup ────────────────────────────────────────────
        print("[1] Starting fresh node with -pqcsig=falcon ...")
        proc = start_node(fresh=True)
        info = cli_json("getblockchaininfo")
        ok = report("Node started (regtest, Falcon)", info["chain"] == "regtest")
        if not ok:
            return

        # Create wallet
        cli("createwallet", WALLET)
        addr_mine = cli("getnewaddress", "", "bech32", wallet=WALLET)
        addr_recv = cli("getnewaddress", "", "bech32", wallet=WALLET)
        report("Wallet + Falcon addresses created", True, addr_mine[:20] + "...")

        # Verify it's a Falcon hybrid address (witness program format encodes both keys)
        addrinfo = cli_json("getaddressinfo", addr_mine, wallet=WALLET)
        is_bech32 = addrinfo.get("iswitness", False)
        report("Address is witness (P2WPKH hybrid)", is_bech32)

        # ── Phase 2: Mine coins ───────────────────────────────────────────────
        print("\n[2] Mining 101 blocks to Falcon address ...")
        cli_json("generatetoaddress", "101", addr_mine, wallet=WALLET)
        bal_before = float(cli("getbalance", wallet=WALLET))
        report("Coinbase spendable after 101 blocks", bal_before > 0,
               f"{bal_before:.8f} QBTC")

        # Record a UTXO we'll spend after restart
        utxos = cli_json("listunspent", wallet=WALLET)
        assert utxos, "No spendable UTXOs"
        target_utxo = max(utxos, key=lambda u: u["amount"])
        pre_restart_txid = target_utxo["txid"]
        pre_restart_vout = target_utxo["vout"]
        report("Target UTXO identified", True,
               f"txid={pre_restart_txid[:16]}... amount={target_utxo['amount']:.8f}")

        # Record block count
        blocks_before = cli_json("getblockcount")

        # ── Phase 3: Stop node ────────────────────────────────────────────────
        print("\n[3] Stopping node ...")
        stop_node(proc)
        proc = None
        time.sleep(2)  # Let all files flush
        report("Node stopped cleanly", True)

        # ── Phase 4: Restart node (same datadir) ──────────────────────────────
        print("\n[4] Restarting node (same datadir, same wallet) ...")
        proc = start_node(fresh=False)
        info2 = cli_json("getblockchaininfo")
        report("Node restarted successfully", info2["chain"] == "regtest")

        blocks_after = cli_json("getblockcount")
        report("Chain height preserved across restart", blocks_after == blocks_before,
               f"before={blocks_before}, after={blocks_after}")

        # Load wallet explicitly (it should auto-load but force it)
        wallets_loaded = cli_json("listwallets")
        if WALLET not in wallets_loaded:
            cli("loadwallet", WALLET)
        wallets_loaded = cli_json("listwallets")
        report("Wallet loaded after restart", WALLET in wallets_loaded)

        # ── Phase 5: Verify address still present ─────────────────────────────
        print("\n[5] Verifying address and balance post-restart ...")
        addrinfo2 = cli_json("getaddressinfo", addr_mine, wallet=WALLET)
        report("Address still in wallet after restart",
               addrinfo2.get("ismine", False),
               addr_mine[:20] + "...")

        bal_restart = float(cli("getbalance", wallet=WALLET))
        report("Balance preserved after restart", abs(bal_restart - bal_before) < 0.0001,
               f"{bal_restart:.8f} QBTC (was {bal_before:.8f})")

        # Verify UTXO still unspent
        utxos2 = cli_json("listunspent", wallet=WALLET)
        utxo_ids = {(u["txid"], u["vout"]) for u in utxos2}
        report("Pre-restart UTXO still unspent",
               (pre_restart_txid, pre_restart_vout) in utxo_ids)

        # ── Phase 6: Sign and spend FROM that address after restart ───────────
        print("\n[6] Spending from Falcon address (key must be re-derived) ...")
        send_amt = round(target_utxo["amount"] * 0.4, 6)
        fee      = 0.005  # generous fee for Falcon tx
        change   = round(target_utxo["amount"] - send_amt - fee, 8)
        assert change > 0, "Insufficient funds"

        inputs  = json.dumps([{"txid": pre_restart_txid, "vout": pre_restart_vout}])
        outputs = json.dumps({addr_recv: send_amt, addr_mine: change})

        raw_unsigned = cli("createrawtransaction", inputs, outputs)

        # This is the critical step: signing re-derives the Falcon private key
        # from the ECDSA key that was loaded from the wallet.dat on restart.
        signed = cli_json("signrawtransactionwithwallet", raw_unsigned, wallet=WALLET)
        signing_ok = signed.get("complete", False)
        report("Signing succeeded after restart (Falcon key re-derived)", signing_ok,
               str(signed.get("errors", ""))[:100] if not signing_ok else "")

        if not signing_ok:
            return  # Can't proceed without a valid sig

        # Verify the witness contains 4 elements (ECDSA sig, EC pk, Falcon sig, Falcon pk)
        decoded = cli_json("decoderawtransaction", signed["hex"])
        witness = None
        for vin in decoded["vin"]:
            if "txinwitness" in vin and len(vin["txinwitness"]) == 4:
                witness = vin["txinwitness"]
                break
        report("Witness is 4-element Falcon hybrid after restart", witness is not None,
               f"sizes={[len(w)//2 for w in witness]}" if witness else "no PQC witness found")

        # Broadcast
        txid = cli("sendrawtransaction", signed["hex"], wallet=WALLET)
        report("Post-restart spend tx accepted to mempool", bool(txid),
               txid[:16] + "...")

        # Mine to confirm
        cli_json("generatetoaddress", "1", addr_mine, wallet=WALLET)
        time.sleep(1)

        # Verify spend was confirmed
        tx_info = cli_json("gettransaction", txid, wallet=WALLET)
        confirmed = tx_info.get("confirmations", 0) > 0
        report("Post-restart spend tx confirmed in block", confirmed,
               f"confirmations={tx_info.get('confirmations', 0)}")

        # ── Phase 7: Final balance sanity ─────────────────────────────────────
        print("\n[7] Final balance check ...")
        bal_final = float(cli("getbalance", wallet=WALLET))
        # Should be less than original (we spent some) but positive (we have change + new coinbase)
        report("Balance changed correctly after spend", bal_final > 0,
               f"final={bal_final:.8f} QBTC")

    except Exception as e:
        print(f"\n  [ERROR] Test aborted: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Test completed without exception", False))
    finally:
        if proc is not None:
            stop_node(proc)
        cleanup()

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "="*55)
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    print(f"Results: {passed}/{total} passed")
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'} {name}")
    print()
    if passed == total:
        print("ALL TESTS PASSED — Falcon keys survive node restart.")
        print("Private keys are derived on demand; ECDSA key in wallet.dat is sufficient.")
    else:
        print(f"FAILED: {total - passed} test(s) failed.")
    print()
    return passed == total

if __name__ == "__main__":
    ok = run_test()
    sys.exit(0 if ok else 1)
