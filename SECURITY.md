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

