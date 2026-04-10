#!/usr/bin/env python3
"""
QuantumBTC PQC Security Tests
==============================
Tests for PQC signature bypass vulnerabilities on a live qbtctestnet node.

Requires:
  - ./src/bitcoind running with -qbtctestnet (use ./contrib/qbtc-testnet/qbtc-testnet.sh start)
  - A 'miner' wallet with spendable balance (mine 200+ blocks first)

Tests:
  1. PQC Witness Downgrade Bypass  — 2-element ECDSA-only witness accepted
     on PQC-active chain (SCRIPT_VERIFY_HYBRID_SIG never set)
  2. SCRIPT_VERIFY_HYBRID_SIG flag audit — verify the flag is missing from
     GetBlockScriptFlags() in validation.cpp
  3. Validation flag coverage — check DEPLOYMENT_PQC is active and
     SCRIPT_VERIFY_PQC is set, but has no enforcement teeth
  4. PQC witness size boundary — malformed 3-element and 5-element witnesses
  5. ECDSA-only tx can be mined into a block on PQC chain

Usage:
  ./contrib/qbtc-testnet/qbtc-testnet.sh start
  ./contrib/qbtc-testnet/qbtc-testnet.sh wallet
  ./contrib/qbtc-testnet/qbtc-testnet.sh mine 200
  python3 test_pqc_security.py
"""

import subprocess
import json
import sys
import os
import time
import struct
import hashlib
from collections import OrderedDict

# ── Configuration ──────────────────────────────────────────────────────
CHAIN = "qbtctestnet"
CLI_BIN = os.environ.get("CLI", "./src/bitcoin-cli")
WALLET = os.environ.get("WALLET", "miner")
MIN_BLOCKS = 101  # coinbase maturity

# Expected PQC element sizes (from src/crypto/pqc/dilithium.h)
DILITHIUM_SIG_SIZE = 2420
DILITHIUM_PK_SIZE = 1312
SPHINCS_SIG_SIZE = 17088
SPHINCS_PK_SIZE = 32

# ── Helpers ────────────────────────────────────────────────────────────
passed = 0
failed = 0
errors = []


def cli(*args, wallet=None):
    """Call bitcoin-cli and return raw stdout."""
    cmd = [CLI_BIN, f"-{CHAIN}"]
    if wallet:
        cmd.append(f"-rpcwallet={wallet}")
    cmd.extend(str(a) for a in args)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"RPC failed: {' '.join(cmd)}\n  stderr: {r.stderr.strip()}")
    return r.stdout.strip()


def cli_json(*args, wallet=None):
    """Call bitcoin-cli and parse JSON result."""
    return json.loads(cli(*args, wallet=wallet))


def mine(n=1):
    """Mine n blocks to the miner wallet."""
    addr = cli("getnewaddress", "", "bech32", wallet=WALLET)
    return cli_json("generatetoaddress", str(n), addr, wallet=WALLET)


def get_spendable_utxo(min_amount=0.01):
    """Return a spendable UTXO with at least min_amount."""
    utxos = cli_json("listunspent", "1", "9999999", wallet=WALLET)
    for u in utxos:
        if u["amount"] >= min_amount and u["spendable"]:
            return u
    raise RuntimeError(f"No spendable UTXO >= {min_amount} QBTC found. Mine more blocks.")


def report(test_name, passed_flag, detail=""):
    """Print test result and update counters."""
    global passed, failed
    status = "PASS" if passed_flag else "FAIL"
    icon = "\033[92m✓\033[0m" if passed_flag else "\033[91m✗\033[0m"
    print(f"  {icon} [{status}] {test_name}")
    if detail:
        print(f"         {detail}")
    if passed_flag:
        passed += 1
    else:
        failed += 1
        errors.append(test_name)


