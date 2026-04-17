#ifndef BITCOIN_CRYPTO_PQC_FALCON_H
#define BITCOIN_CRYPTO_PQC_FALCON_H

#include <stdint.h>
#include <cstddef>
#include <vector>

namespace pqc {

/**
 * Falcon-padded-512 / FN-DSA digital signature scheme.
 *
 * Wraps the vendored PQClean Falcon-padded-512 reference implementation.
 * The padded variant produces fixed-size 666-byte signatures, which is
 * essential for deterministic witness size validation on-chain.
 *
 * Security level: NIST Level 1 (AES-128 equivalent).
 * Standard: FIPS 206 (FN-DSA), finalized August 2024.
 *
 * Key advantage over Dilithium (ML-DSA-44):
 *   Signature: 666 bytes vs 2420 bytes (3.6× smaller)
 *   Public key: 897 bytes vs 1312 bytes (1.5× smaller)
 */
class Falcon {
public:
    static constexpr size_t PUBLIC_KEY_SIZE  = 897;   // FN-DSA-padded-512 public key
    static constexpr size_t PRIVATE_KEY_SIZE = 1281;  // FN-DSA-padded-512 secret key
    static constexpr size_t SIGNATURE_SIZE   = 666;   // FN-DSA-padded-512 signature (fixed)
    static constexpr size_t SEED_SIZE        = 48;    // seed for deterministic keygen

    Falcon();
    ~Falcon();

    bool GenerateKeyPair(std::vector<uint8_t>& public_key, std::vector<uint8_t>& private_key);
    bool Sign(const std::vector<uint8_t>& message, const std::vector<uint8_t>& private_key, std::vector<uint8_t>& signature);
    bool Verify(const std::vector<uint8_t>& message, const std::vector<uint8_t>& signature, const std::vector<uint8_t>& public_key);
};

} // namespace pqc

#endif // BITCOIN_CRYPTO_PQC_FALCON_H
