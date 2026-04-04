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

- **PQC consensus** — ML-DSA-44 (Dilithium2) signature verification in the script interpreter
- **GHOSTDAG consensus** — blue/red classification, mergeset computation, selected parent chain
- **Hybrid witness format** — 4-element P2WPKH witness (ECDSA + Dilithium)
- **DAG tip-set management** — tip tracking, score pruning, parent selection
- **Early protection system** — activation delay, ramp weight, IP throttling
- **Signature cache** — ECDSA, Schnorr, and Dilithium cache entry computation

For vulnerabilities in upstream Bitcoin Core code, please report to the Bitcoin Core security team at security@bitcoincore.org.
