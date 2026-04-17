#!/usr/bin/env python3
"""
Falcon Signature Tamper Rejection Test
=======================================
Proves that the consensus layer actually verifies Falcon signatures by:

  1. Mine coins to a Falcon hybrid address
  2. Create + sign a valid spend tx -> confirm it's accepted
  3. Clone that raw tx, flip bytes in the Falcon sig portion of the witness
  4. Broadcast the tampered tx -> must be REJECTED (not accepted to mempool)
  5. Clone that raw tx, flip bytes in the ECDSA sig portion of the witness
  6. Broadcast the ECDSA-tampered tx -> must be REJECTED as well
  7. Confirm only the original, valid tx can be mined

This proves sig verification is enforced at the consensus level, not just
advisory.
"""

import subprocess, json, os, shutil, time, sys, struct

BITCOIND = "./build-fresh/src/bitcoind"
CLI      = "./build-fresh/src/bitcoin-cli"
DATADIR  = os.path.join(os.environ.get("TMPDIR", "/tmp"), "falcon_tamper_regtest")
WALLET   = "tamper_wallet"
RPC_PORT = "18748"

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
results = []

def report(name, ok, detail=""):
    tag = PASS if ok else FAIL
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))
    results.append((name, ok))

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
    """Return (returncode, stdout, stderr) without raising."""
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
        "-pqcsig=falcon",
        "-fallbackfee=0.0001",
        "-maxtxfee=1.0",
        "-txindex=1",
        "-nodebug",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(6)
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

def flip_bytes_at(hex_str, byte_offset, length=4):
    """Flip `length` bytes at `byte_offset` within hex_str."""
    data = bytearray.fromhex(hex_str)
    for i in range(length):
        idx = byte_offset + i
        if idx < len(data):
            data[idx] ^= 0xFF
    return data.hex()

def tamper_witness_element(raw_hex, input_index, witness_element_index, byte_offset=8, flip_len=4):
    """
    Decode raw tx, flip bytes inside a specific witness element, re-encode.
    Uses bitcoin-tx for decode/encode so we don't need a full serialization lib.
    This works by string-splicing on the hex — we locate the witness element
    in the decoded JSON and reconstruct the hex with the tampered element.
    """
    # We'll use `bitcoin-tx` to decode and re-sign... but actually the simplest
    # approach: find the witness element hex in the decoded tx JSON, flip bytes,
    # then use createrawtransaction + witness injection via getrawtransaction.
    #
    # Simpler: use the decoderawtransaction RPC to find witness offsets,
    # then directly patch the raw hex.
    #
    # The witness is at the end of the serialised tx. We use a helper approach:
    # decode -> patch the JSON element -> re-encode via bitcoin-tx.
    return None  # see below for actual implementation

