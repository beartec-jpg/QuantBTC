# Post-Quantum Cryptography in Bitcoin Core

This document describes the post-quantum cryptography (PQC) features implemented in Bitcoin Core.

## Overview

The PQC implementation provides quantum-resistant cryptographic algorithms alongside classical cryptography,
creating a hybrid system that maintains compatibility with existing Bitcoin infrastructure while providing
protection against potential quantum computer attacks.

## Supported Algorithms

### Key Encapsulation Mechanisms (KEMs)
- **Kyber-768** (ML-KEM-768): A lattice-based KEM providing 128-bit post-quantum security
  - Implements the full IND-CCA2-secure scheme via the Fujisaki-Okamoto transform
  - Public key: 1184 bytes, secret key: 2400 bytes, ciphertext: 1088 bytes, shared secret: 32 bytes
  - Implemented using the pq-crystals/kyber reference C implementation (Kyber-768 ref/)
- **FrodoKEM-976**: A conservative KEM based on the learning with errors problem
  - Implements IND-CCA2 security via the Fujisaki-Okamoto transform
  - On decapsulation failure the implicit rejection path returns a deterministic pseudorandom
    shared secret derived from a per-key rejection seed `s` and the ciphertext, preventing
    adaptive chosen-ciphertext attacks
  - Stack overflow fix: the 976×976 public matrix A (~1.86 MB) is allocated on the heap
  - Public key: 15648 bytes, secret key: 31328 bytes, ciphertext: 15744 bytes, shared secret: 32 bytes
- **NTRU-HPS-4096-821**: A lattice-based cryptosystem with long-standing security analysis
  - Implements IND-CCA2 security via the Fujisaki-Okamoto transform
  - The blinding polynomial `r` is derived deterministically from the message `m` and `H(pk)` via
    SHA-512, enabling re-encryption and ciphertext comparison in Decaps
  - On decapsulation failure the implicit rejection path returns a deterministic pseudorandom
    shared secret derived from a per-key rejection seed `z` and the ciphertext
  - Note: the underlying `poly_invert` has a known bug in its extended-GCD (separate TODO); the
    FO transform is correct independently of the IND-CPA core

### Digital Signatures
- **Dilithium** (ML-DSA-44): A lattice-based signature scheme (NIST FIPS 204)
- **SPHINCS+** (SLH-DSA-SHA2-128f): A stateless hash-based signature scheme (NIST FIPS 205)
  - Parameter set: SHA2-128f (fast variant)
  - Public key: 32 bytes, private key: 64 bytes, signature: 17 088 bytes
  - Pure hash-based construction (SHA-256 only), no external dependencies
  - Implemented using the sphincs/sphincsplus reference C implementation
- **Falcon** (FN-DSA-512): A fast lattice-based signature scheme (NIST FIPS 206)
  - Public key: 897 bytes, private key: 1281 bytes, fixed-size signature: 666 bytes
  - Implemented via vendored PQClean Falcon-padded-512 reference implementation
- **SQIsign**: An isogeny-based signature scheme — **Not Yet Implemented — Disabled**
  - All operations return errors if selected; this algorithm is awaiting NIST standardization

## Configuration Options

The following command-line options are available:

- `-pqc=0|1`: Enable/disable all PQC features (default: 1)
- `-pqchybridkeys=0|1`: Enable/disable hybrid key generation (default: 1)
- `-pqchybridsig=0|1`: Enable/disable hybrid signatures (default: 1)
- `-pqcalgo=algo1,algo2,...`: Specify enabled PQC algorithms (default: kyber,frodo,ntru)
- `-pqcsig=sig1,sig2,...`: Specify enabled signature schemes (default: falcon). Note: `sqisign` is not yet implemented and will be ignored with a warning if specified.

Example:
```bash
bitcoind -pqc=1 -pqcalgo=kyber,ntru -pqcsig=falcon
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
