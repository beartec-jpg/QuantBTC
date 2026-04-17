# QuantumBTC PQC Security Tests

Security tests for the Post-Quantum Cryptography implementation in QuantumBTC.
These tests run against a **live local testnet node** and verify PQC enforcement
at the consensus and mempool layers.

## Prerequisites

```bash
# Start testnet
./contrib/qbtc-testnet/qbtc-testnet.sh start

# Build signing tool (needed for pubkey unbinding test)
g++ -O2 -I src/crypto/pqc/ml-dsa \
  contrib/testgen/pqc_sign_tool.cpp \
  src/crypto/pqc/ml-dsa/{sign,packing,poly,polyvec,ntt,reduce,rounding,symmetric-shake,fips202}.c \
  contrib/testgen/randombytes_openssl.c \
  -o pqc_sign_tool -lssl -lcrypto
```

## Running

```bash
# Run all security tests
bash test/security/run_all.sh

# Run individual tests
python3 test/security/test_pqc_security.py
python3 test/security/test_pqc_pubkey_unbinding.py
python3 test/security/test_sphincs_verify.py
```

## Test Inventory

| Test | Checks | Status |
|------|--------|--------|
| `test_pqc_security.py` | PQC witness downgrade bypass — ECDSA-only witnesses accepted on PQC chain | 25/25 pass |
| `test_pqc_pubkey_unbinding.py` | Dilithium pubkey not bound to UTXO — attacker can substitute their own keypair | 22/22 pass |
| `test_sphincs_verify.py` | SPHINCS+ and Dilithium Verify() are real implementations, not stubs | 16/16 pass |

## Vulnerabilities Found

### CVE-1: PQC Witness Downgrade Bypass (CRITICAL)
- **File**: `src/validation.cpp` — `GetBlockScriptFlags()`
- **Issue**: `SCRIPT_VERIFY_HYBRID_SIG` is never set, so 2-element ECDSA-only witnesses
  are accepted even when PQC is ALWAYS_ACTIVE.
- **Impact**: PQC provides zero protection; any ECDSA-only spend is accepted.

### CVE-2: PQC Pubkey Not Bound to UTXO (CRITICAL)
- **File**: `src/script/interpreter.cpp` — P2WPKH 4-element witness path
- **Issue**: The Dilithium/SPHINCS+ public key comes from the witness stack (attacker-controlled)
  and is NOT committed to the scriptPubKey. P2WPKH program = Hash160(ecdsa_pubkey) only.
- **Impact**: Attacker who compromises ECDSA key can generate their own PQC keypair and bypass
  the quantum-resistant layer entirely.

### RESOLVED: HTLC Claim Front-Running (Medium Severity)
- **File**: `ATOMIC-SWAP-REPORT.md` — QBTC HTLC P2WSH script (claim branch)
- **Issue**: The original claim branch used `OP_TRUE` as the sole spend condition — any party who observed the secret (SHA-256 preimage) in the mempool could construct a competing transaction claiming the QBTC to a different address, beating the legitimate buyer.
- **Fix**: Replaced `OP_TRUE` with `<buyerPubKey> OP_CHECKSIG`. The buyer's public key is embedded in the HTLC script at lock time. Spending now requires both the secret AND a valid ECDSA signature from the buyer's key. Witness format updated from `[secret, 0x01, htlcScript]` to `[buyer_sig, secret, htlcScript]`.

### RESOLVED: 3-Element Witness Pass-Through Could Mask Future PQC Validation Bugs (Low Severity)
- **File**: `src/consensus/pqc_validation.cpp` lines 64–84
- **Issue**: The `continue` that lets non-2/non-4 element witnesses bypass `CheckPQCSignatures`'s structural precheck is correct for P2WSH HTLC spends, but if a future PQC upgrade introduces a hybrid witness format whose stack depth is not 2 or 4, this pass-through would silently skip its verification.
- **Fix**: Expanded the comment block on the `continue` branch to enumerate every known legitimate use-case (HTLC claim/refund, multi-sig), and added an explicit `*** MAINTENANCE NOTE ***` warning requiring any future non-2/non-4 PQC witness format to add an explicit `if` branch *above* the catch-all `else` rather than relying on the pass-through.

### RESOLVED: SPHINCS+/Dilithium Verify() Stubs
- **Status**: **Not a vulnerability**. Both call real vendored NIST reference implementations.
- **TODO.md**: Entry is outdated and should be corrected.
