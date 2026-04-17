# Security Policy

## Supported Versions

QuantumBTC (QBTC) is currently in testnet. The `main` branch at [beartec-jpg/QuantBTC](https://github.com/beartec-jpg/QuantBTC) is the only supported version.

## Reporting a Vulnerability

To report security issues, please open a **private** security advisory on GitHub:

1. Go to [github.com/beartec-jpg/QuantBTC/security/advisories](https://github.com/beartec-jpg/QuantBTC/security/advisories)
2. Click **New draft security advisory**
3. Describe the vulnerability with steps to reproduce

Do **not** open public issues for security vulnerabilities.

## Scope

QBTC-specific areas of particular interest:

- **PQC consensus** — ML-DSA-44 (Dilithium2) and SLH-DSA-SHA2-128f (SPHINCS+) signature verification in the script interpreter
- **GHOSTDAG consensus** — blue/red classification, mergeset computation, selected parent chain
- **Hybrid witness format** — 4-element P2WPKH witness (ECDSA + Dilithium)
- **DAG tip-set management** — tip tracking, score pruning, parent selection
- **Early protection system** — activation delay, ramp weight, IP throttling
- **Signature cache** — ECDSA, Schnorr, and Dilithium cache entry computation
- **Atomic swap protocol** — HTLC scripts, EVM HTLC contract, swap server coordination

For vulnerabilities in upstream Bitcoin Core code, please report to the Bitcoin Core security team at security@bitcoincore.org.

## Known Design Limitations

### Atomic Swap — Centralized Secret Generation (Medium)

**Affected component:** Swap server (`/api/swap/*`), not the QBTC node.

The current swap server generates the 32-byte HTLC preimage (secret) and stores it in the database.  This introduces a coordinator trust assumption with three risk vectors:

1. **Server compromise** — a compromised server knows the preimage before the buyer locks USDC and can call `withdraw()` on the EVM HTLC to steal the USDC while the QBTC refund timelock is still live.
2. **Database breach** — all pending swap preimages are exposed simultaneously.
3. **Server downtime at reveal time** — the swap stalls until timelocks expire.

**Recommended fix:** Adopt the standard Lightning/submarine-swap pattern: the *seller* generates the 32-byte secret locally and posts only `secretHash = SHA-256(secret)` to the server.  The server stores only the hash; the secret is never held server-side.  See `ATOMIC-SWAP-REPORT.md §3.2` for full details.  No changes to the QBTC node or on-chain scripts are required.

### EVM HTLC Contract — Testnet Only; External Audit Required Before Mainnet (Low)

**Affected component:** Solidity HTLC contract (to be redeployed on Ethereum Sepolia before testnet reset).

An internal audit (2026-04-17) identified and fixed the following issues in the
contract source.  The fixed contract is at `contrib/evm-htlc/contracts/QBTCUSDCHTLC.sol`.
The previous deployment (`0xaF898a5F565c0cAE1746122ad475c0B7F160A3eb`) is superseded;
redeploy with `npm run deploy:sepolia` from `contrib/evm-htlc/` before the next testnet cycle.

**Fixes applied (internal audit 2026-04-17):**

| ID  | Severity | Finding                                       | Fix                                         |
|-----|----------|-----------------------------------------------|---------------------------------------------|
| H-1 | HIGH     | CEI violation — reentrancy in withdraw/refund | CEI order enforced + `ReentrancyGuard`      |
| H-2 | HIGH     | Must use `sha256()` not `keccak256()`         | Explicit `sha256()` with cross-chain comment|
| M-1 | MEDIUM   | approve/transferFrom race window              | `initiateWithPermit()` (EIP-2612)           |
| M-2 | MEDIUM   | No minimum timelock — immediate expiry attack | `MIN_LOCKTIME = 1 hours` enforced           |
| M-3 | MEDIUM   | contractId collision on identical params      | Per-sender nonce in contractId hash         |
| L-1 | LOW      | No zero-address / zero-amount checks          | Guards in `_initiate()`                     |
| L-2 | LOW      | Unchecked ERC-20 return values                | `SafeERC20` throughout                      |
| L-3 | LOW      | Arbitrary ERC-20 token accepted               | Immutable `TOKEN` (single-token deploy)     |

Before any **mainnet** deployment the fixed contract **must** be independently
audited by a qualified Solidity security firm.  See the mainnet checklist in
`contrib/evm-htlc/README.md`.

## Falcon / FN-DSA Implementation Security Assessment

The following table documents known security considerations for the Falcon-padded-512
(FN-DSA) implementation used as the mandatory PQC scheme from genesis.

| # | Concern | Status | Detail |
|---|---------|--------|--------|
| 1 | **Constant-time implementation** | ✅ Covered | PQClean mandates CT as an acceptance requirement. The `CLEAN` variant enforces no data-dependent branches or memory patterns on secret material. Both sign and verify call `hash_to_point_ct()` exclusively; the `vartime` variant in `common.c` is never reachable from any public API path. |
| 2 | **Side-channel (power/EM — hardware)** | ℹ️ Out of scope | Power-analysis and electromagnetic attacks require physical access to the signing device. A software full-node is not subject to these attacks. Users deploying Falcon in HSMs or smartcards must evaluate hardware-layer masking independently. |
| 3 | **Key and signature sizes** | ✅ Fixed-size | Falcon-padded-512 produces constant-size signatures (666 B) regardless of the message, preventing oracle attacks based on signature-length leakage. Public key is 897 B. Sizes are consensus-enforced constants. |
| 4 | **Key reuse and address migration** | ✅ N/A | QuantumBTC enforces Falcon hybrid witness from block 1. There are no legacy ECDSA-only UTXOs to migrate. Each address encodes a unique Falcon public key hash; key reuse is prevented by the standard wallet keypool. |
| 5 | **Consensus change requirement** | ✅ N/A | Falcon is mandated from genesis, not via a soft-fork activation. There is no flag-day period during which old rules and new rules coexist. Consensus safety is equivalent to any rule enforced from block 1. |
| 6 | **Quantum security level** | ✅ 128-bit PQ | Falcon-512 provides NIST Level 1 security (128-bit post-quantum, 256-bit classical). This matches the security level of AES-128 and is considered adequate for the foreseeable near-term quantum threat. A future `-pqcsig=falcon1024` flag (NIST Level 5, 256-bit PQ) is planned for high-value vault outputs and will vendor PQClean `FALCONPADDED1024_CLEAN`. |
| 7 | **Implementation correctness** | ✅ Reviewed | The vendored code is PQClean `FALCONPADDED512_CLEAN` — the community-reviewed reference submission. PQClean applies automated CT-checking (valgrind ct-verif), ASAN, and UBSAN in CI. Additionally, `DeriveKeyPair` uses the deterministic `crypto_sign_seed_keypair` API for reproducible key derivation from a 48-byte HD seed, eliminating keygen randomness as an attack surface. |

The `getpqcinfo` RPC returns a machine-readable summary of these properties for
automated tooling and monitoring.

## Completed Audits

### Internal Code Review — April 9, 2026

A security review of the PQC consensus and key management code identified and resolved:
- **3 CRITICAL** — SPHINCS+ witness routing, insecure private key storage, misleading validation naming
- **5 HIGH** — hot-path logging, public key getter exposure, undocumented formats, stub KEM warnings
- **4 MEDIUM** — default KEM config, over-permissive size checks, config-dependent verification downgrade, missing memory cleanse

Full details in [REPORT.md § 9](REPORT.md).

### Full Code Audit — April 17, 2026

A comprehensive audit of consensus (GHOSTDAG), PQC integration, and atomic swap contracts identified and resolved:
- **2 HIGH** — SPHINCS+ missing domain separation context string; centralized swap secret generation (documented above)
- **4 MEDIUM** — `IsBlockAncestor` BFS node-count limit; `ComputeVirtualSelectedParentChain` returning only 1 hop; `DummySignatureCreator::CreatePQCSig` undocumented scope; `IsPQCGloballyRequired()` duplicate API
- **2 LOW** — DAG IBD provisional blue score documentation; EVM HTLC mainnet audit warning (documented above)

Full details in [TESTREPORT-2026-04-10-SECURITY-AUDIT-FINAL.md](TESTREPORT-2026-04-10-SECURITY-AUDIT-FINAL.md).

### EVM HTLC Solidity Audit — April 17, 2026

Internal audit of the EVM HTLC contract identified and fixed:
- **2 HIGH** — CEI violation in `withdraw()`/`refund()` (reentrancy); explicit `sha256()` requirement
- **3 MEDIUM** — ERC-20 approve race window; no minimum timelock; contractId collision
- **3 LOW** — Missing zero-address/amount guards; unchecked ERC-20 return values; arbitrary-token attack surface

Fixed contract source: `contrib/evm-htlc/contracts/QBTCUSDCHTLC.sol`.
Deploy with `npm run deploy:sepolia` from `contrib/evm-htlc/` before next testnet cycle.

