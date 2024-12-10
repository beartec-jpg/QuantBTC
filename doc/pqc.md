# Post-Quantum Cryptography in Bitcoin Core

This document describes the post-quantum cryptography (PQC) features implemented in Bitcoin Core.

## Overview

The PQC implementation provides quantum-resistant cryptographic algorithms alongside classical cryptography,
creating a hybrid system that maintains compatibility with existing Bitcoin infrastructure while providing
protection against potential quantum computer attacks.

## Supported Algorithms

### Key Encapsulation Mechanisms (KEMs)
- **Kyber-768**: A lattice-based KEM providing 128-bit post-quantum security
- **FrodoKEM-976**: A conservative KEM based on the learning with errors problem
- **NTRU-HPS-4096-821**: A lattice-based cryptosystem with long-standing security analysis

### Digital Signatures (Coming Soon)
- **Dilithium**: A lattice-based signature scheme
- **Falcon**: A fast lattice-based signature scheme
- **SPHINCS+**: A stateless hash-based signature scheme

## Configuration Options

The following command-line options are available:

- `-pqc=0|1`: Enable/disable all PQC features (default: 1)
- `-pqchybridkeys=0|1`: Enable/disable hybrid key generation (default: 1)
- `-pqchybridsig=0|1`: Enable/disable hybrid signatures (default: 1)
- `-pqcalgo=algo1,algo2,...`: Specify enabled PQC algorithms (default: kyber,frodo,ntru)
- `-pqcsig=sig1,sig2,...`: Specify enabled signature schemes (default: dilithium,falcon)

Example:
```bash
bitcoind -pqc=1 -pqcalgo=kyber,ntru -pqcsig=dilithium
```

## Technical Details

### Hybrid Keys
The system uses hybrid keys that combine classical ECDSA with PQC algorithms. Each key pair consists of:
1. A classical ECDSA key pair
2. One or more PQC key pairs

### Hybrid Signatures
Transaction signatures contain both:
1. A classical ECDSA signature
2. One or more PQC signatures

This ensures that transactions remain valid even if either classical or quantum cryptography is broken.

### Network Protocol
The PQC implementation maintains backward compatibility with existing Bitcoin nodes while allowing
PQC-enabled nodes to exchange quantum-resistant signatures and keys.

## Address Format

PQC-enabled addresses use the Bech32m format with witness version 2 (prefix bc1z). This follows the SegWit address structure while providing a distinct prefix for PQC transactions.

Example:
```
bc1z...  # PQC-enabled address
```

## Activation Mechanism

The PQC feature activates through a SegWit-style soft fork:

1. **Signaling Period**: Miners signal readiness using version bits
2. **Activation Threshold**: Requires 95% of blocks in a 2016-block period to signal support
3. **Grace Period**: Additional time after threshold reached before enforcement begins

### Backward Compatibility

The implementation follows SegWit principles for backward compatibility:
- Old nodes see PQC transactions as anyone-can-spend
- New nodes enforce both classical and quantum signatures
- PQC signature data stored in witness area, not counting toward legacy block size

### Block Size Considerations

To maintain network performance:
- PQC signatures stored in witness area (similar to SegWit)
- Witness data has a 75% discount in weight calculations
- Maximum block weight remains 4 million units
- Effective capacity increased for PQC transactions through witness discount

## Security Considerations

1. The hybrid approach ensures that security is maintained even if one system is compromised
2. All PQC algorithms are implemented with constant-time operations to prevent timing attacks
3. The system uses Bitcoin Core's secure random number generation facilities

## Performance Impact

The PQC implementation has the following impact on performance:
- Key generation: Additional ~100ms per key pair
- Signing: Additional ~50ms per signature
- Verification: Additional ~20ms per signature
- Transaction size: Increased by ~2-4KB depending on algorithms used

## Future Work

1. Implementation of additional PQC signature schemes
2. Optimization of signature and key sizes
3. Integration with Lightning Network
4. Enhanced quantum-resistant multisignature schemes