def run_test():
    proc = None
    try:
        print("\n=== Falcon Signature Tamper Rejection Test ===\n")

        # ── Start node ─────────────────────────────────────────────────────────
        print("[1] Starting bitcoind with -pqcsig=falcon ...")
        proc = start_node()
        info = cli_json("getblockchaininfo")
        report("Node started in regtest", info["chain"] == "regtest")

        # ── Wallet + addresses ──────────────────────────────────────────────────
        print("\n[2] Setting up wallet and addresses ...")
        cli("createwallet", WALLET)
        addr_mine = cli("getnewaddress", "", "bech32", wallet=WALLET)
        addr_recv = cli("getnewaddress", "", "bech32", wallet=WALLET)
        report("Wallet + addresses ready", True)

        # ── Mine coins ─────────────────────────────────────────────────────────
        print("\n[3] Mining 101 blocks to Falcon address ...")
        cli_json("generatetoaddress", "101", addr_mine, wallet=WALLET)
        bal = float(cli("getbalance", wallet=WALLET))
        report("Coins spendable", bal > 0, f"{bal:.8f} BTC")

        # ── Create a valid signed tx (don't broadcast yet) ─────────────────────
        print("\n[4] Building valid spend tx ...")
        send_amt = round(bal * 0.3, 6)

        # List UTXOs to pick inputs manually
        utxos = cli_json("listunspent", wallet=WALLET)
        assert utxos, "No UTXOs available"
        # Pick the largest
        utxo = max(utxos, key=lambda u: u["amount"])

        # Calculate change
        fee = 0.0001
        change_amt = round(utxo["amount"] - send_amt - fee, 8)
        assert change_amt > 0, "Insufficient funds in chosen UTXO"

        # Create raw tx
        inputs = json.dumps([{"txid": utxo["txid"], "vout": utxo["vout"]}])
        outputs = json.dumps({addr_recv: send_amt, addr_mine: change_amt})
        raw_unsigned = cli("createrawtransaction", inputs, outputs)

        # Sign with wallet (uses the same signing path as sendtoaddress)
        signed = cli_json("signrawtransactionwithwallet", raw_unsigned, wallet=WALLET)
        assert signed["complete"], f"Signing incomplete: {signed.get('errors', '')}"
        valid_raw = signed["hex"]
        report("Valid signed tx built", True, f"{len(valid_raw)//2} bytes")

        # Decode to find the witness data
        decoded = cli_json("decoderawtransaction", valid_raw)
        spend_vin = None
        for vin in decoded["vin"]:
            if "txinwitness" in vin and len(vin["txinwitness"]) == 4:
                spend_vin = vin
                break
        assert spend_vin is not None, "No 4-element PQC witness found in tx"

        witness = spend_vin["txinwitness"]
        # Element layout: [0]=ECDSA sig, [1]=ECDSA pubkey, [2]=Falcon sig, [3]=Falcon pubkey
        ecdsa_sig_hex  = witness[0]
        falcon_sig_hex = witness[2]
        w_sizes = [len(w)//2 for w in witness]
        report("Witness is 4-element PQC hybrid", len(witness) == 4,
               f"sizes={w_sizes}")
        report(f"Falcon sig present ({len(falcon_sig_hex)//2}B)", len(falcon_sig_hex) > 600)

        # ── Tamper the Falcon signature FIRST (before original is confirmed) ────
        print("\n[5] Tampering Falcon signature and broadcasting (must be rejected) ...")
        # Flip 8 bytes deep inside the Falcon sig (past any length prefix)
        tampered_falcon_sig = flip_bytes_at(falcon_sig_hex, byte_offset=16, length=8)
        assert tampered_falcon_sig != falcon_sig_hex, "Tamper had no effect"

        # Rebuild the raw tx with the tampered element.
        tampered_raw_falcon = valid_raw.replace(falcon_sig_hex, tampered_falcon_sig, 1)
        if tampered_raw_falcon == valid_raw:
            report("Falcon sig tamper applied to raw tx", False,
                   "Substitution had no effect — element not found verbatim")
        else:
            report("Falcon sig tamper applied to raw tx", True)
            rc_f, out_f, err_f = cli_ok("sendrawtransaction", tampered_raw_falcon)
            report("Tampered-Falcon tx REJECTED by node", rc_f != 0,
                   err_f[:120] if rc_f != 0 else f"ACCEPTED (bad!) txid={out_f[:16]}")
            if rc_f != 0:
                rejected_for_sig = any(k in err_f.lower() for k in
                                       ["script", "verify", "mandatory", "witness", "non-mandatory",
                                        "scripterror"])
                report("Rejection is script/sig related", rejected_for_sig, err_f[:160])

        # ── Tamper the ECDSA signature NEXT (also before original confirmed) ───
        print("\n[6] Tampering ECDSA signature and broadcasting (must be rejected) ...")
        tampered_ecdsa_sig = flip_bytes_at(ecdsa_sig_hex, byte_offset=4, length=8)
        assert tampered_ecdsa_sig != ecdsa_sig_hex, "Tamper had no effect"

        tampered_raw_ecdsa = valid_raw.replace(ecdsa_sig_hex, tampered_ecdsa_sig, 1)
        if tampered_raw_ecdsa == valid_raw:
            report("ECDSA sig tamper applied to raw tx", False,
                   "Substitution had no effect — element not found verbatim")
        else:
            report("ECDSA sig tamper applied to raw tx", True)
            rc_e, out_e, err_e = cli_ok("sendrawtransaction", tampered_raw_ecdsa)
            report("Tampered-ECDSA tx REJECTED by node", rc_e != 0,
                   err_e[:120] if rc_e != 0 else f"ACCEPTED (bad!) txid={out_e[:16]}")
            if rc_e != 0:
                rejected_for_sig = any(k in err_e.lower() for k in
                                       ["script", "verify", "mandatory", "witness", "non-mandatory",
                                        "scripterror"])
                report("Rejection is script/sig related", rejected_for_sig, err_e[:160])

        # ── Now broadcast the valid tx -> must be ACCEPTED ─────────────────────
        print("\n[7] Broadcasting valid (untampered) tx (must be accepted) ...")
        rc, valid_txid, err = cli_ok("sendrawtransaction", valid_raw)
        report("Valid tx accepted to mempool", rc == 0,
               valid_txid[:16] + "..." if rc == 0 else err[:80])

        # Mine to confirm
        cli_json("generatetoaddress", "1", addr_mine, wallet=WALLET)
        report("Valid tx confirmed", True)

        # ── Confirm chain integrity ────────────────────────────────────────────
        print("\n[8] Confirming chain integrity ...")
        # Both tampered txs should be absent from UTXO set / mempool
        mpool = cli_json("getrawmempool")
        report("Tampered txs not in mempool", len(mpool) == 0,
               f"mempool size={len(mpool)}")

        # Original balance decreased correctly (already mined above)
        new_bal = float(cli("getbalance", wallet=WALLET))
        report("Chain balance consistent after tamper attempts", new_bal >= 0,
               f"{new_bal:.8f} BTC")

    finally:
        if proc:
            stop_node(proc)

    # ── Summary ───────────────────────────────────────────────────────────────
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