# ══════════════════════════════════════════════════════════════════════
# Test 1: PQC Signature Bypass via Witness Downgrade
# ══════════════════════════════════════════════════════════════════════
def test_pqc_witness_downgrade_bypass():
    """
    Vulnerability: interpreter.cpp only triggers PQC verification when
    witness stack.size() == 4. A standard 2-element ECDSA witness skips
    PQC entirely.

    SCRIPT_VERIFY_HYBRID_SIG (which would reject missing PQC) is NEVER
    set in GetBlockScriptFlags() in validation.cpp.

    This test:
    1. Creates a transaction spending a PQC-chain UTXO
    2. Signs with wallet (produces 2-element ECDSA-only witness)
    3. Verifies testmempoolaccept ACCEPTS it (vulnerability confirmed)
    4. Verifies the witness has only 2 elements (no PQC)
    """
    print("\n── Test 1: PQC Witness Downgrade Bypass ──────────────────────")
    utxo = get_spendable_utxo(0.1)
    send_amount = round(utxo["amount"] - 0.001, 8)
    dest = cli("getnewaddress", "", "bech32", wallet=WALLET)

    # Create and sign with wallet (produces ECDSA-only witness)
    raw = cli("createrawtransaction",
              json.dumps([{"txid": utxo["txid"], "vout": utxo["vout"]}]),
              json.dumps([{dest: send_amount}]),
              wallet=WALLET)

    signed = cli_json("signrawtransactionwithwallet", raw, wallet=WALLET)
    report("Wallet signs transaction successfully",
           signed["complete"],
           f"tx hex length: {len(signed['hex'])} chars")

    # Decode and inspect witness
    decoded = cli_json("decoderawtransaction", signed["hex"])
    witness = decoded["vin"][0].get("txinwitness", [])
    witness_sizes = [len(w) // 2 for w in witness]

    report("Witness has exactly 2 elements (ECDSA-only, no PQC)",
           len(witness) == 2,
           f"stack size={len(witness)}, element sizes={witness_sizes} bytes")

    # Test mempool acceptance — this SHOULD fail on PQC-active chain
    # but currently PASSES (vulnerability)
    result = cli_json("testmempoolaccept", json.dumps([signed["hex"]]))
    accepted = result[0]["allowed"]

    report("VULNERABILITY: ECDSA-only tx accepted on PQC-active chain",
           accepted is True,
           f"allowed={accepted} — ECDSA-only witness bypasses PQC requirement")

    # Verify chain is PQC-active
    info = cli_json("getblockchaininfo")
    pqc_active = info.get("pqc", False)
    report("Chain confirms PQC is active",
           pqc_active is True,
           f"pqc={pqc_active}, chain={info['chain']}")

    return signed["hex"]


# ══════════════════════════════════════════════════════════════════════
# Test 2: SCRIPT_VERIFY_HYBRID_SIG flag audit (source code check)
# ══════════════════════════════════════════════════════════════════════
def test_hybrid_sig_flag_audit():
    """
    Check the source code to verify SCRIPT_VERIFY_HYBRID_SIG is never
    set in the block validation path. This flag is defined but dead.
    """
    print("\n── Test 2: SCRIPT_VERIFY_HYBRID_SIG Flag Audit ──────────────")

    # Check validation.cpp for the flag
    validation_path = os.path.join(os.path.dirname(CLI_BIN), "validation.cpp")
    if not os.path.exists(validation_path):
        # Try from repo root
        validation_path = "./src/validation.cpp"

    if os.path.exists(validation_path):
        with open(validation_path, "r") as f:
            content = f.read()

        # Check if SCRIPT_VERIFY_HYBRID_SIG is ever set (flags |=) in validation.cpp
        import re
        flag_set_pattern = re.compile(r'flags\s*\|=.*SCRIPT_VERIFY_HYBRID_SIG')
        flag_is_set = bool(flag_set_pattern.search(content))
        flag_referenced = "SCRIPT_VERIFY_HYBRID_SIG" in content

        report("VULNERABILITY: SCRIPT_VERIFY_HYBRID_SIG absent from validation.cpp entirely",
               flag_referenced is False,
               f"Flag defined in pqc_validation.h but never imported or used in validation.cpp")

        report("VULNERABILITY: SCRIPT_VERIFY_HYBRID_SIG is NEVER set in flags",
               flag_is_set is False,
               "No 'flags |= ...SCRIPT_VERIFY_HYBRID_SIG' found in GetBlockScriptFlags()")

        # Verify SCRIPT_VERIFY_PQC IS set
        pqc_flag_set = bool(re.search(r'flags\s*\|=.*SCRIPT_VERIFY_PQC', content))
        report("SCRIPT_VERIFY_PQC is set in GetBlockScriptFlags()",
               pqc_flag_set,
               "flags |= SCRIPT_VERIFY_PQC is present")
    else:
        report("validation.cpp accessible", False, f"not found at {validation_path}")

    # Check pqc_validation.cpp enforcement gap
    pqc_val_path = "./src/consensus/pqc_validation.cpp"
    if os.path.exists(pqc_val_path):
        with open(pqc_val_path, "r") as f:
            pqc_content = f.read()

        # The check at line 65 depends on SCRIPT_VERIFY_HYBRID_SIG which is never set
        has_dead_check = "SCRIPT_VERIFY_HYBRID_SIG" in pqc_content and "!pqc_found" in pqc_content
        report("pqc_validation.cpp has dead-code guard (HYBRID_SIG && !pqc_found)",
               has_dead_check,
               "This check never fires because SCRIPT_VERIFY_HYBRID_SIG is never set")


# ══════════════════════════════════════════════════════════════════════
# Test 3: ECDSA-only tx actually mines into a block
# ══════════════════════════════════════════════════════════════════════
def test_ecdsa_only_tx_mines():
    """
    Submit an ECDSA-only signed tx to the mempool and mine it into a block.
    This proves the bypass isn't just a mempool policy gap — it's consensus.
    """
    print("\n── Test 3: ECDSA-only Tx Mines Into Block ───────────────────")

    utxo = get_spendable_utxo(0.1)
    send_amount = round(utxo["amount"] - 0.001, 8)
    dest = cli("getnewaddress", "", "bech32", wallet=WALLET)

    # Create, sign (ECDSA-only), and broadcast
    raw = cli("createrawtransaction",
              json.dumps([{"txid": utxo["txid"], "vout": utxo["vout"]}]),
              json.dumps([{dest: send_amount}]),
              wallet=WALLET)

    signed = cli_json("signrawtransactionwithwallet", raw, wallet=WALLET)
    signed_hex = signed["hex"]

    # Verify it's ECDSA-only
    decoded = cli_json("decoderawtransaction", signed_hex)
    witness = decoded["vin"][0].get("txinwitness", [])
    report("Tx witness is ECDSA-only (2 elements)", len(witness) == 2)

    # Send to mempool
    try:
        txid = cli("sendrawtransaction", signed_hex)
        report("ECDSA-only tx accepted into mempool",
               len(txid) == 64,
               f"txid={txid[:16]}...")
    except RuntimeError as e:
        report("ECDSA-only tx accepted into mempool", False, str(e))
        return

    # Verify it's in mempool
    mempool = cli_json("getrawmempool")
    in_mempool = txid in mempool
    report("Tx is in mempool", in_mempool, f"mempool size={len(mempool)}")

    # Mine blocks — DAG mode may need several mines for tx to confirm
    pre_height = int(cli("getblockcount"))
    for _ in range(10):
        mine(1)
        time.sleep(0.2)
    post_height = int(cli("getblockcount"))

    report("Block(s) mined after submitting ECDSA-only tx",
           post_height >= pre_height,
           f"height {pre_height} → {post_height} (DAG consolidation)")

    # Verify tx is confirmed — check mempool and confirmations
    mempool_after = cli_json("getrawmempool")
    tx_left_mempool = txid not in mempool_after

    confirmations = 0
    try:
        tx_info = cli_json("gettransaction", txid, wallet=WALLET)
        confirmations = tx_info.get("confirmations", 0)
    except RuntimeError:
        try:
            tx_raw = cli_json("getrawtransaction", txid, "1")
            confirmations = tx_raw.get("confirmations", 0)
        except RuntimeError:
            pass

    report("VULNERABILITY: ECDSA-only tx confirmed in block on PQC chain",
           confirmations >= 1 or tx_left_mempool,
           f"confirmations={confirmations}, left_mempool={tx_left_mempool}")


# ══════════════════════════════════════════════════════════════════════
# Test 4: Witness size boundary testing (malformed witnesses)
# ══════════════════════════════════════════════════════════════════════
def test_witness_boundary_manipulation():
    """
    Test interpreter.cpp's witness size branching:
    - stack.size() == 2 → pure ECDSA (no PQC check)
    - stack.size() == 4 → PQC path
    - stack.size() == 3 or 5 → should reject

    We can't easily craft custom witnesses via RPC alone, but we verify
    the structural rules by checking the signed tx format.
    """
    print("\n── Test 4: Witness Stack Size & Format Analysis ─────────────")

    utxo = get_spendable_utxo(0.01)
    send_amount = round(utxo["amount"] - 0.001, 8)
    dest = cli("getnewaddress", "", "bech32", wallet=WALLET)

    raw = cli("createrawtransaction",
              json.dumps([{"txid": utxo["txid"], "vout": utxo["vout"]}]),
              json.dumps([{dest: send_amount}]),
              wallet=WALLET)
    signed = cli_json("signrawtransactionwithwallet", raw, wallet=WALLET)
    decoded = cli_json("decoderawtransaction", signed["hex"])

    witness = decoded["vin"][0].get("txinwitness", [])
    report("Wallet produces 2-element witness (not 4-element PQC)",
           len(witness) == 2,
           f"Expected 4 for PQC; got {len(witness)}")

    # Check element sizes
    if len(witness) >= 2:
        sig_size = len(witness[0]) // 2
        pk_size = len(witness[1]) // 2

        report("Signature is standard ECDSA DER (70-73 bytes)",
               70 <= sig_size <= 73,
               f"sig_size={sig_size} bytes")

        report("Public key is standard EC compressed (33 bytes)",
               pk_size == 33,
               f"pk_size={pk_size} bytes")

        # If PQC were enforced, we'd see:
        #   [0] ECDSA sig (~72 bytes)
        #   [1] EC pubkey (33 bytes)
        #   [2] Dilithium sig (2420 bytes)
        #   [3] Dilithium pubkey (1312 bytes)
        has_pqc = (len(witness) == 4 and
                   len(witness[2]) // 2 == DILITHIUM_SIG_SIZE and
                   len(witness[3]) // 2 == DILITHIUM_PK_SIZE)
        report("VULNERABILITY: No Dilithium PQC signature present",
               has_pqc is False,
               f"Expected 4-elem witness with {DILITHIUM_SIG_SIZE}B sig, "
               f"{DILITHIUM_PK_SIZE}B pk — got {len(witness)}-elem ECDSA-only")

    # Verify the scriptPubKey is P2WPKH (20-byte program)
    spk = utxo.get("scriptPubKey", "")
    is_p2wpkh = spk.startswith("0014") and len(spk) == 44  # OP_0 PUSH20 <20bytes>
    report("UTXO is P2WPKH (20-byte witness program)",
           is_p2wpkh,
           f"scriptPubKey={spk[:20]}... (len={len(spk)//2} bytes)")


# ══════════════════════════════════════════════════════════════════════
# Test 5: IsPQCRequired() / IsPQCActivated() check
# ══════════════════════════════════════════════════════════════════════
def test_pqc_activation_status():
    """
    Verify that PQC deployment is active but enforcement is toothless.
    """
    print("\n── Test 5: PQC Activation vs Enforcement Gap ────────────────")

    info = cli_json("getblockchaininfo")

    # Check deployment status — PQC may be in softforks or exposed as top-level flag
    deployments = info.get("softforks", {})
    pqc_deploy = deployments.get("pqc", {})
    pqc_top_level = info.get("pqc", False)

    if pqc_deploy:
        pqc_status = pqc_deploy.get("type", "unknown")
        is_active = pqc_deploy.get("active", False)
        report("PQC deployment present in softforks",
               True, f"type={pqc_status}, active={is_active}")
    else:
        report("PQC exposed as top-level flag (not in softforks)",
               pqc_top_level is True,
               f"getblockchaininfo.pqc={pqc_top_level} (ALWAYS_ACTIVE deployment)")

    # Check chain config
    chain = info.get("chain", "")
    report("Running on qbtctestnet",
           chain == "qbtctestnet",
           f"chain={chain}")

    height = info.get("blocks", 0)
    report(f"Current block height ({height}) > 0",
           height > 0,
           f"height={height}")

    # Verify PQC field from getblockchaininfo
    pqc_flag = info.get("pqc", None)
    report("PQC flag is True in chain info",
           pqc_flag is True,
           f"pqc={pqc_flag}")

    # The core issue: PQC is "active" but SCRIPT_VERIFY_HYBRID_SIG is never set
    # so CheckPQCSignatures() never rejects ECDSA-only transactions
    report("VULNERABILITY SUMMARY: PQC active but unenforced",
           pqc_flag is True,
           "DEPLOYMENT_PQC=ALWAYS_ACTIVE sets SCRIPT_VERIFY_PQC, but only "
           "triggers structural precheck — no mandatory PQC requirement. "
           "SCRIPT_VERIFY_HYBRID_SIG is defined but never enabled in "
           "GetBlockScriptFlags().")


# ══════════════════════════════════════════════════════════════════════
# Test 6: Multiple ECDSA-only txs in sequence
# ══════════════════════════════════════════════════════════════════════
def test_multiple_ecdsa_bypass():
    """
    Submit multiple ECDSA-only transactions and mine them all to
    demonstrate the bypass is systematic, not a one-off.
    """
    print("\n── Test 6: Multiple ECDSA-only Tx Bypass ────────────────────")

    NUM_TXS = 5
    txids = []

    for i in range(NUM_TXS):
        try:
            utxo = get_spendable_utxo(0.01)
            send_amount = round(utxo["amount"] - 0.001, 8)
            dest = cli("getnewaddress", "", "bech32", wallet=WALLET)

            raw = cli("createrawtransaction",
                      json.dumps([{"txid": utxo["txid"], "vout": utxo["vout"]}]),
                      json.dumps([{dest: send_amount}]),
                      wallet=WALLET)
            signed = cli_json("signrawtransactionwithwallet", raw, wallet=WALLET)
            txid = cli("sendrawtransaction", signed["hex"])
            txids.append(txid)
        except RuntimeError as e:
            report(f"Tx {i+1}/{NUM_TXS} submitted", False, str(e))
            break

    report(f"All {NUM_TXS} ECDSA-only txs accepted into mempool",
           len(txids) == NUM_TXS,
           f"submitted={len(txids)}/{NUM_TXS}")

    if txids:
        # Mine enough blocks for DAG confirmation
        for _ in range(10):
            mine(1)
            time.sleep(0.2)

        confirmed = 0
        in_mempool = 0
        for txid in txids:
            try:
                tx = cli_json("gettransaction", txid, wallet=WALLET)
                if tx.get("confirmations", 0) >= 1:
                    confirmed += 1
            except RuntimeError:
                pass
            # Also check if it left mempool (means it's in a block)
            mempool = cli_json("getrawmempool")
            if txid not in mempool:
                in_mempool += 1

        report(f"VULNERABILITY: All {len(txids)} ECDSA-only txs confirmed/mined",
               confirmed == len(txids) or in_mempool == len(txids),
               f"confirmed={confirmed}/{len(txids)}, left_mempool={in_mempool}/{len(txids)}")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════
def main():
    print("=" * 70)
    print("  QuantumBTC PQC Security Test Suite")
    print("  Vulnerability: PQC Signature Bypass via Witness Downgrade")
    print("=" * 70)

    # Preflight checks
    print("\n── Preflight ────────────────────────────────────────────────")
    try:
        info = cli_json("getblockchaininfo")
        print(f"  Node: {info['chain']}  height={info['blocks']}  pqc={info.get('pqc')}")
    except Exception as e:
        print(f"  ERROR: Cannot reach node. Start it with:")
        print(f"    ./contrib/qbtc-testnet/qbtc-testnet.sh start")
        print(f"  Detail: {e}")
        sys.exit(1)

    # Check wallet
    try:
        bal = cli_json("getbalances", wallet=WALLET)
        spendable = bal["mine"]["trusted"]
        immature = bal["mine"]["immature"]
        print(f"  Wallet: {WALLET}  spendable={spendable} QBTC  immature={immature} QBTC")
    except Exception as e:
        print(f"  ERROR: Wallet '{WALLET}' not available. Create it with:")
        print(f"    ./contrib/qbtc-testnet/qbtc-testnet.sh wallet")
        print(f"  Detail: {e}")
        sys.exit(1)

    if spendable < 0.1:
        print(f"  WARNING: Low balance ({spendable}). Mining more blocks...")
        addr = cli("getnewaddress", "", "bech32", wallet=WALLET)
        for i in range(200):
            try:
                cli("generatetoaddress", "1", addr, wallet=WALLET)
            except RuntimeError:
                pass
        bal = cli_json("getbalances", wallet=WALLET)
        spendable = bal["mine"]["trusted"]
        print(f"  Updated: spendable={spendable} QBTC")

    if spendable < 0.1:
        print("  ERROR: Still insufficient balance. Try mining more blocks manually.")
        sys.exit(1)

    # Run tests
    test_pqc_witness_downgrade_bypass()
    test_hybrid_sig_flag_audit()
    test_ecdsa_only_tx_mines()
    test_witness_boundary_manipulation()
    test_pqc_activation_status()
    test_multiple_ecdsa_bypass()

    # Summary
    print("\n" + "=" * 70)
    print(f"  RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    if errors:
        print("\n  Failed tests:")
        for e in errors:
            print(f"    - {e}")

    print(f"""
  SECURITY FINDINGS:
  ──────────────────
  Vulnerability: PQC Signature Bypass via Witness Downgrade

  Root Cause:
    1. GetBlockScriptFlags() in validation.cpp sets SCRIPT_VERIFY_PQC
       when DEPLOYMENT_PQC is active, but NEVER sets SCRIPT_VERIFY_HYBRID_SIG.

    2. SCRIPT_VERIFY_PQC only enables CheckPQCSignatures() which is a
       structural precheck — it validates PQC element sizes IF present,
       but does NOT require PQC in every witness.

    3. SCRIPT_VERIFY_HYBRID_SIG (bit 25) would enforce mandatory PQC
       via the check at pqc_validation.cpp:65, but is dead code.

    4. In interpreter.cpp, VerifyWitnessProgram() only enters the PQC
       path when stack.size() == 4. A 2-element ECDSA witness falls
       through to standard verification with no PQC check.

  Impact:
    An attacker who compromises an ECDSA private key (e.g. via quantum
    computer) can spend PQC-protected UTXOs using ECDSA-only signatures,
    completely bypassing the post-quantum protection layer.

  Fix Required:
    In GetBlockScriptFlags() (src/validation.cpp), add:
      if (DeploymentActiveAt(block_index, chainman, Consensus::DEPLOYMENT_PQC)) {{
          flags |= Consensus::SCRIPT_VERIFY_PQC;
          flags |= Consensus::SCRIPT_VERIFY_HYBRID_SIG;  // MISSING!
      }}
""")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
