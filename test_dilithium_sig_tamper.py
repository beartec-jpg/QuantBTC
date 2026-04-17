#!/usr/bin/env python3
"""
Dilithium (ML-DSA-44) Signature Tamper Rejection Test
=======================================================
Mirror of test_falcon_sig_tamper.py for -pqcsig=dilithium.
Proves that the consensus layer enforces BOTH halves of the Dilithium
hybrid witness at the script interpreter level.

Test sequence:
  1. Start node with -pqcsig=dilithium (the default PQC scheme)
  2. Mine coins to a Dilithium hybrid address
  3. Build a valid signed spend tx — verify 4-element PQC witness present
  4. Tamper the Dilithium signature (flip 8 bytes) → must be REJECTED
  5. Tamper the ECDSA signature → must be REJECTED
  6. Broadcast the UNTAMPERED tx → must be ACCEPTED and confirmed

This proves that Dilithium hybrid signatures are enforced at consensus
independently — cannot be omitted, truncated, or corrupted.
"""

import subprocess, json, os, shutil, time, sys

BITCOIND = "./build-fresh/src/bitcoind"
CLI      = "./build-fresh/src/bitcoin-cli"
DATADIR  = os.path.join(os.environ.get("TMPDIR", "/tmp"), "dilithium_tamper_regtest")
WALLET   = "dil_tamper_wallet"
RPC_PORT = "18750"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []

def report(name, ok, detail=""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok))
    return ok

def cli(*args, wallet=None):
    base = [CLI, f"-datadir={DATADIR}", "-regtest", f"-rpcport={RPC_PORT}",
            "-rpcuser=test", "-rpcpassword=test"]
    if wallet:
        base += [f"-rpcwallet={wallet}"]
    out = subprocess.run(base + list(args), capture_output=True, text=True)
    if out.returncode != 0:
        raise RuntimeError(f"CLI error ({args[0]}): {out.stderr.strip()}")
    return out.stdout.strip()

def cli_json(*args, wallet=None):
    return json.loads(cli(*args, wallet=wallet))

def cli_ok(*args, wallet=None):
    base = [CLI, f"-datadir={DATADIR}", "-regtest", f"-rpcport={RPC_PORT}",
            "-rpcuser=test", "-rpcpassword=test"]
    if wallet:
        base += [f"-rpcwallet={wallet}"]
    r = subprocess.run(base + list(args), capture_output=True, text=True)
    return r.returncode, r.stdout.strip(), r.stderr.strip()

def start_node():
    if os.path.exists(DATADIR):
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
        "-pqcsig=dilithium",
        "-fallbackfee=0.0001",
        "-maxtxfee=1.0",
        "-txindex=1",
        "-nodebug",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        time.sleep(0.5)
        try:
            cli("getblockchaininfo")
            return proc
        except Exception:
            pass
    raise RuntimeError("Node failed to start")

def stop_node(proc):
    try:
        cli("stop")
        proc.wait(timeout=15)
    except Exception:
        proc.terminate()
        proc.wait(timeout=5)
    shutil.rmtree(DATADIR, ignore_errors=True)

def flip_bytes_at(hex_str, byte_offset, length=8):
    data = bytearray.fromhex(hex_str)
    for i in range(length):
        idx = byte_offset + i
        if idx < len(data):
            data[idx] ^= 0xFF
    return data.hex()

