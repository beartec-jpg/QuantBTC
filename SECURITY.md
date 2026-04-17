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

### EVM HTLC Contract — Testnet Only, No Independent Audit (Low)

**Affected component:** Solidity HTLC contract at `0xaF898a5F565c0cAE1746122ad475c0B7F160A3eb` (Ethereum Sepolia).

The EVM HTLC contract is currently deployed on Ethereum Sepolia (testnet).  Before any mainnet deployment the contract bytecode **must** be independently audited by a qualified Solidity security firm.  Areas of particular interest:

- Reentrancy protection in `withdraw()` and `refund()`
- Correct SHA-256 hashlock verification (not keccak256)
- ERC-20 approval/transfer ordering
- Integer overflow in timelock comparisons

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