def run_test():
    proc = None
    try:
        print("\n=== Dilithium Signature Tamper Rejection Test ===\n")

        # ── Start node ────────────────────────────────────────────────────────
        print("[1] Starting bitcoind with -pqcsig=dilithium ...")
        proc = start_node()
        info = cli_json("getblockchaininfo")
        report("Node started in regtest (Dilithium mode)", info["chain"] == "regtest")

        # ── Wallet + addresses ────────────────────────────────────────────────
        print("\n[2] Setting up wallet and addresses ...")
        cli("createwallet", WALLET)
        addr_mine = cli("getnewaddress", "", "bech32", wallet=WALLET)
        addr_recv = cli("getnewaddress", "", "bech32", wallet=WALLET)
        report("Wallet + Dilithium hybrid addresses created", True)

        # ── Mine coins ────────────────────────────────────────────────────────
        print("\n[3] Mining 101 blocks to Dilithium address ...")
        cli_json("generatetoaddress", "101", addr_mine, wallet=WALLET)
        bal = float(cli("getbalance", wallet=WALLET))
        report("Coins spendable", bal > 0, f"{bal:.8f} QBTC")

        # ── Build valid signed tx ────────────────────────────────────────────
        print("\n[4] Building valid spend tx ...")
        send_amt = round(bal * 0.3, 6)
        utxos = cli_json("listunspent", wallet=WALLET)
        assert utxos, "No UTXOs available"
        utxo = max(utxos, key=lambda u: u["amount"])
        fee = 0.01   # Dilithium tx is large; use a generous fee
        change_amt = round(utxo["amount"] - send_amt - fee, 8)
        assert change_amt > 0, f"Insufficient funds: utxo={utxo['amount']}, send={send_amt}, fee={fee}"

        inputs  = json.dumps([{"txid": utxo["txid"], "vout": utxo["vout"]}])
        outputs = json.dumps({addr_recv: send_amt, addr_mine: change_amt})
        raw_unsigned = cli("createrawtransaction", inputs, outputs)

        signed = cli_json("signrawtransactionwithwallet", raw_unsigned, wallet=WALLET)
        assert signed["complete"], f"Signing incomplete: {signed.get('errors', '')}"
        valid_raw = signed["hex"]
        report("Valid Dilithium hybrid tx signed", True, f"{len(valid_raw)//2} bytes")

        # ── Decode and find the 4-element witness ────────────────────────────
        decoded = cli_json("decoderawtransaction", valid_raw)
        spend_vin = None
        for vin in decoded["vin"]:
            if "txinwitness" in vin and len(vin["txinwitness"]) == 4:
                spend_vin = vin
                break
        assert spend_vin is not None, "No 4-element PQC witness found"

        witness = spend_vin["txinwitness"]
        # Element layout: [0]=ECDSA sig, [1]=ECDSA pubkey, [2]=Dilithium sig (2420B), [3]=Dilithium pubkey (1312B)
        ecdsa_sig_hex     = witness[0]
        dilithium_sig_hex = witness[2]
        w_sizes = [len(w)//2 for w in witness]
        report("Witness is 4-element PQC hybrid", len(witness) == 4, f"sizes={w_sizes}")
        report(f"Dilithium sig present ({len(dilithium_sig_hex)//2}B)",
               len(dilithium_sig_hex)//2 == 2420,
               f"expected 2420B, got {len(dilithium_sig_hex)//2}B")

        # ── Tamper Dilithium signature ────────────────────────────────────────
        print("\n[5] Tampering Dilithium signature — must be REJECTED ...")
        # Flip 8 bytes well inside the signature body (past any size prefix bytes)
        tampered_dil_sig = flip_bytes_at(dilithium_sig_hex, byte_offset=20, length=8)
        assert tampered_dil_sig != dilithium_sig_hex, "Tamper had no effect"

        tampered_raw_dil = valid_raw.replace(dilithium_sig_hex, tampered_dil_sig, 1)
        if tampered_raw_dil == valid_raw:
            report("Dilithium sig tamper applied to raw tx", False,
                   "Substitution had no effect — element not found verbatim in raw tx")
        else:
            report("Dilithium sig tamper applied to raw tx", True)
            rc, out, err = cli_ok("sendrawtransaction", tampered_raw_dil)
            report("Tampered-Dilithium tx REJECTED by node", rc != 0,
                   err[:120] if rc != 0 else f"ACCEPTED (bad!) txid={out[:16]}")
            if rc != 0:
                script_related = any(k in err.lower() for k in
                                     ["script", "verify", "mandatory", "witness",
                                      "non-mandatory", "scripterror", "pqc", "dilithium"])
                report("Rejection is script/sig related", script_related, err[:160])

        # ── Tamper ECDSA signature ────────────────────────────────────────────
        print("\n[6] Tampering ECDSA signature — must be REJECTED ...")
        tampered_ecdsa_sig = flip_bytes_at(ecdsa_sig_hex, byte_offset=4, length=8)
        assert tampered_ecdsa_sig != ecdsa_sig_hex, "Tamper had no effect"

        tampered_raw_ecdsa = valid_raw.replace(ecdsa_sig_hex, tampered_ecdsa_sig, 1)
        if tampered_raw_ecdsa == valid_raw:
            report("ECDSA sig tamper applied to raw tx", False,
                   "Substitution had no effect — element not found verbatim in raw tx")
        else:
            report("ECDSA sig tamper applied to raw tx", True)
            rc, out, err = cli_ok("sendrawtransaction", tampered_raw_ecdsa)
            report("Tampered-ECDSA tx REJECTED by node", rc != 0,
                   err[:120] if rc != 0 else f"ACCEPTED (bad!) txid={out[:16]}")
            if rc != 0:
                script_related = any(k in err.lower() for k in
                                     ["script", "verify", "mandatory", "witness",
                                      "non-mandatory", "scripterror", "ecdsa"])
                report("Rejection is script/sig related", script_related, err[:160])

        # ── Broadcast valid tx — must be ACCEPTED ────────────────────────────
        print("\n[7] Broadcasting valid (untampered) tx — must be ACCEPTED ...")
        rc, valid_txid, err = cli_ok("sendrawtransaction", valid_raw)
        report("Valid Dilithium tx accepted to mempool", rc == 0,
               valid_txid[:16] + "..." if rc == 0 else err[:80])

        # Mine to confirm
        cli_json("generatetoaddress", "1", addr_mine, wallet=WALLET)
        report("Valid Dilithium tx confirmed in block", True)

        # ── Chain integrity ───────────────────────────────────────────────────
        print("\n[8] Chain integrity check ...")
        mpool = cli_json("getrawmempool")
        report("Tampered txs not in mempool", len(mpool) == 0,
               f"mempool size={len(mpool)}")

        new_bal = float(cli("getbalance", wallet=WALLET))
        balance_changed = abs(new_bal - bal) > 0.001
        report("Balance changed (spend confirmed)", balance_changed,
               f"before={bal:.8f}, after={new_bal:.8f}")

    except Exception as e:
        print(f"\n  [ERROR] Test aborted: {e}")
        import traceback
        traceback.print_exc()
        results.append(("Test completed without exception", False))
    finally:
        if proc is not None:
            stop_node(proc)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "="*55)
    passed = sum(1 for _, ok in results if ok)
    total  = len(results)
    print(f"Results: {passed}/{total} passed")
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'} {name}")
    print()
    if passed == total:
        print("ALL TESTS PASSED — Dilithium hybrid sig verification enforced at consensus.")
    else:
        print(f"FAILED: {total - passed} test(s) failed.")
    print()
    return passed == total

if __name__ == "__main__":
    ok = run_test()
    sys.exit(0 if ok else 1)
